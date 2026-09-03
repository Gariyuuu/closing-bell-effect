"""Trailing normalisation must look backwards only.

These are the tests that protect the study's central claim to being
out-of-sample in time.  If any of them fail, every event classification in the
repository is contaminated.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from closingbell import config as C
from closingbell import normalize as nz


def _panel(n=300, seed=0, ticker="AAA"):
    rng = np.random.default_rng(seed)
    return pd.DataFrame({
        "ticker": ticker,
        "session": pd.date_range("2022-01-03", periods=n, freq="B").date,
        "x": rng.normal(0, 0.01, n),
    })


def test_trailing_mean_matches_a_hand_computed_window():
    df = _panel()
    out = nz.add_trailing(df, "x", "t", window=60, min_obs=40)
    i = 200
    manual = df["x"].iloc[i - 60:i]
    assert out["t_mean"].iloc[i] == pytest.approx(manual.mean())
    assert out["t_std"].iloc[i] == pytest.approx(manual.std(ddof=1))
    assert out["t_median"].iloc[i] == pytest.approx(manual.median())


def test_current_observation_is_excluded_from_its_own_reference():
    """Changing today's value must not change today's mean/median/std."""
    df = _panel()
    base = nz.add_trailing(df, "x", "t")
    bumped = df.copy()
    bumped.loc[200, "x"] = 99.0
    out = nz.add_trailing(bumped, "x", "t")
    for col in ["t_mean", "t_std", "t_median", "t_mad"]:
        assert out[col].iloc[200] == pytest.approx(base[col].iloc[200])
    # ...but the z-score itself must move, because the numerator uses today.
    assert out["t_z"].iloc[200] != pytest.approx(base["t_z"].iloc[200])


def test_no_future_information_leaks_backwards():
    """Overwriting every value after t leaves all statistics at t untouched."""
    df = _panel()
    base = nz.add_trailing(df, "x", "t")
    poisoned = df.copy()
    poisoned.loc[201:, "x"] = np.random.default_rng(7).normal(50, 10, len(df) - 201)
    out = nz.add_trailing(poisoned, "x", "t")
    cols = ["t_mean", "t_std", "t_median", "t_mad", "t_pct", "t_z", "t_zrobust", "t_n"]
    pd.testing.assert_frame_equal(base.loc[:200, cols], out.loc[:200, cols])


def test_percentile_is_computed_against_earlier_sessions_only():
    df = _panel()
    out = nz.add_trailing(df, "x", "t", window=60, min_obs=40)
    i = 150
    prev = df["x"].iloc[i - 60:i]
    expected = (prev < df["x"].iloc[i]).mean()
    assert out["t_pct"].iloc[i] == pytest.approx(expected)
    assert out["t_pct"].dropna().between(0, 1).all()


def test_minimum_history_is_enforced():
    df = _panel(n=100)
    out = nz.add_trailing(df, "x", "t", window=60, min_obs=40)
    assert out["t_z"].iloc[:40].isna().all()
    assert out["t_z"].iloc[45:].notna().all()


def test_window_counts_valid_observations_not_calendar_rows():
    """A session where the variable does not exist must not consume a slot."""
    df = _panel(n=200)
    df.loc[[50, 51, 52], "x"] = np.nan          # e.g. three early closes
    out = nz.add_trailing(df, "x", "t", window=60, min_obs=40)
    assert out.loc[[50, 51, 52], "t_z"].isna().all()
    i = 130
    manual = df["x"].dropna().iloc[:]
    pos = manual.index.get_loc(i)
    expected = manual.iloc[pos - 60:pos]
    assert out["t_mean"].iloc[i] == pytest.approx(expected.mean())
    assert out["t_n"].iloc[i] == 60


def test_normalisation_is_per_ticker():
    a = _panel(seed=1, ticker="AAA")
    b = _panel(seed=2, ticker="BBB")
    b["x"] += 5.0                                # a completely different level
    out = nz.add_trailing(pd.concat([a, b], ignore_index=True), "x", "t")
    za = out[out["ticker"] == "AAA"]["t_z"].dropna()
    zb = out[out["ticker"] == "BBB"]["t_z"].dropna()
    # BBB's offset is absorbed by its own trailing mean, so both are centred.
    assert abs(za.mean()) < 0.3 and abs(zb.mean()) < 0.3


def test_extreme_tagging_uses_trailing_percentiles():
    df = _panel(n=400)
    df = df.rename(columns={"x": "r_close30"})
    df["r_close60"] = df["r_close30"] * 1.4
    d = nz.add_closing_pressure(df)
    d = nz.tag_extremes(d, 0.05)
    tagged = d[d["is_extreme"]]
    assert (tagged["closing_pressure_pct"].between(0, 0.05) |
            tagged["closing_pressure_pct"].between(0.95, 1.0)).all()
    assert (d.loc[d["extreme_up"], "extreme_dir"] == 1).all()
    assert (d.loc[d["extreme_down"], "extreme_dir"] == -1).all()
    # Roughly the nominal tail share among rows that have enough history.
    have = d["closing_pressure_pct"].notna()
    assert 0.04 < d.loc[have, "is_extreme"].mean() < 0.16


def test_avol_is_log_volume_less_trailing_median_log_free():
    n = 200
    rng = np.random.default_rng(3)
    df = pd.DataFrame({
        "ticker": "AAA",
        "session": pd.date_range("2022-01-03", periods=n, freq="B").date,
        "close30_volume": rng.lognormal(15, 0.4, n),
    })
    out = nz.add_closing_volume_surprise(df)
    i = 150
    prev = np.log(df["close30_volume"].iloc[i - 60:i])
    assert out["avol"].iloc[i] == pytest.approx(
        np.log(df["close30_volume"].iloc[i]) - prev.median())
    # Doubling today's closing volume raises AVOL by exactly log 2.
    bumped = df.copy()
    bumped.loc[i, "close30_volume"] *= 2
    out2 = nz.add_closing_volume_surprise(bumped)
    assert out2["avol"].iloc[i] - out["avol"].iloc[i] == pytest.approx(np.log(2))
