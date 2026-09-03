"""Block-bootstrap inference."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from closingbell import config as C
from closingbell import events as ev


def _panel(n_dates=400, n_tickers=12, seed=0, common_sd=0.01, idio_sd=0.002):
    """A panel with a strong common daily factor -- the realistic case."""
    rng = np.random.default_rng(seed)
    dates = pd.date_range("2022-01-03", periods=n_dates, freq="B").date
    common = rng.normal(0, common_sd, n_dates)
    rows = []
    for i, d in enumerate(dates):
        for t in range(n_tickers):
            rows.append((d, f"T{t}", common[i] + rng.normal(0, idio_sd)))
    return pd.DataFrame(rows, columns=["session", "ticker", "x"])


def test_bootstrap_is_reproducible():
    df = _panel()
    a = ev.block_bootstrap_ci(df, "x", "mean", n_boot=500)
    b = ev.block_bootstrap_ci(df, "x", "mean", n_boot=500)
    assert a == b


def test_interval_brackets_the_point_estimate():
    df = _panel()
    lo, hi = ev.block_bootstrap_ci(df, "x", "mean", n_boot=2000)
    assert lo < df["x"].mean() < hi


def test_date_blocking_widens_intervals_versus_ignoring_dependence():
    """With a common daily factor, treating rows as independent understates risk."""
    df = _panel(common_sd=0.02, idio_sd=0.001)
    lo, hi = ev.block_bootstrap_ci(df, "x", "mean", n_boot=3000)
    block_width = hi - lo

    rng = np.random.default_rng(1)
    vals = df["x"].to_numpy()
    naive = [vals[rng.integers(0, len(vals), len(vals))].mean() for _ in range(3000)]
    naive_width = float(np.quantile(naive, 0.975) - np.quantile(naive, 0.025))
    assert block_width > 2 * naive_width


def test_clustered_t_matches_a_test_on_date_means():
    df = _panel()
    mean, t = ev.cluster_t_stat(df, "x")
    per_date = df.groupby("session")["x"].mean()
    expected = per_date.mean() / (per_date.std(ddof=1) / np.sqrt(len(per_date)))
    assert mean == pytest.approx(df["x"].mean())
    assert t == pytest.approx(expected)


def test_gather_reconstructs_whole_dates():
    """A resampled date must bring all of its rows, never a subset."""
    df = _panel(n_dates=10, n_tickers=3)
    vals = df["x"].to_numpy()
    v, starts, counts, sums, n_dates = ev._date_blocks(vals, df["session"].to_numpy())
    assert n_dates == 10
    assert (counts == 3).all()
    pos = ev._gather(starts, counts, np.array([0, 0, 5]))
    assert len(pos) == 9
    assert sorted(v[pos[:3]]) == sorted(v[pos[3:6]])       # date 0 taken twice


def test_prob_same_sign_counts_direction_correctly():
    df = pd.DataFrame({
        "session": pd.date_range("2022-01-03", periods=6, freq="B").date,
        "r_overnight": [0.01, -0.01, 0.01, -0.01, 0.02, 0.02],
        "extreme_dir": [1, 1, 1, -1, -1, -1],
    })
    out = ev.prob_same_sign(df, "r_overnight", "extreme_dir")
    assert out["n"] == 6
    # up events: +,-,+ -> 2 of 3 ; down events: -,+,+ -> 1 of 3
    assert out["p_same"] == pytest.approx(3 / 6)


def test_excess_over_baseline_is_zero_when_the_cell_is_the_universe():
    df = _panel()
    df = df.rename(columns={"x": "r_overnight"})
    out = ev.excess_over_baseline(df, df, "r_overnight", n_boot=500)
    assert out["excess_bps"] == pytest.approx(0.0, abs=1e-9)
    assert out["excess_ci_low_bps"] <= 0 <= out["excess_ci_high_bps"]
