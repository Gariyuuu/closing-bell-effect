"""Strictly backward-looking normalisation.

Every statistic in this module is computed from a trailing window of *earlier*
sessions for the same ticker.  The current session is never part of its own
reference distribution, and no future session is ever visible.  This is the
single place where look-ahead bias could enter the study, so the leak-free
construction is implemented once, here, and tested directly in
``tests/test_normalization.py``.

Windows are counted in *valid observations*, not calendar rows: a session where
the variable does not exist (an early close has no 15:30-16:00 window) does not
consume a slot in the trailing window.
"""
from __future__ import annotations

import warnings

import numpy as np
import pandas as pd

from . import config as C


def _sliding(values: np.ndarray, window: int) -> np.ndarray:
    """Matrix whose row *i* holds the ``window`` values that PRECEDE ``values[i]``.

    Rows are padded with NaN at the start of the series.
    """
    n = len(values)
    padded = np.concatenate([np.full(window, np.nan), values])
    idx = np.arange(n)[:, None] + np.arange(window)[None, :]
    return padded[idx]


def trailing_reference(x: pd.Series, window: int = C.TRAILING_WINDOW,
                       min_obs: int = C.MIN_TRAILING_OBS) -> pd.DataFrame:
    """Trailing mean/std/median/percentile for one ticker's series.

    ``x`` may contain NaNs; they are dropped before the window is formed and
    the results are re-indexed back onto the original index.
    """
    valid = x.dropna()
    out = pd.DataFrame(index=x.index, columns=["mean", "std", "median", "mad",
                                               "n_obs", "pct"], dtype=float)
    if valid.empty:
        return out

    v = valid.to_numpy(dtype=float)
    prev = _sliding(v, window)                      # (n, window) of earlier values
    n_obs = np.sum(~np.isnan(prev), axis=1)
    # Early rows have an all-NaN trailing window by construction; the empty-slice
    # warnings that produces are expected and are filtered rather than printed.
    with np.errstate(invalid="ignore"), warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        mean = np.nanmean(prev, axis=1)
        std = np.nanstd(prev, axis=1, ddof=1)
        median = np.nanmedian(prev, axis=1)
        mad = np.nanmedian(np.abs(prev - median[:, None]), axis=1)
        # Percentile of the current value inside the trailing window.
        less = np.nansum(prev < v[:, None], axis=1)
        equal = np.nansum(prev == v[:, None], axis=1)
        pct = (less + 0.5 * equal) / np.where(n_obs > 0, n_obs, np.nan)

    ok = n_obs >= min_obs
    res = pd.DataFrame({"mean": mean, "std": std, "median": median, "mad": mad,
                        "n_obs": n_obs.astype(float), "pct": pct}, index=valid.index)
    res.loc[~ok, ["mean", "std", "median", "mad", "pct"]] = np.nan
    out.loc[res.index, res.columns] = res
    return out


def add_trailing(df: pd.DataFrame, value: str, prefix: str,
                 group: str = "ticker", sort_by: str = "session",
                 window: int = C.TRAILING_WINDOW,
                 min_obs: int = C.MIN_TRAILING_OBS) -> pd.DataFrame:
    """Attach ``{prefix}_mean/std/median/mad/n/pct/z/zrobust`` columns."""
    d = df.sort_values([group, sort_by]).copy()
    pieces = []
    for _, g in d.groupby(group, sort=False):
        pieces.append(trailing_reference(g[value], window, min_obs))
    ref = pd.concat(pieces).reindex(d.index)

    d[f"{prefix}_mean"] = ref["mean"]
    d[f"{prefix}_std"] = ref["std"]
    d[f"{prefix}_median"] = ref["median"]
    d[f"{prefix}_mad"] = ref["mad"]
    d[f"{prefix}_n"] = ref["n_obs"]
    d[f"{prefix}_pct"] = ref["pct"]
    with np.errstate(invalid="ignore", divide="ignore"):
        d[f"{prefix}_z"] = (d[value] - ref["mean"]) / ref["std"].replace(0, np.nan)
        # Median/MAD version, scaled to be comparable with a Gaussian sigma.
        d[f"{prefix}_zrobust"] = ((d[value] - ref["median"])
                                  / (1.4826 * ref["mad"]).replace(0, np.nan))
    return d


def add_closing_pressure(sess: pd.DataFrame, window: int = C.TRAILING_WINDOW) -> pd.DataFrame:
    """Closing z-score, percentile and absolute pressure for the final 30 min."""
    d = add_trailing(sess, "r_close30", "close30", window=window)
    d = add_trailing(d, "r_close60", "close60", window=window)
    d["closing_pressure_z"] = d["close30_z"]
    d["closing_pressure_pct"] = d["close30_pct"]
    d["abs_closing_pressure"] = d["close30_z"].abs()
    return d


def add_closing_volume_surprise(sess: pd.DataFrame,
                                window: int = C.TRAILING_WINDOW) -> pd.DataFrame:
    """AVOL: log closing volume less log trailing-median closing volume."""
    d = sess.copy()
    d["log_close30_volume"] = np.log(d["close30_volume"].where(d["close30_volume"] > 0))
    d = add_trailing(d, "log_close30_volume", "cvol", window=window)
    d["avol"] = d["log_close30_volume"] - d["cvol_median"]
    d["avol_pct"] = d["cvol_pct"]
    d["avol_z"] = d["cvol_z"]
    return d


def tag_extremes(sess: pd.DataFrame, tail: float = C.TAIL_PCT,
                 suffix: str = "") -> pd.DataFrame:
    """Flag extreme closing pressure using trailing percentiles only.

    An event is extreme when the session's final-30-minute return sits in the
    top or bottom ``tail`` of that ticker's own trailing distribution.  Because
    the percentile is computed against earlier sessions only, the classification
    could have been made at 16:00 on the day itself.
    """
    d = sess.copy()
    p = d["closing_pressure_pct"]
    up = p >= (1 - tail)
    dn = p <= tail
    d[f"extreme_up{suffix}"] = up.fillna(False)
    d[f"extreme_down{suffix}"] = dn.fillna(False)
    d[f"is_extreme{suffix}"] = (up | dn).fillna(False)
    d[f"extreme_dir{suffix}"] = np.where(up, 1, np.where(dn, -1, 0))
    return d


def tag_volume_regime(sess: pd.DataFrame,
                      high_pctile: float = C.AVOL_HIGH_PCTILE) -> pd.DataFrame:
    d = sess.copy()
    d["high_volume"] = (d["avol_pct"] >= high_pctile).fillna(False)
    d["volume_regime"] = np.where(d["avol_pct"].isna(), "unknown",
                                  np.where(d["high_volume"], "high", "ordinary"))
    return d


def build_normalized(sess: pd.DataFrame) -> pd.DataFrame:
    d = add_closing_pressure(sess)
    d = add_closing_volume_surprise(d)
    d = tag_extremes(d, C.TAIL_PCT)
    d = tag_extremes(d, C.TAIL_PCT_ROBUST, suffix="_1pct")
    d = tag_volume_regime(d)
    return d
