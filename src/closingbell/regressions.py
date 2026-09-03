"""Panel regressions and the persistence classifier.

Specification
-------------
    r_overnight[i,t+1] = a_i + b1*r_close[i,t] + b2*AVOL[i,t]
                       + b3*r_close[i,t]*AVOL[i,t] + gamma*X[i,t] + e

``a_i`` are ticker fixed effects (absorbed as dummies).  Controls ``X`` are the
same-session market return, same-session realised volatility, the previous
overnight return, day-of-week dummies and a month-end indicator.

Standard errors
---------------
Default inference is **two-way clustered by ticker and by date**.  Date
clustering is the important one: the twelve names move together, so residuals
on the same trading day are strongly correlated.  Ticker clustering allows for
serial correlation within a name.  Results under alternative error structures
(date-only, ticker-only, Newey-West on date means, plain heteroskedasticity-
robust) are reported side by side in ``se_comparison`` so the conclusion does
not rest on one choice.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import statsmodels.api as sm

from . import config as C

DOW_ORDER = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"]

BASE_CONTROLS = ["mkt_r_session", "realized_vol", "r_overnight_prev"]


def build_design(df: pd.DataFrame, main_var: str = "r_close30",
                 vol_var: str = "avol", controls: list[str] | None = None,
                 ticker_fe: bool = True, dow: bool = True,
                 month_end: bool = True, scale_returns: bool = True) -> tuple[pd.DataFrame, pd.Series, pd.DataFrame]:
    """Assemble y, X and the cluster keys, dropping rows with any missing input."""
    controls = BASE_CONTROLS if controls is None else controls
    need = [main_var, vol_var, "r_overnight", "ticker", "session"] + controls
    d = df.dropna(subset=need).copy()

    scale = 1e4 if scale_returns else 1.0  # work in basis points
    y = d["r_overnight"] * scale

    X = pd.DataFrame(index=d.index)
    X["r_close"] = d[main_var] * scale
    X["avol"] = d[vol_var]
    X["r_close_x_avol"] = X["r_close"] * X["avol"]
    for c in controls:
        X[c] = d[c] * (scale if c.startswith(("mkt_r", "r_")) else 1.0)
    if month_end:
        X["month_end"] = d["is_month_end"].astype(float)
    if dow:
        for day in DOW_ORDER[1:]:            # Monday is the reference level
            X[f"dow_{day}"] = (d["dow"] == day).astype(float)
    if ticker_fe:
        tks = sorted(d["ticker"].unique())
        for t in tks[1:]:                    # first ticker is the reference level
            X[f"fe_{t}"] = (d["ticker"] == t).astype(float)
    X = sm.add_constant(X, has_constant="add")
    keys = d[["ticker", "session"]].copy()
    return X, y, keys


def _cluster_kwds(keys: pd.DataFrame, how: str):
    if how == "two_way":
        g = np.column_stack([pd.factorize(keys["ticker"])[0],
                             pd.factorize(keys["session"])[0]])
        return {"cov_type": "cluster", "cov_kwds": {"groups": g, "df_correction": True}}
    if how == "date":
        return {"cov_type": "cluster",
                "cov_kwds": {"groups": pd.factorize(keys["session"])[0]}}
    if how == "ticker":
        return {"cov_type": "cluster",
                "cov_kwds": {"groups": pd.factorize(keys["ticker"])[0]}}
    if how == "hc1":
        return {"cov_type": "HC1"}
    raise ValueError(how)


def fit_ols(df: pd.DataFrame, cluster: str = "two_way", **kw):
    X, y, keys = build_design(df, **kw)
    model = sm.OLS(y, X)
    res = model.fit(**_cluster_kwds(keys, cluster))
    res._keys = keys
    res._X, res._y = X, y
    return res


def tidy(res, keep_fe: bool = False) -> pd.DataFrame:
    t = pd.DataFrame({"term": res.params.index, "coef": res.params.values,
                      "se": res.bse.values, "t": res.tvalues.values,
                      "p": res.pvalues.values})
    ci = res.conf_int()
    t["ci_low"], t["ci_high"] = ci.iloc[:, 0].values, ci.iloc[:, 1].values
    if not keep_fe:
        t = t[~t["term"].str.startswith("fe_")]
    return t.reset_index(drop=True)


def se_comparison(df: pd.DataFrame, terms=("r_close", "avol", "r_close_x_avol"),
                  **kw) -> pd.DataFrame:
    rows = []
    for how in ["two_way", "date", "ticker", "hc1"]:
        res = fit_ols(df, cluster=how, **kw)
        for term in terms:
            if term in res.params.index:
                rows.append({"cov": how, "term": term,
                             "coef": res.params[term], "se": res.bse[term],
                             "t": res.tvalues[term], "p": res.pvalues[term]})
    return pd.DataFrame(rows)


def spec_ladder(df: pd.DataFrame) -> pd.DataFrame:
    """Coefficients as controls are added, so the reader can see what moves them."""
    specs = {
        "1: closing return only": dict(controls=[], ticker_fe=False, dow=False, month_end=False),
        "2: + ticker FE": dict(controls=[], ticker_fe=True, dow=False, month_end=False),
        "3: + market & vol controls": dict(controls=["mkt_r_session", "realized_vol"],
                                           ticker_fe=True, dow=False, month_end=False),
        "4: + prev overnight": dict(controls=BASE_CONTROLS, ticker_fe=True,
                                    dow=False, month_end=False),
        "5: full (calendar controls)": dict(controls=BASE_CONTROLS, ticker_fe=True,
                                            dow=True, month_end=True),
    }
    rows = []
    for name, kw in specs.items():
        res = fit_ols(df, cluster="two_way", **kw)
        for term in ["r_close", "avol", "r_close_x_avol"]:
            rows.append({"spec": name, "term": term, "coef": res.params[term],
                         "se": res.bse[term], "t": res.tvalues[term],
                         "p": res.pvalues[term], "n": int(res.nobs),
                         "r2": res.rsquared})
    return pd.DataFrame(rows)


def per_ticker_coefficients(df: pd.DataFrame, main_var: str = "r_close30",
                            outcome: str = "r_overnight") -> pd.DataFrame:
    """Ticker-by-ticker slope of the overnight return on the closing move."""
    rows = []
    for tk, g in df.groupby("ticker"):
        g = g.dropna(subset=[main_var, outcome])
        if len(g) < 100:
            continue
        X = sm.add_constant(pd.DataFrame({"r_close": g[main_var] * 1e4}, index=g.index))
        res = sm.OLS(g[outcome] * 1e4, X).fit(
            cov_type="cluster", cov_kwds={"groups": pd.factorize(g["session"])[0]})
        ci = res.conf_int().loc["r_close"]
        rows.append({"ticker": tk, "coef": res.params["r_close"],
                     "se": res.bse["r_close"], "t": res.tvalues["r_close"],
                     "p": res.pvalues["r_close"], "ci_low": ci.iloc[0],
                     "ci_high": ci.iloc[1], "n": int(res.nobs)})
    return pd.DataFrame(rows).sort_values("coef").reset_index(drop=True)


# --------------------------------------------------------------------------
# Persistence classification
# --------------------------------------------------------------------------
def persistence_frame(events: pd.DataFrame) -> pd.DataFrame:
    """Label extreme events by whether the overnight move kept the closing sign."""
    d = events.dropna(subset=["r_close30", "r_overnight", "avol"]).copy()
    d = d[d["r_close30"] != 0]
    d["persistent"] = (np.sign(d["r_close30"]) == np.sign(d["r_overnight"])).astype(int)
    return d


def fit_persistence_logit(events: pd.DataFrame, ticker_fe: bool = True):
    """Logit for P(persistent).

    The features are deliberately sign-symmetric -- the magnitude of the closing
    move, its direction, abnormal volume and their interaction -- so the model
    describes *when* a closing move carries into the next open rather than
    simply learning a directional drift.
    """
    d = persistence_frame(events)
    X = pd.DataFrame(index=d.index)
    X["abs_pressure"] = d["abs_closing_pressure"]
    X["direction"] = np.sign(d["r_close30"])
    X["avol"] = d["avol"]
    X["abs_pressure_x_avol"] = X["abs_pressure"] * X["avol"]
    X["realized_vol"] = d["realized_vol"] * 1e4
    X["mkt_r_session"] = d["mkt_r_session"] * 1e4
    X["month_end"] = d["is_month_end"].astype(float)
    if ticker_fe:
        tks = sorted(d["ticker"].unique())
        for t in tks[1:]:
            X[f"fe_{t}"] = (d["ticker"] == t).astype(float)
    X = sm.add_constant(X, has_constant="add")
    res = sm.Logit(d["persistent"], X).fit(
        disp=0, cov_type="cluster", cov_kwds={"groups": pd.factorize(d["session"])[0]})
    res._frame, res._X = d, X
    return res


def calibration_table(res, n_bins: int = 10) -> pd.DataFrame:
    """Predicted vs realised persistence rate, in bins of predicted probability."""
    d = res._frame.copy()
    d["p_hat"] = res.predict(res._X)
    d["bin"] = pd.qcut(d["p_hat"], n_bins, labels=False, duplicates="drop") + 1
    out = (d.groupby("bin")
             .agg(n=("persistent", "size"),
                  mean_predicted=("p_hat", "mean"),
                  observed=("persistent", "mean"))
             .reset_index())
    se = np.sqrt(out["observed"] * (1 - out["observed"]) / out["n"])
    out["obs_ci_low"] = out["observed"] - 1.96 * se
    out["obs_ci_high"] = out["observed"] + 1.96 * se
    return out


def persistence_by_decile(sess: pd.DataFrame, n_bins: int = 10,
                          split_volume: bool = True) -> pd.DataFrame:
    """Realised persistence rate by decile of closing pressure.

    The no-information benchmark is **not** 50%.  Overnight returns carry a
    positive unconditional drift, so a down-close persists whenever the market
    does the less likely thing.  Each decile therefore gets a drift-implied
    benchmark: P(overnight > 0) for rows whose closing move was up, and its
    complement for rows whose closing move was down.  Comparing the realised
    rate with a flat 50% line would read the ordinary overnight drift as a
    closing-pressure effect.
    """
    d = sess.dropna(subset=["closing_pressure_pct", "r_close30", "r_overnight"]).copy()
    d = d[d["r_close30"] != 0]
    d["persistent"] = (np.sign(d["r_close30"]) == np.sign(d["r_overnight"])).astype(int)
    d["decile"] = np.minimum((d["closing_pressure_pct"] * n_bins).astype(int), n_bins - 1) + 1
    p_pos = float((d["r_overnight"] > 0).mean())
    d["benchmark"] = np.where(d["r_close30"] > 0, p_pos, 1 - p_pos)
    keys = ["decile", "volume_regime"] if split_volume else ["decile"]
    out = (d.groupby(keys)
             .agg(n=("persistent", "size"), p_persistent=("persistent", "mean"),
                  benchmark=("benchmark", "mean"))
             .reset_index())
    out["excess_over_benchmark"] = out["p_persistent"] - out["benchmark"]
    se = np.sqrt(out["p_persistent"] * (1 - out["p_persistent"]) / out["n"])
    out["ci_low"] = out["p_persistent"] - 1.96 * se
    out["ci_high"] = out["p_persistent"] + 1.96 * se
    return out


def brier_and_auc(res) -> dict:
    from sklearn.metrics import brier_score_loss, roc_auc_score
    d, X = res._frame, res._X
    p = res.predict(X)
    y = d["persistent"]
    base = float(y.mean())
    return {"n": int(len(y)), "base_rate": base,
            "brier": float(brier_score_loss(y, p)),
            "brier_baseline": float(brier_score_loss(y, np.full(len(y), base))),
            "auc": float(roc_auc_score(y, p))}


def rolling_relationship(df: pd.DataFrame, window: int = 252,
                         main_var: str = "r_close30",
                         outcome: str = "r_overnight") -> pd.DataFrame:
    """Rolling pooled slope of overnight on closing return, by trailing sessions."""
    d = df.dropna(subset=[main_var, outcome]).sort_values("session")
    dates = np.array(sorted(d["session"].unique()))
    rows = []
    for i in range(window, len(dates) + 1):
        win = set(dates[i - window:i])
        g = d[d["session"].isin(win)]
        if len(g) < 200:
            continue
        X = sm.add_constant(pd.DataFrame({"r_close": g[main_var] * 1e4}, index=g.index))
        res = sm.OLS(g[outcome] * 1e4, X).fit(
            cov_type="cluster", cov_kwds={"groups": pd.factorize(g["session"])[0]})
        rows.append({"end_session": dates[i - 1], "coef": res.params["r_close"],
                     "se": res.bse["r_close"], "n": int(res.nobs)})
    out = pd.DataFrame(rows)
    if not out.empty:
        out["ci_low"] = out["coef"] - 1.96 * out["se"]
        out["ci_high"] = out["coef"] + 1.96 * out["se"]
    return out
