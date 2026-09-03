"""Conditioning the closing effect on market state and calendar position.

Regimes that can be built from verified sources only.  VIX comes from an
independent daily series; market direction from the SPY session return; the
calendar cuts are derived from the exchange trading calendar itself.

Monthly equity option expiration is included because it is a *rule*, not a
guessed list: standard U.S. equity options expire on the third Friday of the
month, rolling back to the previous session when that Friday is a holiday.
FOMC announcement days are deliberately NOT included -- reproducing them would
require hard-coding a list of dates that this repository cannot verify from any
data it ships, and a mislabelled event calendar would silently corrupt the
comparison.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from . import config as C
from .events import block_bootstrap_ci, cluster_t_stat, prob_same_sign


def add_vix(sess: pd.DataFrame, vix: pd.DataFrame) -> pd.DataFrame:
    """Attach the VIX close of the *event* session (known by 16:00 that day)."""
    d = sess.merge(vix, on="session", how="left")
    med = d.groupby("ticker")["vix"].transform("median")
    d["vix_regime"] = np.where(d["vix"].isna(), "unknown",
                               np.where(d["vix"] > med, "high VIX", "low VIX"))
    d["vix_tercile"] = pd.qcut(d["vix"], 3, labels=["low", "mid", "high"]).astype(object)
    return d


def add_opex(sess: pd.DataFrame, schedule: pd.DataFrame) -> pd.DataFrame:
    """Flag monthly option-expiration sessions (third Friday rule)."""
    sessions = pd.Series(sorted(schedule.index))
    ts = pd.to_datetime(sessions)
    frame = pd.DataFrame({"session": sessions, "ts": ts})
    frame["ym"] = ts.dt.to_period("M")
    fridays = frame[ts.dt.dayofweek == 4]
    third = fridays.groupby("ym").nth(2)["session"]
    opex = set(third)

    # If the third Friday is not a trading session it cannot appear above; find
    # the nominal third Friday and roll back to the previous session instead.
    nominal = {}
    for ym, g in frame.groupby("ym"):
        cal_fridays = pd.date_range(g["ts"].min().replace(day=1),
                                    g["ts"].max(), freq="W-FRI")
        if len(cal_fridays) >= 3:
            nominal[ym] = cal_fridays[2].date()
    have = set(frame["session"])
    for ym, day in nominal.items():
        if day in have:
            opex.add(day)
        else:
            prior = frame[(frame["ym"] == ym) & (frame["session"] < day)]
            if len(prior):
                opex.add(prior["session"].iloc[-1])

    d = sess.copy()
    d["is_opex"] = d["session"].isin(opex)
    return d


def add_market_direction(sess: pd.DataFrame, threshold: float = 0.005) -> pd.DataFrame:
    d = sess.copy()
    r = d["mkt_r_session"]
    d["market_day"] = np.where(r.isna(), "unknown",
                               np.where(r > threshold, "strong up",
                                        np.where(r < -threshold, "strong down", "flat")))
    return d


def build_regimes(sess: pd.DataFrame, vix: pd.DataFrame,
                  schedule: pd.DataFrame) -> pd.DataFrame:
    d = add_vix(sess, vix)
    d = add_opex(d, schedule)
    d = add_market_direction(d)
    return d


def regime_table(events: pd.DataFrame, by: str, outcome: str = "r_overnight",
                 dir_col: str = "extreme_dir", min_n: int = 30) -> pd.DataFrame:
    """Event outcomes inside each level of a regime variable, by direction."""
    rows = []
    for level, g in events.groupby(by):
        for direction, dlabel in [(1, "strong up"), (-1, "strong down")]:
            cell = g[g[dir_col] == direction].dropna(subset=[outcome])
            if len(cell) < min_n:
                continue
            mean, t = cluster_t_stat(cell, outcome)
            lo, hi = block_bootstrap_ci(cell, outcome, "mean", n_boot=2000)
            ps = prob_same_sign(cell, outcome, dir_col)
            rows.append({"regime_var": by, "regime": level, "direction": dlabel,
                         "n": int(len(cell)),
                         "mean_bps": mean * 1e4, "ci_low_bps": lo * 1e4,
                         "ci_high_bps": hi * 1e4, "t_stat": t,
                         "p_same_sign": ps["p_same"],
                         "mean_close30_bps": cell["r_close30"].mean() * 1e4})
    return pd.DataFrame(rows)


def all_regime_tables(events: pd.DataFrame, outcome: str = "r_overnight") -> pd.DataFrame:
    out = []
    for by in ["vix_regime", "market_day", "dow", "is_month_end",
               "is_quarter_end", "is_opex", "volume_regime"]:
        if by in events.columns:
            out.append(regime_table(events, by, outcome))
    return pd.concat([t for t in out if len(t)], ignore_index=True)


def monday_friday(events: pd.DataFrame, outcome: str = "r_overnight") -> pd.DataFrame:
    sub = events[events["dow"].isin(["Monday", "Friday"])]
    return regime_table(sub, "dow", outcome, min_n=10)
