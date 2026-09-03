"""Session validation and data-quality control.

Every (ticker, session) pair is checked against what the *exchange calendar*
says should exist, not against what the file happens to contain.  A session is
only admitted to the study if it clears the checks below; the reasons for every
exclusion are recorded so the attrition is auditable.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from . import calendar_utils as cal
from . import config as C

#: A session is dropped if more than this share of its expected 5-minute bars
#: are absent.  Isolated gaps in a liquid name are tolerable; a session that is
#: mostly missing is not.
MAX_MISSING_FRAC = 0.05

#: A session whose high/low range exceeds this fraction of its low is rejected.
#: No mega-cap in this universe moves 50% inside a session, so a range that wide
#: means two different instruments have been merged under one symbol, or a print
#: is corrupt.  This is a deliberately generic guard: it catches the symbol-reuse
#: problem without needing to know which symbol was reused.
MAX_SESSION_RANGE = 0.50

#: A single 5-minute bar spanning more than this fraction of its own low is
#: treated as an erroneous print.  The empirical gap in this sample is wide: the
#: three widest bars are known bad ticks (the 2023-01-24 NYSE opening-auction
#: error and a stray SPY low), all at 18-28%, while the widest genuine bar -- the
#: 2025-04-07 reversal -- is 9.6%.  A 15% cut sits inside that gap.
MAX_BAR_RANGE = 0.15

#: Slots without which no variable at all can be built for the session.
CORE_SLOTS = ["09:30", "09:55"]
#: Slots the closing-window variables are read from.  These only exist on a
#: full-length session -- an early close genuinely has no 15:30-16:00 window,
#: which makes it unusable as an *event* but perfectly usable as the session
#: that follows one.
CLOSE_SLOTS = ["14:55", "15:25", "15:55"]
CRITICAL_SLOTS = CORE_SLOTS + CLOSE_SLOTS


def session_quality(bars: pd.DataFrame, auction: pd.DataFrame,
                    schedule: pd.DataFrame | None = None) -> pd.DataFrame:
    """One row per (ticker, session) describing completeness and integrity."""
    if schedule is None:
        schedule = cal.session_schedule()

    b = bars.assign(bar_range=bars["high"] / bars["low"] - 1.0)
    obs = (b.groupby(["ticker", "session"])
             .agg(observed_bars=("slot", "size"),
                  n_minutes=("n_minutes", "sum"),
                  zero_volume_bars=("volume", lambda v: int((v <= 0).sum())),
                  min_price=("low", "min"),
                  max_price=("high", "max"),
                  max_bar_range=("bar_range", "max"))
             .reset_index())

    # Cross-join every ticker with every calendar session so that a ticker that
    # is entirely absent on a trading day is reported as missing, not omitted.
    tickers = sorted(bars["ticker"].unique())
    grid = pd.MultiIndex.from_product(
        [tickers, list(schedule.index)], names=["ticker", "session"]).to_frame(index=False)
    qc = grid.merge(obs, on=["ticker", "session"], how="left")
    qc["observed_bars"] = qc["observed_bars"].fillna(0).astype(int)

    sch = schedule.reset_index()[["session", "expected_bars", "is_early_close",
                                  "close_time", "dst_transition", "is_dst"]]
    qc = qc.merge(sch, on="session", how="left")
    qc["missing_bars"] = qc["expected_bars"] - qc["observed_bars"]
    qc["missing_pct"] = qc["missing_bars"] / qc["expected_bars"]

    have_auction = auction.assign(has_auction=True)[["ticker", "session", "has_auction",
                                                     "auction_price", "auction_volume"]]
    qc = qc.merge(have_auction, on=["ticker", "session"], how="left")
    qc["has_auction"] = qc["has_auction"].fillna(False).astype(bool)

    # Presence of the specific slots the primary variables are read from.
    present = bars.assign(one=1).pivot_table(index=["ticker", "session"], columns="slot",
                                             values="one", aggfunc="max")
    flags = pd.DataFrame(index=present.index)
    for slot in CRITICAL_SLOTS:
        name = f"has_{slot.replace(':', '')}"
        flags[name] = present[slot] if slot in present.columns else np.nan
    qc = qc.merge(flags.reset_index(), on=["ticker", "session"], how="left")
    crit_cols = [f"has_{s.replace(':', '')}" for s in CRITICAL_SLOTS]
    for c in crit_cols:
        qc[c] = qc[c].notna() & qc[c].fillna(0).astype(bool)
    core_cols = [f"has_{s.replace(':', '')}" for s in CORE_SLOTS]
    close_cols = [f"has_{s.replace(':', '')}" for s in CLOSE_SLOTS]
    qc["has_core_slots"] = qc[core_cols].all(axis=1)
    qc["has_close_slots"] = qc[close_cols].all(axis=1)

    # Integrity of the bars themselves.
    bad = bars[(bars["high"] < bars["low"]) |
               (bars["close"] > bars["high"]) | (bars["close"] < bars["low"]) |
               (bars["open"] > bars["high"]) | (bars["open"] < bars["low"]) |
               (bars[["open", "high", "low", "close"]] <= 0).any(axis=1)]
    bad_ct = bad.groupby(["ticker", "session"]).size().rename("bad_bars").reset_index()
    qc = qc.merge(bad_ct, on=["ticker", "session"], how="left")
    qc["bad_bars"] = qc["bad_bars"].fillna(0).astype(int)

    qc["session_range"] = qc["max_price"] / qc["min_price"] - 1.0

    reason = pd.Series("", index=qc.index, dtype=object)
    reason = reason.mask(qc["observed_bars"] == 0, "no_data")
    reason = reason.mask((reason == "") & (qc["observed_bars"] > qc["expected_bars"]),
                         "excess_bars")
    reason = reason.mask((reason == "") & (qc["session_range"] > MAX_SESSION_RANGE),
                         "implausible_range")
    reason = reason.mask((reason == "") & (qc["max_bar_range"] > MAX_BAR_RANGE),
                         "erroneous_print")
    reason = reason.mask((reason == "") & (qc["missing_pct"] > MAX_MISSING_FRAC),
                         "incomplete_session")
    reason = reason.mask((reason == "") & (qc["bad_bars"] > 0), "bar_integrity")
    reason = reason.mask((reason == "") & ~qc["has_core_slots"], "missing_core_slot")
    qc["exclusion_reason"] = reason
    qc["usable"] = qc["exclusion_reason"] == ""
    # Only a full-length session can host a 15:30-16:00 event, and only if the
    # slots that window is measured from are actually there.
    qc["event_eligible"] = qc["usable"] & ~qc["is_early_close"] & qc["has_close_slots"]
    qc.loc[qc["usable"] & ~qc["event_eligible"] & qc["is_early_close"],
           "event_exclusion_reason"] = "early_close_no_closing_window"
    qc.loc[qc["usable"] & ~qc["event_eligible"] & ~qc["is_early_close"],
           "event_exclusion_reason"] = "missing_closing_slot"
    qc["event_exclusion_reason"] = qc.get("event_exclusion_reason", pd.Series(index=qc.index)).fillna("")
    return qc


def quality_summary(qc: pd.DataFrame) -> pd.DataFrame:
    """Per-ticker attrition table for the report."""
    g = qc.groupby("ticker")
    out = pd.DataFrame({
        "calendar_sessions": g.size(),
        "sessions_with_data": g["observed_bars"].apply(lambda s: int((s > 0).sum())),
        "expected_bars": g["expected_bars"].sum(),
        "observed_bars": g["observed_bars"].sum(),
        "usable_sessions": g["usable"].sum(),
        "event_eligible_sessions": g["event_eligible"].sum(),
        "auction_coverage": g["has_auction"].mean(),
    })
    out["missing_bar_pct"] = 1 - out["observed_bars"] / out["expected_bars"]
    return out.reset_index()


def exclusion_breakdown(qc: pd.DataFrame) -> pd.DataFrame:
    ex = qc[~qc["usable"]]
    if ex.empty:
        return pd.DataFrame(columns=["exclusion_reason", "sessions", "tickers"])
    return (ex.groupby("exclusion_reason")
              .agg(sessions=("session", "size"), tickers=("ticker", "nunique"))
              .reset_index().sort_values("sessions", ascending=False))


def dst_check(qc: pd.DataFrame) -> pd.DataFrame:
    """Bar counts on DST-transition sessions.

    A 09:30-16:00 New York session is 390 wall-clock minutes on every trading
    day, including the Monday after a clock change -- the transition happens on
    Sunday.  This table exists to *demonstrate* that, rather than assume it.
    """
    t = qc[qc["dst_transition"].notna()]
    return (t.groupby(["session", "dst_transition"])
             .agg(tickers=("ticker", "nunique"),
                  expected_bars=("expected_bars", "first"),
                  median_observed=("observed_bars", "median"),
                  min_observed=("observed_bars", "min"))
             .reset_index())


def early_close_check(qc: pd.DataFrame) -> pd.DataFrame:
    t = qc[qc["is_early_close"]]
    return (t.groupby(["session", "close_time"])
             .agg(tickers=("ticker", "nunique"),
                  expected_bars=("expected_bars", "first"),
                  median_observed=("observed_bars", "median"),
                  bars_after_1300=("has_1525", "sum"))
             .reset_index())
