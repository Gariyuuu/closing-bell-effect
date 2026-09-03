"""Intraday seasonality: the empirical shape of the trading day.

This module measures the intraday profile rather than assuming it.  The
familiar U (or reverse-J) shape in volume and volatility is something the data
should demonstrate; the closing-period statistics later in the study are only
interpretable against this baseline, because "a big move in the last 30
minutes" means something different if the last 30 minutes are routinely the
most volatile part of the day.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from . import config as C


def slot_returns(bars: pd.DataFrame) -> pd.DataFrame:
    """Within-session 5-minute log returns, slot by slot.

    The first slot of a session has no within-session predecessor; its return
    would be the overnight gap, which is not an intraday observation, so it is
    left undefined.
    """
    b = bars.sort_values(["ticker", "session", "slot"]).copy()
    b["log_close"] = np.log(b["close"])
    b["r"] = b.groupby(["ticker", "session"])["log_close"].diff()
    b["abs_r"] = b["r"].abs()
    b["hl_range"] = (b["high"] - b["low"]) / b["close"]
    return b


def intraday_profile(bars: pd.DataFrame, full_sessions_only: bool = True,
                     schedule: pd.DataFrame | None = None) -> pd.DataFrame:
    """Per-ticker, per-slot seasonality statistics."""
    b = slot_returns(bars)
    if full_sessions_only:
        counts = b.groupby(["ticker", "session"])["slot"].transform("size")
        b = b[counts == C.FULL_SESSION_BARS]

    prof = (b.groupby(["ticker", "slot"])
              .agg(median_volume=("volume", "median"),
                   mean_volume=("volume", "mean"),
                   mean_abs_return=("abs_r", "mean"),
                   realized_variance=("r", lambda x: float(np.nanmean(x ** 2))),
                   mean_hl_range=("hl_range", "mean"),
                   median_hl_range=("hl_range", "median"),
                   n_obs=("volume", "size"))
              .reset_index())
    prof["rms_return"] = np.sqrt(prof["realized_variance"])
    return prof


def normalize_profile(prof: pd.DataFrame) -> pd.DataFrame:
    """Express each slot relative to the ticker's own all-day average.

    Normalising within ticker is what makes an ETF and a single name
    comparable: the level of volume differs by orders of magnitude, the *shape*
    of the day is the object of interest.
    """
    d = prof.copy()
    cols = ["median_volume", "mean_volume", "mean_abs_return",
            "realized_variance", "mean_hl_range", "rms_return"]
    for c in cols:
        d[f"{c}_norm"] = d[c] / d.groupby("ticker")[c].transform("mean")
    return d


def cross_sectional_profile(prof_norm: pd.DataFrame) -> pd.DataFrame:
    """Average normalised profile across the universe, with dispersion."""
    cols = [c for c in prof_norm.columns if c.endswith("_norm")]
    g = prof_norm.groupby("slot")
    out = g[cols].mean()
    for c in cols:
        out[f"{c}_p25"] = g[c].quantile(0.25)
        out[f"{c}_p75"] = g[c].quantile(0.75)
    return out.reset_index().sort_values("slot").reset_index(drop=True)


def u_shape_diagnostics(prof_norm: pd.DataFrame) -> pd.DataFrame:
    """Quantify the U rather than eyeball it.

    Reports, per ticker, the normalised level of the opening slot, the midday
    trough, and the closing slot, plus the close/midday ratio.  A U-shape
    implies both ends sit well above the middle.
    """
    d = prof_norm.copy()
    mid = d[(d["slot"] >= "11:30") & (d["slot"] <= "13:30")]
    rows = []
    for tk, g in d.groupby("ticker"):
        gm = mid[mid["ticker"] == tk]
        row = {"ticker": tk}
        for metric in ["median_volume_norm", "mean_abs_return_norm", "mean_hl_range_norm"]:
            # The 09:30 slot has no within-session predecessor, so return-based
            # metrics start at 09:35; volume and range are defined at 09:30.
            open_slot = "09:35" if metric == "mean_abs_return_norm" else "09:30"
            first = g.loc[g["slot"] == open_slot, metric].mean()
            last = g.loc[g["slot"] == "15:55", metric].mean()
            trough = gm[metric].mean()
            close30 = g.loc[g["slot"] >= "15:30", metric].mean()
            row[f"{metric}_open"] = first
            row[f"{metric}_midday"] = trough
            row[f"{metric}_close"] = last
            row[f"{metric}_close30"] = close30
            row[f"{metric}_close_over_midday"] = last / trough if trough else np.nan
            row[f"{metric}_open_over_midday"] = first / trough if trough else np.nan
        rows.append(row)
    return pd.DataFrame(rows)


def closing_share(bars: pd.DataFrame, auction: pd.DataFrame) -> pd.DataFrame:
    """Share of regular-hours volume transacted in the final 30 minutes."""
    counts = bars.groupby(["ticker", "session"])["slot"].transform("size")
    b = bars[counts == C.FULL_SESSION_BARS]
    tot = b.groupby(["ticker", "session"])["volume"].sum().rename("rth_volume")
    cl = (b[b["slot"] >= "15:30"].groupby(["ticker", "session"])["volume"].sum()
          .rename("close30_volume_bars"))
    d = pd.concat([tot, cl], axis=1).reset_index()
    d = d.merge(auction[["ticker", "session", "auction_volume"]],
                on=["ticker", "session"], how="left")
    d["auction_volume"] = d["auction_volume"].fillna(0.0)
    d["close30_share_ex_auction"] = d["close30_volume_bars"] / d["rth_volume"]
    d["close30_share"] = ((d["close30_volume_bars"] + d["auction_volume"])
                          / (d["rth_volume"] + d["auction_volume"]))
    d["auction_share"] = d["auction_volume"] / (d["rth_volume"] + d["auction_volume"])
    return (d.groupby("ticker")[["close30_share_ex_auction", "close30_share", "auction_share"]]
             .median().reset_index())
