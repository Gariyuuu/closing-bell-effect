"""The central event study: extreme closing moves, split by closing volume.

Inference note
--------------
Observations are not independent.  Twelve correlated names share every trading
date, so a naive i.i.d. bootstrap would understate uncertainty badly -- a
market-wide late selloff contributes twelve highly correlated rows.  Every
confidence interval here is produced by a **block bootstrap that resamples
trading dates**, carrying all tickers on a sampled date together.  The same
concern motivates date-clustered standard errors in ``regressions.py``.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from . import config as C

OUTCOMES = {
    "r_overnight": "overnight return",
    "r_open30_next": "next-session first 30 min",
    "r_session_next": "next full session (open->close)",
    "r_next_close_to_close": "next close-to-close",
}


def event_panel(sess: pd.DataFrame, tail_suffix: str = "",
                require_outcome: str = "r_overnight",
                drop_corp_action: bool = False) -> pd.DataFrame:
    """Rows eligible to be treated as closing-pressure events.

    Eligibility requires a full-length session (an early close has no
    15:30-16:00 window), a clean session, a defined closing z-score, a defined
    abnormal-volume measure, and a defined outcome.
    """
    d = sess[sess["event_eligible"].fillna(False)].copy()
    d = d[d["closing_pressure_pct"].notna() & d["avol"].notna()]
    if require_outcome:
        d = d[d[require_outcome].notna()]
    if drop_corp_action:
        d = d[~d["overnight_corp_action"].fillna(False)]
    return d.reset_index(drop=True)


# --------------------------------------------------------------------------
# Block bootstrap over trading dates
# --------------------------------------------------------------------------
def _date_blocks(values: np.ndarray, dates: np.ndarray):
    """Group observations by trading date.

    Returns the values re-ordered so that each date's observations are
    contiguous, plus the per-date start offsets, counts, sums and n.
    """
    codes, uniques = pd.factorize(dates, sort=True)
    order = np.argsort(codes, kind="stable")
    v = values[order]
    counts = np.bincount(codes, minlength=len(uniques))
    starts = np.concatenate([[0], np.cumsum(counts)[:-1]])
    sums = np.bincount(codes, weights=values, minlength=len(uniques))
    return v, starts, counts, sums, len(uniques)


def _gather(starts: np.ndarray, counts: np.ndarray, pick: np.ndarray) -> np.ndarray:
    """Positions of every observation belonging to the sampled dates."""
    c = counts[pick]
    total = int(c.sum())
    if total == 0:
        return np.empty(0, dtype=int)
    ends = np.cumsum(c)
    within = np.arange(total) - np.repeat(ends - c, c)
    return np.repeat(starts[pick], c) + within


def block_bootstrap_ci(df: pd.DataFrame, column: str, stat: str = "mean",
                       n_boot: int = C.N_BOOT, alpha: float = 0.05,
                       seed: int = C.BOOT_SEED) -> tuple[float, float]:
    """Percentile CI for a statistic, resampling whole trading dates.

    The mean is computed in closed form from per-date sums and counts, so all
    ``n_boot`` replications are evaluated in one vectorised pass; the median
    needs the actual observations and is gathered per replication.
    """
    d = df[["session", column]].dropna()
    if d.empty:
        return (np.nan, np.nan)
    vals = d[column].to_numpy(dtype=float)
    v, starts, counts, sums, n_dates = _date_blocks(vals, d["session"].to_numpy())
    if n_dates < 3:
        return (np.nan, np.nan)

    rng = np.random.default_rng(seed)
    if stat == "mean":
        pick = rng.integers(0, n_dates, size=(n_boot, n_dates))
        draws = sums[pick].sum(axis=1) / counts[pick].sum(axis=1)
    else:
        draws = np.empty(n_boot)
        for i in range(n_boot):
            pick = rng.integers(0, n_dates, n_dates)
            draws[i] = np.median(v[_gather(starts, counts, pick)])
    return tuple(np.quantile(draws, [alpha / 2, 1 - alpha / 2]))


def cluster_t_stat(df: pd.DataFrame, column: str) -> tuple[float, float]:
    """Mean and a date-clustered t-statistic for H0: mean = 0.

    Collapsing to date means and testing those is the simplest defensible
    treatment of cross-sectional dependence; it is equivalent to a
    date-clustered mean test and needs no distributional assumption beyond a
    CLT over dates.
    """
    d = df[["session", column]].dropna()
    if d.empty:
        return (np.nan, np.nan)
    per_date = d.groupby("session")[column].mean()
    n = len(per_date)
    if n < 3 or per_date.std(ddof=1) == 0:
        return (float(d[column].mean()), np.nan)
    t = per_date.mean() / (per_date.std(ddof=1) / np.sqrt(n))
    return (float(d[column].mean()), float(t))


def prob_same_sign(df: pd.DataFrame, outcome: str = "r_overnight",
                   direction_col: str = "extreme_dir") -> dict:
    """Share of events whose outcome carries the same sign as the closing move."""
    d = df[[outcome, direction_col, "session"]].dropna()
    d = d[d[direction_col] != 0]
    if d.empty:
        return {"n": 0, "p_same": np.nan, "ci_low": np.nan, "ci_high": np.nan}
    same = (np.sign(d[outcome]) == np.sign(d[direction_col])).astype(float)
    tmp = pd.DataFrame({"session": d["session"], "same": same})
    lo, hi = block_bootstrap_ci(tmp, "same", "mean")
    return {"n": int(len(d)), "p_same": float(same.mean()), "ci_low": lo, "ci_high": hi}


def cell_stats(df: pd.DataFrame, outcome: str) -> dict:
    mean, t = cluster_t_stat(df, outcome)
    lo, hi = block_bootstrap_ci(df, outcome, "mean")
    # The median needs a gathered resample, so it uses fewer replications; a
    # percentile interval is stable well below the mean's replication count.
    mlo, mhi = block_bootstrap_ci(df, outcome, "median", n_boot=2000)
    s = df[outcome].dropna()
    return {
        "n": int(s.size),
        "n_dates": int(df.loc[s.index, "session"].nunique()) if s.size else 0,
        "mean_bps": mean * 1e4,
        "ci_low_bps": lo * 1e4,
        "ci_high_bps": hi * 1e4,
        "median_bps": float(s.median()) * 1e4 if s.size else np.nan,
        "median_ci_low_bps": mlo * 1e4,
        "median_ci_high_bps": mhi * 1e4,
        "t_stat_clustered": t,
        "std_bps": float(s.std(ddof=1)) * 1e4 if s.size > 1 else np.nan,
    }


def baseline_stats(universe: pd.DataFrame, outcome: str = "r_overnight") -> dict:
    """Unconditional outcome across every eligible session.

    Equities carry a well-documented positive overnight drift, so a cell mean of
    +7 bp is not evidence of anything until it is set against the drift that a
    randomly chosen session already earns.  Every conditional mean in this study
    is reported next to this benchmark.
    """
    rec = {"direction": "all (baseline)", "volume_regime": "all",
           "outcome": outcome}
    rec.update(cell_stats(universe, outcome))
    rec["p_positive"] = float((universe[outcome] > 0).mean())
    rec["mean_close30_bps"] = universe["r_close30"].mean() * 1e4
    rec["mean_avol"] = universe["avol"].mean()
    return rec


def excess_over_baseline(cell: pd.DataFrame, universe: pd.DataFrame,
                         outcome: str = "r_overnight",
                         n_boot: int = C.N_BOOT) -> dict:
    """Cell mean minus the unconditional mean, with a date-block bootstrap CI.

    Both arms are resampled on the *same* draw of trading dates, so the
    market-wide component common to the cell and the benchmark cancels instead
    of inflating the interval.
    """
    cols = ["session", outcome]
    c = cell[cols].dropna()
    u = universe[cols].dropna()
    if c.empty or u.empty:
        return {"excess_bps": np.nan, "excess_ci_low_bps": np.nan,
                "excess_ci_high_bps": np.nan, "excess_p_value": np.nan}

    dates = np.array(sorted(set(u["session"]) | set(c["session"])))
    code = {d: i for i, d in enumerate(dates)}
    n_dates = len(dates)

    def sums_counts(df):
        idx = df["session"].map(code).to_numpy()
        v = df[outcome].to_numpy(dtype=float)
        return (np.bincount(idx, weights=v, minlength=n_dates),
                np.bincount(idx, minlength=n_dates).astype(float))

    cs, cc = sums_counts(c)
    us, uc = sums_counts(u)
    rng = np.random.default_rng(C.BOOT_SEED + 2)
    pick = rng.integers(0, n_dates, size=(n_boot, n_dates))
    with np.errstate(invalid="ignore", divide="ignore"):
        draws = cs[pick].sum(1) / cc[pick].sum(1) - us[pick].sum(1) / uc[pick].sum(1)
    obs = c[outcome].mean() - u[outcome].mean()
    lo, hi = np.nanquantile(draws, [0.025, 0.975])
    p = 2 * min(np.nanmean(draws <= 0), np.nanmean(draws >= 0))
    return {"excess_bps": obs * 1e4, "excess_ci_low_bps": lo * 1e4,
            "excess_ci_high_bps": hi * 1e4, "excess_p_value": float(p)}


def two_by_two(events: pd.DataFrame, outcome: str = "r_overnight",
               dir_col: str = "extreme_dir",
               universe: pd.DataFrame | None = None) -> pd.DataFrame:
    """The central table: direction of the closing move x closing-volume regime."""
    rows = []
    if universe is not None:
        rows.append(baseline_stats(universe, outcome))
    for direction, dlabel in [(1, "strong up"), (-1, "strong down")]:
        for regime in ["high", "ordinary"]:
            cell = events[(events[dir_col] == direction) &
                          (events["volume_regime"] == regime)]
            if cell.empty:
                continue
            rec = {"direction": dlabel, "volume_regime": regime,
                   "outcome": outcome}
            rec.update(cell_stats(cell, outcome))
            ps = prob_same_sign(cell, outcome, dir_col)
            rec["p_same_sign"] = ps["p_same"]
            rec["p_same_ci_low"] = ps["ci_low"]
            rec["p_same_ci_high"] = ps["ci_high"]
            rec["mean_close30_bps"] = cell["r_close30"].mean() * 1e4
            rec["mean_avol"] = cell["avol"].mean()
            rec["p_positive"] = float((cell[outcome] > 0).mean())
            if universe is not None:
                rec.update(excess_over_baseline(cell, universe, outcome))
            rows.append(rec)
    return pd.DataFrame(rows)


def central_table(events: pd.DataFrame, dir_col: str = "extreme_dir",
                  universe: pd.DataFrame | None = None) -> pd.DataFrame:
    """The 2x2 evaluated across every outcome horizon."""
    return pd.concat([two_by_two(events, o, dir_col, universe) for o in OUTCOMES],
                     ignore_index=True)


def volume_contrast(events: pd.DataFrame, outcome: str = "r_overnight",
                    dir_col: str = "extreme_dir") -> pd.DataFrame:
    """High-minus-ordinary volume difference within each direction.

    This is the quantity the research question actually turns on: does abnormal
    closing volume separate persistence from reversal?
    """
    rows = []
    for direction, dlabel in [(1, "strong up"), (-1, "strong down")]:
        sub = events[events[dir_col] == direction]
        hi = sub[sub["volume_regime"] == "high"]
        lo = sub[sub["volume_regime"] == "ordinary"]
        if hi.empty or lo.empty:
            continue
        diff = hi[outcome].mean() - lo[outcome].mean()

        d = sub[["session", outcome, "volume_regime"]].dropna()
        vals = d[outcome].to_numpy(dtype=float)
        dates = d["session"].to_numpy()
        is_hi = (d["volume_regime"].to_numpy() == "high").astype(float)
        # Per-date sums and counts for each arm let every replication be a
        # difference of two ratios evaluated in one vectorised pass.
        _, _, _, sum_hi, n_dates = _date_blocks(vals * is_hi, dates)
        _, _, _, cnt_hi, _ = _date_blocks(is_hi, dates)
        _, _, _, sum_lo, _ = _date_blocks(vals * (1 - is_hi), dates)
        _, _, _, cnt_lo, _ = _date_blocks(1 - is_hi, dates)
        rng = np.random.default_rng(C.BOOT_SEED + 1)
        pick = rng.integers(0, n_dates, size=(C.N_BOOT, n_dates))
        with np.errstate(invalid="ignore", divide="ignore"):
            draws = (sum_hi[pick].sum(1) / cnt_hi[pick].sum(1)
                     - sum_lo[pick].sum(1) / cnt_lo[pick].sum(1))
        lo_ci, hi_ci = np.nanquantile(draws, [0.025, 0.975])
        p_two = 2 * min(np.nanmean(draws <= 0), np.nanmean(draws >= 0))
        rows.append({"direction": dlabel, "outcome": outcome,
                     "n_high": int(hi[outcome].notna().sum()),
                     "n_ordinary": int(lo[outcome].notna().sum()),
                     "mean_high_bps": hi[outcome].mean() * 1e4,
                     "mean_ordinary_bps": lo[outcome].mean() * 1e4,
                     "diff_bps": diff * 1e4,
                     "diff_ci_low_bps": lo_ci * 1e4,
                     "diff_ci_high_bps": hi_ci * 1e4,
                     "boot_p_value": float(p_two)})
    return pd.DataFrame(rows)


def decile_table(sess: pd.DataFrame, outcome: str = "r_overnight",
                 n_bins: int = 10, split_volume: bool = False) -> pd.DataFrame:
    """Outcome by decile of closing pressure (optionally split by volume regime).

    Deciles are formed on the trailing percentile, which is already a
    backward-looking quantity, so the binning itself introduces no look-ahead.
    """
    d = sess[sess["closing_pressure_pct"].notna() & sess[outcome].notna()].copy()
    d["decile"] = np.minimum((d["closing_pressure_pct"] * n_bins).astype(int), n_bins - 1) + 1
    keys = ["decile", "volume_regime"] if split_volume else ["decile"]
    rows = []
    for key, g in d.groupby(keys):
        rec = dict(zip(keys, key if isinstance(key, tuple) else (key,)))
        rec.update(cell_stats(g, outcome))
        rec["mean_close30_bps"] = g["r_close30"].mean() * 1e4
        rec["p_positive"] = float((g[outcome] > 0).mean())
        rows.append(rec)
    return pd.DataFrame(rows).sort_values(keys).reset_index(drop=True)
