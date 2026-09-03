"""Provenance checks against an independent daily vendor.

The intraday feed is only worth analysing if it reproduces prices that a second,
unrelated source agrees with.  This module aggregates the 5-minute panel back up
to daily OHLCV and compares it with daily bars fetched separately.

Two adjustments are needed for the comparison to be meaningful:

* The daily vendor reports **split-adjusted** prices while the intraday feed is
  raw, so daily prices are multiplied back up by the cumulative ratio of every
  split with an ex-date after the session.
* Daily volume is split-adjusted the other way round (a 10:1 split multiplies
  historical share counts by ten), so it is divided by the same factor.
* Daily volume includes pre- and post-market trading, which the regular-hours
  panel by construction does not.  The volume ratio is therefore expected to sit
  below one at roughly 0.85-0.95; it is reported rather than forced to match.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from . import config as C


def cumulative_split_factor(sessions: pd.Series, ticker: str,
                            splits: pd.DataFrame) -> np.ndarray:
    """Product of every split ratio with an ex-date strictly after each session."""
    sp = splits[splits["ticker"] == ticker]
    factor = np.ones(len(sessions), dtype=float)
    for _, row in sp.iterrows():
        factor *= np.where(sessions.to_numpy() < row["session"], row["split_ratio"], 1.0)
    return factor


def crossvalidate_daily(sess: pd.DataFrame, daily: pd.DataFrame,
                        splits: pd.DataFrame) -> pd.DataFrame:
    """Per-ticker agreement between the rebuilt daily bars and the vendor's."""
    d = sess.merge(daily, on=["ticker", "session"], how="inner")
    rows = []
    for tk, g in d.groupby("ticker"):
        g = g.sort_values("session").copy()
        f = cumulative_split_factor(g["session"], tk, splits)
        for col in ["d_open", "d_high", "d_low", "d_close"]:
            g[col] = g[col] * f
        err = {
            "open": (g["open_0930"] / g["d_open"] - 1).abs(),
            "high": (g["session_high"] / g["d_high"] - 1).abs(),
            "low": (g["session_low"] / g["d_low"] - 1).abs(),
            "close": (g["p_1600"] / g["d_close"] - 1).abs(),
        }
        rec = {"ticker": tk, "n_sessions": int(len(g))}
        for k, e in err.items():
            rec[f"{k}_median_bps"] = float(e.median()) * 1e4
            rec[f"{k}_p99_bps"] = float(e.quantile(0.99)) * 1e4
            rec[f"{k}_over_50bp"] = int((e > 0.005).sum())
        # Vendor volume is split-adjusted in the opposite direction to price:
        # a 10:1 split multiplies historical share counts by ten.
        vol = (g["rth_volume"] + g["auction_volume"].fillna(0)) / (g["d_volume"] / f)
        rec["volume_ratio_median"] = float(vol.median())
        rec["volume_ratio_p05"] = float(vol.quantile(0.05))
        rec["volume_ratio_p95"] = float(vol.quantile(0.95))
        rows.append(rec)
    return pd.DataFrame(rows).sort_values("ticker").reset_index(drop=True)


def worst_disagreements(sess: pd.DataFrame, daily: pd.DataFrame,
                        splits: pd.DataFrame, n: int = 15) -> pd.DataFrame:
    """The sessions where the two sources disagree most about the close."""
    d = sess.merge(daily, on=["ticker", "session"], how="inner")
    out = []
    for tk, g in d.groupby("ticker"):
        g = g.sort_values("session").copy()
        g["d_close_raw"] = g["d_close"] * cumulative_split_factor(g["session"], tk, splits)
        g["close_err_bps"] = (g["p_1600"] / g["d_close_raw"] - 1).abs() * 1e4
        out.append(g[["ticker", "session", "p_1600", "d_close_raw", "close_err_bps",
                      "close_is_auction", "usable"]])
    return (pd.concat(out).nlargest(n, "close_err_bps").reset_index(drop=True))
