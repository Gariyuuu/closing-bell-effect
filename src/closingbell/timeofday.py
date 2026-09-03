"""Is the close special, or is any 30 minutes of the day like this?

Design
------
Three non-overlapping 30-minute windows are constructed -- 09:30-10:00,
12:00-12:30 and 15:30-16:00 -- and each is tested as a predictor of the
30 minutes of trading that follows it.  The close's "following period" is the
overnight gap, since that is the next available price change.

To make the coefficients comparable, the predictor and the outcome in every
window are standardised with the same trailing, current-session-excluded
machinery used for closing pressure.  The regression is then

    z(next window)  =  a  +  b * z(this window)

so ``b`` is a standardised predictive coefficient on the same scale in all
three windows.  Claiming that the close is unusual requires the closing
coefficient to stand apart from the morning and midday ones -- otherwise the
finding is a generic short-horizon return property, not a closing effect.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import statsmodels.api as sm

from . import config as C
from . import normalize as nz

#: window -> (return column of the window, return column of the following period)
WINDOW_PAIRS = {
    "morning 09:30-10:00": ("r_open30", "r_morning_next30", "10:00-10:30"),
    "midday 12:00-12:30": ("r_midday30", "r_midday_next30", "12:30-13:00"),
    "close 15:30-16:00": ("r_close30", "r_overnight", "overnight"),
}


def build_tod_panel(sess: pd.DataFrame) -> pd.DataFrame:
    """Standardise every window return, and every following-period return."""
    d = sess.copy()
    cols = {c for pair in WINDOW_PAIRS.values() for c in pair[:2]}
    for c in sorted(cols):
        if f"{c}_z" in d.columns:
            continue
        d = nz.add_trailing(d, c, c)          # produces f"{c}_z"
    return d


def tod_regressions(sess: pd.DataFrame, restrict_to_extremes: bool = False,
                    tail: float = C.TAIL_PCT) -> pd.DataFrame:
    """Standardised predictive coefficient for each time-of-day window."""
    d = build_tod_panel(sess)
    d = d[d["usable"].fillna(False)]
    rows = []
    for label, (x_col, y_col, following) in WINDOW_PAIRS.items():
        xz, yz = f"{x_col}_z", f"{y_col}_z"
        g = d.dropna(subset=[xz, yz]).copy()
        # Early closes have no 15:30-16:00 window; they are already NaN there.
        if restrict_to_extremes:
            p = g[f"{x_col}_pct"]
            g = g[(p >= 1 - tail) | (p <= tail)]
        if len(g) < 200:
            continue
        X = sm.add_constant(pd.DataFrame({"z": g[xz]}, index=g.index))
        res = sm.OLS(g[yz], X).fit(
            cov_type="cluster",
            cov_kwds={"groups": np.column_stack([pd.factorize(g["ticker"])[0],
                                                 pd.factorize(g["session"])[0]])})
        ci = res.conf_int().loc["z"]
        rows.append({"window": label, "predicts": following,
                     "beta_std": res.params["z"], "se": res.bse["z"],
                     "t": res.tvalues["z"], "p": res.pvalues["z"],
                     "ci_low": ci.iloc[0], "ci_high": ci.iloc[1],
                     "n": int(res.nobs), "r2": res.rsquared,
                     "sample": "extremes" if restrict_to_extremes else "all"})
    return pd.DataFrame(rows)


def tod_persistence_rates(sess: pd.DataFrame, tail: float = C.TAIL_PCT) -> pd.DataFrame:
    """Same-sign continuation rate after an extreme move in each window."""
    d = build_tod_panel(sess)
    d = d[d["usable"].fillna(False)]
    rows = []
    for label, (x_col, y_col, following) in WINDOW_PAIRS.items():
        p = d[f"{x_col}_pct"]
        g = d[((p >= 1 - tail) | (p <= tail))].dropna(subset=[x_col, y_col])
        g = g[g[x_col] != 0]
        if g.empty:
            continue
        same = (np.sign(g[x_col]) == np.sign(g[y_col])).astype(float)
        tmp = pd.DataFrame({"session": g["session"].values, "same": same.values})
        from .events import block_bootstrap_ci
        lo, hi = block_bootstrap_ci(tmp, "same", "mean")
        rows.append({"window": label, "predicts": following, "n": int(len(g)),
                     "p_same_sign": float(same.mean()),
                     "ci_low": lo, "ci_high": hi,
                     "mean_next_bps": float(g[y_col].mean()) * 1e4})
    return pd.DataFrame(rows)


def window_volatility_scale(sess: pd.DataFrame) -> pd.DataFrame:
    """Raw dispersion of each window's returns -- context for the comparison.

    The three windows are not equally volatile, which is exactly why the
    comparison is run on standardised returns.
    """
    rows = []
    for label, (x_col, y_col, following) in WINDOW_PAIRS.items():
        s, n = sess[x_col].dropna(), sess[y_col].dropna()
        rows.append({"window": label,
                     "sd_window_bps": s.std(ddof=1) * 1e4,
                     "mean_abs_window_bps": s.abs().mean() * 1e4,
                     "following": following,
                     "sd_following_bps": n.std(ddof=1) * 1e4,
                     "n": int(len(s))})
    return pd.DataFrame(rows)
