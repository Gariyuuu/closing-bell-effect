"""Primary variables: session prices, window returns, overnight returns.

Timing conventions
------------------
A 5-minute slot is labelled by its LEFT edge, so the slot '15:55' spans
15:55:00-15:59:59 and its ``close`` is the last regular-hours trade.  The price
"at 15:30" is therefore the *close of the 15:25 slot*, and the price "at 10:00"
is the close of the 09:55 slot.  Using the open of the 15:30 slot instead would
put part of the final-30-minute move inside the reference price.

The 16:00 price is the official closing price, taken as the first print of the
closing auction where the feed carries it and falling back to the last regular
trade otherwise.

Corporate actions
-----------------
The feed is unadjusted, so overnight returns are corrected for splits (a
mechanical price change) and, separately, for cash dividends (a mechanical
price drop on the ex-date).  Both are non-informational; leaving them in would
manufacture enormous fake overnight moves.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from . import calendar_utils as cal
from . import config as C

#: Minimum share of regular-hours volume for the closing bar to be accepted as
#: the closing auction.  See ``build_session_table``.
MIN_AUCTION_SHARE = 0.005

#: slot whose close is the price "at" the given clock time
PRICE_SLOT = {
    "10:00": "09:55",
    "12:00": "11:55",
    "12:30": "12:25",
    "13:00": "12:55",
    "15:00": "14:55",
    "15:30": "15:25",
    "10:30": "10:25",
}


def _slot_close(bars: pd.DataFrame, slot: str, name: str) -> pd.DataFrame:
    s = bars.loc[bars["slot"] == slot, ["ticker", "session", "close"]]
    return s.rename(columns={"close": name})


def build_session_table(bars: pd.DataFrame, auction: pd.DataFrame,
                        qc: pd.DataFrame, schedule: pd.DataFrame | None = None,
                        external: dict | None = None) -> pd.DataFrame:
    """One row per (ticker, session) carrying every price/volume primitive."""
    if schedule is None:
        schedule = cal.session_schedule()

    bars = bars.copy()
    bars["log_close"] = np.log(bars["close"])

    # ---- session aggregates -------------------------------------------------
    agg = (bars.sort_values(["ticker", "session", "slot"])
               .groupby(["ticker", "session"])
               .agg(open_0930=("open", "first"),
                    last_rth_close=("close", "last"),
                    session_high=("high", "max"),
                    session_low=("low", "min"),
                    rth_volume=("volume", "sum"),
                    n_bars=("slot", "size"))
               .reset_index())

    # ---- realised variance from 5-minute log returns ------------------------
    b = bars.sort_values(["ticker", "session", "slot"]).copy()
    b["r5"] = b.groupby(["ticker", "session"])["log_close"].diff()
    rv = (b.groupby(["ticker", "session"])
            .agg(rv_5m=("r5", lambda x: float(np.nansum(x ** 2))),
                 n_r5=("r5", "count"))
            .reset_index())
    rv["realized_vol"] = np.sqrt(rv["rv_5m"])
    agg = agg.merge(rv, on=["ticker", "session"], how="left")

    # ---- reference prices ---------------------------------------------------
    for clock, slot in PRICE_SLOT.items():
        agg = agg.merge(_slot_close(bars, slot, f"p_{clock.replace(':', '')}"),
                        on=["ticker", "session"], how="left")

    # ---- official close -----------------------------------------------------
    agg = agg.merge(auction[["ticker", "session", "auction_price", "auction_volume"]],
                    on=["ticker", "session"], how="left")

    # The bar stamped at the official close is only treated as the closing
    # auction if it is large enough to plausibly BE one.  The feed intermittently
    # carries a stray one-share print at 16:00 instead of the auction (XOM for
    # much of 2021-2024); taking its price as the official close would put a
    # meaningless tick at the end of the closing window, and counting its volume
    # as auction volume would understate closing activity by orders of magnitude.
    # Real auctions run 1.5-20% of regular-hours volume, so the floor below is
    # far under any genuine auction and far above any stray print.
    share = agg["auction_volume"] / agg["rth_volume"]
    agg["auction_rejected"] = agg["auction_volume"].notna() & (share < MIN_AUCTION_SHARE)
    agg.loc[agg["auction_rejected"], ["auction_price", "auction_volume"]] = np.nan

    agg["p_1600"] = agg["auction_price"].where(agg["auction_price"].notna(),
                                               agg["last_rth_close"])
    agg["close_is_auction"] = agg["auction_price"].notna()

    # ---- closing-window volume ---------------------------------------------
    close_slots = [s for s in C.five_minute_slots() if s >= "15:30"]
    cv = (bars[bars["slot"].isin(close_slots)]
          .groupby(["ticker", "session"])["volume"].sum()
          .rename("close30_volume_bars").reset_index())
    agg = agg.merge(cv, on=["ticker", "session"], how="left")
    # The closing auction is part of the closing period's activity.
    agg["close30_volume"] = (agg["close30_volume_bars"].fillna(0)
                             + agg["auction_volume"].fillna(0))
    agg["close30_volume"] = agg["close30_volume"].where(agg["close30_volume"] > 0)

    sch = schedule.reset_index()[["session", "is_early_close", "close_time",
                                  "dst_transition", "is_dst"]]
    agg = agg.merge(sch, on="session", how="left")
    agg = agg.merge(qc[["ticker", "session", "usable", "event_eligible",
                        "exclusion_reason", "missing_pct"]],
                    on=["ticker", "session"], how="left")

    # ---- corporate actions --------------------------------------------------
    ext = external or {}
    splits = ext.get("splits", pd.DataFrame(columns=["ticker", "session", "split_ratio"]))
    divs = ext.get("dividends", pd.DataFrame(columns=["ticker", "session", "dividend"]))
    agg = agg.merge(splits, on=["ticker", "session"], how="left")
    agg = agg.merge(divs, on=["ticker", "session"], how="left")
    agg["split_ratio"] = agg["split_ratio"].fillna(1.0)
    agg["dividend"] = agg["dividend"].fillna(0.0)
    agg["is_exdiv"] = agg["dividend"] > 0
    agg["is_split"] = agg["split_ratio"] != 1.0

    return agg.sort_values(["ticker", "session"]).reset_index(drop=True)


def add_window_returns(sess: pd.DataFrame) -> pd.DataFrame:
    """Intraday window returns that use only same-session information."""
    d = sess.copy()
    d["r_close30"] = d["p_1600"] / d["p_1530"] - 1.0
    # A version of the closing move that stops at the last regular trade, so it
    # shares no price with the overnight return (which starts at the auction
    # print).  Any purely mechanical negative correlation induced by measurement
    # error in a shared closing price disappears in this specification.
    d["r_close30_ex_auction"] = d["last_rth_close"] / d["p_1530"] - 1.0
    d["r_close60"] = d["p_1600"] / d["p_1500"] - 1.0
    d["r_open30"] = d["p_1000"] / d["open_0930"] - 1.0
    d["r_session"] = d["p_1600"] / d["open_0930"] - 1.0
    d["r_midday30"] = d["p_1230"] / d["p_1200"] - 1.0
    d["r_morning_next30"] = d["p_1030"] / d["p_1000"] - 1.0
    d["r_midday_next30"] = d["p_1300"] / d["p_1230"] - 1.0

    # An early-close session has no 15:30-16:00 window at all.
    for c in ["r_close30", "r_close60", "r_close30_ex_auction"]:
        d.loc[d["is_early_close"], c] = np.nan
    return d


def add_next_session_links(sess: pd.DataFrame, schedule: pd.DataFrame | None = None) -> pd.DataFrame:
    """Attach next-session outcomes using the exchange calendar for matching.

    Matching is done through an explicit calendar successor map.  If a ticker is
    missing the session that actually follows session *t*, the overnight return
    is left NaN rather than being computed against some later session.
    """
    if schedule is None:
        schedule = cal.session_schedule()
    nxt = cal.next_session_map(list(schedule.index))

    d = sess.copy()
    d["next_session"] = d["session"].map(nxt)

    cols = ["ticker", "session", "open_0930", "p_1000", "p_1600", "r_open30",
            "r_session", "split_ratio", "dividend", "is_exdiv", "usable",
            "rv_5m", "realized_vol"]
    nx = d[cols].rename(columns={
        "session": "next_session",
        "open_0930": "n_open_0930", "p_1000": "n_p_1000", "p_1600": "n_p_1600",
        "r_open30": "r_open30_next", "r_session": "r_session_next",
        "split_ratio": "n_split_ratio", "dividend": "n_dividend",
        "is_exdiv": "n_is_exdiv", "usable": "n_usable",
        "rv_5m": "n_rv_5m", "realized_vol": "n_realized_vol"})
    d = d.merge(nx, on=["ticker", "next_session"], how="left")

    # Raw (unadjusted) overnight return, then corporate-action corrections.
    d["r_overnight_raw"] = d["n_open_0930"] / d["p_1600"] - 1.0
    adj_open = d["n_open_0930"] * d["n_split_ratio"] + d["n_dividend"]
    d["r_overnight"] = adj_open / d["p_1600"] - 1.0
    d["r_next_close_to_close"] = (d["n_p_1600"] * d["n_split_ratio"] + d["n_dividend"]) / d["p_1600"] - 1.0
    d["overnight_corp_action"] = d["n_split_ratio"].ne(1.0) | d["n_is_exdiv"].fillna(False)
    return d


def add_previous_overnight(d: pd.DataFrame) -> pd.DataFrame:
    """Previous overnight return -- a control, strictly backward-looking.

    The overnight return stored on row *t* runs from close(t) into open(t+1),
    so the overnight move that *preceded* session t is the value stored on the
    previous session's row.
    """
    d = d.sort_values(["ticker", "session"]).copy()
    d["r_overnight_prev"] = d.groupby("ticker")["r_overnight"].shift(1)
    return d


def add_market_factor(d: pd.DataFrame, proxy: str = C.MARKET_PROXY) -> pd.DataFrame:
    """Same-session market return and market closing move, as controls."""
    mkt = (d.loc[d["ticker"] == proxy, ["session", "r_session", "r_close30", "r_overnight"]]
             .rename(columns={"r_session": "mkt_r_session",
                              "r_close30": "mkt_r_close30",
                              "r_overnight": "mkt_r_overnight"}))
    return d.merge(mkt, on="session", how="left")


def add_calendar_flags(d: pd.DataFrame) -> pd.DataFrame:
    s = pd.to_datetime(d["session"])
    d = d.copy()
    d["dow"] = s.dt.day_name()
    d["month"] = s.dt.month
    d["year"] = s.dt.year
    # Month/quarter end measured on the *trading* calendar.
    order = d[["session"]].drop_duplicates().sort_values("session").reset_index(drop=True)
    ts = pd.to_datetime(order["session"])
    order["ym"] = ts.dt.to_period("M")
    order["yq"] = ts.dt.to_period("Q")
    last_m = order.groupby("ym")["session"].max()
    last_q = order.groupby("yq")["session"].max()
    d["is_month_end"] = d["session"].isin(set(last_m))
    d["is_quarter_end"] = d["session"].isin(set(last_q))
    return d


def build_features(bars, auction, qc, schedule=None, external=None) -> pd.DataFrame:
    sess = build_session_table(bars, auction, qc, schedule, external)
    sess = add_window_returns(sess)
    sess = add_next_session_links(sess, schedule)
    sess = add_previous_overnight(sess)
    sess = add_market_factor(sess)
    sess = add_calendar_flags(sess)
    return sess
