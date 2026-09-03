"""Every figure in the report.

House style: one idea per panel, direct labelling instead of legends where it
fits, and error bars on anything that is an estimate.  Returns are shown in
basis points because the effects live at that scale and percent axes would
compress everything onto the zero line.
"""
from __future__ import annotations

import textwrap
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from . import config as C

INK = "#1c1c1c"
MUTED = "#8a8a8a"
GRID = "#e3e3e3"
UP = "#1f6f54"        # high-volume / persistence
DOWN = "#9b2226"      # ordinary-volume / reversal
ACCENT = "#2f5c8f"
FILL = "#c9d6e5"

plt.rcParams.update({
    "figure.dpi": 130, "savefig.dpi": 160, "savefig.bbox": "tight",
    "font.size": 9.5, "axes.titlesize": 11, "axes.labelsize": 9.5,
    "axes.edgecolor": MUTED, "axes.labelcolor": INK, "text.color": INK,
    "xtick.color": INK, "ytick.color": INK,
    "axes.spines.top": False, "axes.spines.right": False,
    "axes.grid": True, "grid.color": GRID, "grid.linewidth": 0.7,
    "legend.frameon": False, "figure.facecolor": "white",
})


def _finish(fig, ax, title, subtitle=None, xlabel=None, ylabel=None, note=None):
    """Common furniture: a left-aligned title block above the axes, notes below.

    The title block sits in figure coordinates above the axes rather than in an
    axes title, so it cannot collide with per-panel labels.  Long strings are
    wrapped explicitly with ``textwrap`` -- matplotlib's own ``wrap=True``
    reports an un-wrapped extent to the tight-bbox pass and leaves a large band
    of empty space above the figure.
    """
    axes = ax.ravel() if isinstance(ax, np.ndarray) else [ax]
    for a in axes:
        a.set_axisbelow(True)
    fig.tight_layout()

    width_in = fig.get_figwidth()
    height_in = fig.get_figheight()
    line_h = 0.16 / height_in            # ~11.5pt of leading in figure units

    def _block(text, size, weight, color, y_bottom, chars_per_in):
        wrapped = textwrap.fill(text, max(20, int(width_in * chars_per_in)))
        n = wrapped.count("\n") + 1
        fig.text(0.0, y_bottom, wrapped, ha="left", va="bottom",
                 fontsize=size, weight=weight, color=color)
        return y_bottom + n * line_h * (size / 10.0)

    y = 1.0 + 0.4 * line_h
    if subtitle:
        y = _block(subtitle, 9.3, "normal", MUTED, y, 13.5) + 0.3 * line_h
    _block(title, 13, "bold", INK, y, 9.5)

    if xlabel:
        for a in axes:
            a.set_xlabel(xlabel)
    if ylabel:
        axes[0].set_ylabel(ylabel)
    if note:
        wrapped = textwrap.fill(note, max(20, int(width_in * 15.5)))
        fig.text(0.0, -0.4 * line_h, wrapped, ha="left", va="top",
                 fontsize=7.6, color=MUTED)
    return fig


def _save(fig, name: str, out_dir: Path = C.FIGURES) -> Path:
    p = out_dir / f"{name}.png"
    fig.savefig(p)
    plt.close(fig)
    return p


def _slot_ticks(ax, slots):
    show = [s for s in slots if s.endswith(("00", "30"))]
    ax.set_xticks([slots.index(s) for s in show])
    ax.set_xticklabels(show, rotation=45, ha="right", fontsize=8)


# --------------------------------------------------------------------------
# 1 & 2: intraday U-curves
# --------------------------------------------------------------------------
def fig_volume_ucurve(prof_norm: pd.DataFrame, cross: pd.DataFrame) -> Path:
    slots = sorted(cross["slot"])
    fig, ax = plt.subplots(figsize=(9, 4.2))
    for tk, g in prof_norm.groupby("ticker"):
        g = g.sort_values("slot")
        ax.plot(range(len(g)), g["median_volume_norm"], color=MUTED, lw=0.7, alpha=0.45)
    c = cross.sort_values("slot")
    ax.plot(range(len(c)), c["median_volume_norm"], color=ACCENT, lw=2.4, zorder=5)
    ax.axhline(1.0, color=INK, lw=0.8, ls=(0, (4, 3)))
    ax.axvspan(slots.index("15:30") - 0.5, len(slots) - 0.5, color=FILL, alpha=0.45, zorder=0)
    ax.annotate("final 30\nminutes", xy=(slots.index("15:30") + 0.5, ax.get_ylim()[1] * 0.58),
                ha="left", fontsize=8.5, color=ACCENT)
    _slot_ticks(ax, slots)
    return _save(_finish(fig, ax,
        "Volume is U-shaped across the trading day",
        "Median 5-minute volume, each ticker scaled by its own all-day average. "
        "Grey lines are the 12 tickers; blue is the cross-sectional mean.",
        "5-minute slot (label = left edge, America/New_York)",
        "volume relative to the ticker's own daily average"), "fig01_volume_ucurve")


def fig_volatility_ucurve(prof_norm: pd.DataFrame, cross: pd.DataFrame) -> Path:
    slots = sorted(cross["slot"])
    fig, axes = plt.subplots(1, 2, figsize=(11, 4.1), sharex=True)
    for ax, metric, lab in [(axes[0], "mean_abs_return_norm", "mean |5-minute return|"),
                            (axes[1], "mean_hl_range_norm", "mean (high-low)/close")]:
        for tk, g in prof_norm.groupby("ticker"):
            ax.plot(range(len(g.sort_values('slot'))),
                    g.sort_values("slot")[metric], color=MUTED, lw=0.7, alpha=0.4)
        c = cross.sort_values("slot")
        ax.plot(range(len(c)), c[metric], color=DOWN, lw=2.3, zorder=5)
        ax.axhline(1.0, color=INK, lw=0.8, ls=(0, (4, 3)))
        ax.axvspan(slots.index("15:30") - 0.5, len(slots) - 0.5, color=FILL, alpha=0.45, zorder=0)
        ax.set_title(lab, loc="left", fontsize=9.5, color=MUTED)
        _slot_ticks(ax, slots)
    axes[0].set_ylabel("relative to the ticker's own daily average")
    return _save(_finish(fig, axes,
        "Volatility is U-shaped too, but its right arm is weaker than volume's",
        "Two measures of 5-minute variability, each ticker scaled by its own all-day average.",
        "5-minute slot (America/New_York)"), "fig02_volatility_ucurve")


# --------------------------------------------------------------------------
# 3: closing-pressure distribution
# --------------------------------------------------------------------------
def fig_closing_pressure_distribution(sess: pd.DataFrame) -> Path:
    z = sess["closing_pressure_z"].dropna()
    fig, axes = plt.subplots(1, 2, figsize=(11, 4.0))
    ax = axes[0]
    ax.hist(z.clip(-6, 6), bins=90, color=FILL, edgecolor=ACCENT, lw=0.4, density=True)
    xs = np.linspace(-6, 6, 400)
    ax.plot(xs, np.exp(-xs ** 2 / 2) / np.sqrt(2 * np.pi), color=DOWN, lw=1.6)
    ax.annotate("standard normal", xy=(1.6, 0.19), color=DOWN, fontsize=8.5)
    for q, lab in [(z.quantile(0.05), "5% tail"), (z.quantile(0.95), "95% tail")]:
        ax.axvline(q, color=INK, lw=0.9, ls=(0, (3, 2)))
    ax.set_title("trailing-standardised closing move", loc="left", fontsize=9.5, color=MUTED)
    ax.set_xlabel("closing z-score (60 prior sessions, current session excluded)")
    ax.set_ylabel("density")

    ax = axes[1]
    q = np.linspace(0.001, 0.999, 400)
    from scipy import stats
    ax.plot(stats.norm.ppf(q), np.quantile(z, q), color=ACCENT, lw=1.6)
    lim = 5.5
    ax.plot([-lim, lim], [-lim, lim], color=DOWN, lw=1.1, ls=(0, (4, 3)))
    ax.set_xlim(-lim, lim); ax.set_ylim(-lim, lim)
    ax.set_title("quantile-quantile against the normal", loc="left", fontsize=9.5, color=MUTED)
    ax.set_xlabel("normal quantile"); ax.set_ylabel("observed quantile")
    return _save(_finish(fig, axes,
        "Closing moves are fat-tailed even after standardising",
        f"n = {len(z):,} ticker-sessions. Tails run well beyond the normal, which is why "
        "events are defined by trailing percentile rather than by a fixed z threshold.",
        note="Extreme closing pressure is defined as the top or bottom 5% of a ticker's own "
             "trailing distribution, so the cut adapts to each name's volatility regime."),
        "fig03_closing_pressure_distribution")


# --------------------------------------------------------------------------
# 4: scatter
# --------------------------------------------------------------------------
def fig_scatter(universe: pd.DataFrame) -> Path:
    d = universe.dropna(subset=["closing_pressure_z", "r_overnight"])
    x = d["closing_pressure_z"].clip(-6, 6)
    y = (d["r_overnight"] * 1e4).clip(-400, 400)
    fig, ax = plt.subplots(figsize=(8.2, 5.2))
    ax.scatter(x, y, s=5, color=ACCENT, alpha=0.13, lw=0)
    bins = np.linspace(-5, 5, 21)
    idx = np.digitize(x, bins)
    mids, means, ses = [], [], []
    for b in range(1, len(bins)):
        m = idx == b
        if m.sum() > 20:
            mids.append((bins[b - 1] + bins[b]) / 2)
            means.append(y[m].mean())
            ses.append(y[m].std(ddof=1) / np.sqrt(m.sum()))
    ax.errorbar(mids, means, yerr=1.96 * np.array(ses), color=DOWN, lw=2.0,
                marker="o", ms=4, capsize=2.5, zorder=6)
    ax.axhline(0, color=INK, lw=0.9)
    ax.axvline(0, color=INK, lw=0.6, ls=(0, (3, 3)))
    ax.annotate("binned mean\n(95% CI)", xy=(3.4, max(means) if means else 0),
                color=DOWN, fontsize=8.5, ha="left")
    return _save(_finish(fig, ax,
        "The closing move barely tilts the overnight return",
        f"{len(d):,} ticker-sessions. Points are clipped for display; the binned means are not.",
        "closing pressure (trailing z-score of the 15:30-16:00 return)",
        "overnight return, basis points"), "fig04_close30_vs_overnight_scatter")


# --------------------------------------------------------------------------
# 5 + HERO 6: deciles
# --------------------------------------------------------------------------
def fig_decile(dec: pd.DataFrame) -> Path:
    d = dec.sort_values("decile")
    fig, ax = plt.subplots(figsize=(8.6, 4.4))
    err = np.vstack([d["mean_bps"] - d["ci_low_bps"], d["ci_high_bps"] - d["mean_bps"]])
    colors = [DOWN if v < 0 else UP for v in d["mean_bps"]]
    ax.bar(d["decile"], d["mean_bps"], color=colors, alpha=0.85, width=0.72)
    ax.errorbar(d["decile"], d["mean_bps"], yerr=err, fmt="none",
                ecolor=INK, elinewidth=1.0, capsize=3)
    ax.axhline(0, color=INK, lw=0.9)
    ax.set_xticks(range(1, 11))
    ax.set_xticklabels(["1\nweakest", "2", "3", "4", "5", "6", "7", "8", "9", "10\nstrongest"])
    return _save(_finish(fig, ax,
        "Overnight return by decile of closing pressure",
        "Decile 1 = the most negative final-30-minute moves, decile 10 = the most positive. "
        "Bars are means with block-bootstrap 95% intervals over trading dates.",
        "decile of the closing move (trailing percentile)",
        "mean overnight return, basis points"), "fig05_overnight_by_decile")


def fig_hero(dec_vol: pd.DataFrame, baseline: float | None = None) -> Path:
    """HERO: overnight return by closing-pressure decile, split by volume regime."""
    d = dec_vol[dec_vol["volume_regime"].isin(["high", "ordinary"])]
    fig, ax = plt.subplots(figsize=(10.2, 5.4))
    w = 0.38
    for i, (regime, color, lab) in enumerate([
            ("ordinary", MUTED, "ordinary closing volume"),
            ("high", ACCENT, "high closing volume (top 30% AVOL)")]):
        g = d[d["volume_regime"] == regime].sort_values("decile")
        pos = g["decile"] + (i - 0.5) * w
        err = np.vstack([g["mean_bps"] - g["ci_low_bps"], g["ci_high_bps"] - g["mean_bps"]])
        ax.bar(pos, g["mean_bps"], width=w, color=color, alpha=0.9, label=lab)
        ax.errorbar(pos, g["mean_bps"], yerr=err, fmt="none", ecolor=INK,
                    elinewidth=0.9, capsize=2.5)
    ax.axhline(0, color=INK, lw=1.0)
    if baseline is not None:
        ax.axhline(baseline, color=DOWN, lw=1.3, ls=(0, (5, 3)))
        ax.annotate(f"unconditional overnight\ndrift, {baseline:+.1f} bp",
                    xy=(10.62, baseline), va="center", ha="left", fontsize=8.2,
                    color=DOWN)
    ax.set_xticks(range(1, 11))
    ax.set_xticklabels(["1\nstrongest\ndown", "2", "3", "4", "5", "6", "7", "8", "9",
                        "10\nstrongest\nup"])
    ax.set_xlim(0.4, 12.9)
    ax.legend(loc="upper right", fontsize=8.8)
    return _save(_finish(fig, ax,
        "Overnight returns by closing-pressure decile, split by abnormal closing volume",
        "Does heavy volume behind a late move make it stick? Bars are mean overnight returns "
        "with block-bootstrap 95% intervals resampled over trading dates.",
        "decile of the final-30-minute move (trailing percentile, current session excluded)",
        "mean overnight return, basis points",
        note="Overnight = official close to the next session's 09:30 opening print, corrected for "
             "splits and cash dividends. Intervals resample whole dates because the twelve names "
             "are strongly correlated within a day."),
        "fig06_hero_decile_by_volume")


# --------------------------------------------------------------------------
# 7: persistence probability by decile
# --------------------------------------------------------------------------
def fig_persistence(pers: pd.DataFrame, pooled: pd.DataFrame) -> Path:
    fig, axes = plt.subplots(1, 2, figsize=(11.6, 4.5))
    ax = axes[0]
    p = pooled.sort_values("decile")
    err = np.vstack([p["p_persistent"] - p["ci_low"], p["ci_high"] - p["p_persistent"]])
    ax.errorbar(p["decile"], p["p_persistent"] * 100, yerr=err * 100, color=ACCENT,
                marker="o", ms=5, lw=1.8, capsize=3, zorder=5)
    ax.step(p["decile"], p["benchmark"] * 100, where="mid", color=DOWN, lw=1.5,
            ls=(0, (5, 3)))
    ax.annotate("no-information benchmark\n(the overnight drift)",
                xy=(5.5, p["benchmark"].max() * 100 + 0.4), color=DOWN,
                fontsize=8.2, ha="center", va="bottom")
    ax.axhline(50, color=MUTED, lw=0.9, ls=":")
    ax.set_title("realised persistence rate", loc="left", fontsize=9.5, color=MUTED)
    ax.set_xticks(range(1, 11))
    ax.set_ylabel("P(overnight keeps the closing sign), %")

    ax = axes[1]
    for regime, color, lab in [("ordinary", MUTED, "ordinary volume"),
                               ("high", ACCENT, "high volume")]:
        g = pers[pers["volume_regime"] == regime].sort_values("decile")
        ax.errorbar(g["decile"], g["excess_over_benchmark"] * 100,
                    yerr=(g["ci_high"] - g["p_persistent"]) * 100, color=color,
                    marker="o", ms=4.5, lw=1.7, capsize=2.5, label=lab)
    ax.axhline(0, color=DOWN, lw=1.3, ls=(0, (5, 3)))
    ax.set_title("excess over the benchmark, split by closing volume", loc="left",
                 fontsize=9.5, color=MUTED)
    ax.set_xticks(range(1, 11))
    ax.set_ylabel("percentage points above benchmark")
    ax.legend(fontsize=8.5, loc="lower right")
    for a in axes:
        a.set_xlabel("decile of the closing move")
    return _save(_finish(fig, axes,
        "How often does the overnight move keep the closing sign?",
        "The benchmark is not a coin flip: equities drift up overnight, so a down-close "
        "persists only when the less likely thing happens.",
        note="Descriptive only. A persistence rate above the benchmark is not a tradable "
             "edge: the overnight gap cannot be captured without crossing the spread twice "
             "and bearing gap risk, neither of which is measurable in OHLCV data."),
        "fig07_persistence_by_decile")


# --------------------------------------------------------------------------
# 8: rolling relationship
# --------------------------------------------------------------------------
def fig_rolling(roll: pd.DataFrame) -> Path:
    d = roll.copy()
    d["end_session"] = pd.to_datetime(d["end_session"])
    fig, ax = plt.subplots(figsize=(9.4, 4.2))
    ax.fill_between(d["end_session"], d["ci_low"], d["ci_high"], color=FILL, alpha=0.75)
    ax.plot(d["end_session"], d["coef"], color=ACCENT, lw=1.8)
    ax.axhline(0, color=INK, lw=1.0)
    return _save(_finish(fig, ax,
        "The close-to-overnight relationship is unstable through time",
        "Rolling 252-session pooled slope of the overnight return on the final-30-minute "
        "return, with date-clustered 95% bands. A value of -0.05 means 100 bp of late move "
        "is followed by 5 bp of overnight give-back.",
        "window end date", "slope (bp of overnight per bp of closing move)"),
        "fig08_rolling_relationship")


# --------------------------------------------------------------------------
# 9: time-of-day comparison
# --------------------------------------------------------------------------
def fig_time_of_day(tod: pd.DataFrame, tod_ext: pd.DataFrame) -> Path:
    # Both panels share an x-axis: the figure exists to compare coefficient
    # magnitudes, and independent auto-scaling would place near-identical
    # estimates at visibly different positions across the two panels.
    fig, axes = plt.subplots(1, 2, figsize=(11.4, 3.5), sharey=True, sharex=True)
    for ax, d, lab in [(axes[0], tod, "all sessions"),
                       (axes[1], tod_ext, "extreme moves only (5% tails)")]:
        d = d.sort_values("window")
        y = np.arange(len(d))
        err = np.vstack([d["beta_std"] - d["ci_low"], d["ci_high"] - d["beta_std"]])
        colors = [ACCENT if "close" in w else MUTED for w in d["window"]]
        ax.errorbar(d["beta_std"], y, xerr=err, fmt="o", ms=7, lw=0, elinewidth=1.6,
                    ecolor=INK, capsize=3, mfc="none")
        ax.scatter(d["beta_std"], y, s=55, color=colors, zorder=5)
        ax.axvline(0, color=DOWN, lw=1.1, ls=(0, (4, 3)))
        ax.set_yticks(y)
        if ax is axes[0]:
            ax.set_yticklabels([f"{w}\n-> {p}" for w, p in zip(d["window"], d["predicts"])],
                               fontsize=8.3)
        ax.set_ylim(-0.6, len(d) - 0.4)
        ax.set_title(lab, loc="left", fontsize=9.5, color=MUTED)
        ax.set_xlabel("standardised predictive coefficient")
        ax.grid(axis="y", alpha=0.0)
    return _save(_finish(fig, axes,
        "Is the close special? Compare it with the morning and midday",
        "Each 30-minute window's standardised return predicting the standardised return of "
        "the period that follows it. Two-way clustered 95% intervals.",
        note="If the closing coefficient is not distinguishable from the morning and midday "
             "coefficients, short-horizon reversal is a property of the trading day, not of "
             "the close."),
        "fig09_time_of_day_comparison")


# --------------------------------------------------------------------------
# 10: ticker forest plot
# --------------------------------------------------------------------------
def fig_forest(per_ticker: pd.DataFrame, pooled_coef: float | None = None) -> Path:
    d = per_ticker.sort_values("coef")
    y = np.arange(len(d))
    fig, ax = plt.subplots(figsize=(8.0, 5.4))
    err = np.vstack([d["coef"] - d["ci_low"], d["ci_high"] - d["coef"]])
    ax.errorbar(d["coef"], y, xerr=err, fmt="o", ms=5.5, color=ACCENT,
                elinewidth=1.4, capsize=3)
    ax.axvline(0, color=INK, lw=1.0)
    if pooled_coef is not None:
        ax.axvline(pooled_coef, color=DOWN, lw=1.4, ls=(0, (4, 3)))
        ax.annotate("pooled estimate", xy=(pooled_coef, len(d) - 0.4), color=DOWN,
                    fontsize=8.5, ha="center")
    ax.set_yticks(y); ax.set_yticklabels(d["ticker"])
    ax.grid(axis="y", alpha=0.0)
    return _save(_finish(fig, ax,
        "Per-ticker slope of the overnight return on the closing move",
        "Univariate slope estimated separately for each name, with date-clustered 95% "
        "intervals. Overlapping intervals mean the pooled estimate is not driven by one name.",
        "slope (bp overnight per bp of closing move)"), "fig10_ticker_forest")


# --------------------------------------------------------------------------
def build_all(res: dict) -> list[Path]:
    T = C.TABLES
    r = lambda n: pd.read_csv(T / f"{n}.csv")
    paths = [
        fig_volume_ucurve(r("intraday_profile"), r("intraday_profile_cross_section")),
        fig_volatility_ucurve(r("intraday_profile"), r("intraday_profile_cross_section")),
        fig_closing_pressure_distribution(res["sessions"]),
        fig_scatter(res["universe"]),
        fig_decile(r("overnight_by_decile")),
        fig_hero(r("overnight_by_decile_volume"), baseline=res.get("baseline_bps")),
        fig_persistence(r("persistence_by_decile"), r("persistence_by_decile_pooled")),
        fig_rolling(r("rolling_relationship")),
        fig_time_of_day(r("time_of_day_regressions"), r("time_of_day_regressions_extremes")),
        fig_forest(r("per_ticker_coefficients"),
                   float(res["main"].params["r_close"])),
    ]
    return paths
