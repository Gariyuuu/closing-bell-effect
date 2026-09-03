"""End-to-end causality check on the whole feature pipeline.

The individual leak-free primitives are tested in ``test_normalization.py``.
This module makes the stronger, integration-level claim: run the real
normalisation, event tagging and volume-regime code over a panel, then destroy
everything after a cut-off date and run it again.  Nothing dated on or before
the cut-off may change.  If any stage ever reaches forward -- a global mean, a
full-sample quantile, a ``shift(-1)`` in the wrong direction -- this fails.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from closingbell import config as C
from closingbell import events as ev
from closingbell import normalize as nz

CUTOFF = 300

EVENT_COLUMNS = [
    "closing_pressure_z", "closing_pressure_pct", "abs_closing_pressure",
    "close30_mean", "close30_std", "close30_median", "close30_zrobust",
    "avol", "avol_pct", "avol_z", "cvol_median",
    "is_extreme", "extreme_up", "extreme_down", "extreme_dir",
    "is_extreme_1pct", "extreme_dir_1pct", "high_volume", "volume_regime",
]


def _panel(n=600, n_tickers=4, seed=11):
    rng = np.random.default_rng(seed)
    rows = []
    dates = pd.date_range("2021-01-04", periods=n, freq="B").date
    for t in range(n_tickers):
        r = rng.standard_t(4, n) * 0.004
        v = rng.lognormal(15 + 0.3 * t, 0.45, n)
        for i, d in enumerate(dates):
            rows.append((f"T{t}", d, r[i], r[i] * 1.5, v[i]))
    df = pd.DataFrame(rows, columns=["ticker", "session", "r_close30",
                                     "r_close60", "close30_volume"])
    return df.sort_values(["ticker", "session"]).reset_index(drop=True)


def _poison_future(df: pd.DataFrame, cutoff_date) -> pd.DataFrame:
    """Replace every post-cutoff observation with wildly different values."""
    rng = np.random.default_rng(999)
    out = df.copy()
    m = out["session"] > cutoff_date
    out.loc[m, "r_close30"] = rng.normal(0.5, 0.5, int(m.sum()))
    out.loc[m, "r_close60"] = rng.normal(0.5, 0.5, int(m.sum()))
    out.loc[m, "close30_volume"] = rng.lognormal(25, 2.0, int(m.sum()))
    return out


def test_event_classification_does_not_depend_on_the_future():
    df = _panel()
    cutoff = sorted(df["session"].unique())[CUTOFF]

    base = nz.build_normalized(df)
    poisoned = nz.build_normalized(_poison_future(df, cutoff))

    keys = ["ticker", "session"]
    b = base[base["session"] <= cutoff].sort_values(keys).reset_index(drop=True)
    p = poisoned[poisoned["session"] <= cutoff].sort_values(keys).reset_index(drop=True)
    assert len(b) > 1000
    pd.testing.assert_frame_equal(b[keys + EVENT_COLUMNS], p[keys + EVENT_COLUMNS])


def test_the_poisoning_would_have_been_detected():
    """Guard against a vacuous test: the future really is different."""
    df = _panel()
    cutoff = sorted(df["session"].unique())[CUTOFF]
    base = nz.build_normalized(df)
    poisoned = nz.build_normalized(_poison_future(df, cutoff))
    b = base[base["session"] > cutoff]
    p = poisoned[poisoned["session"] > cutoff]
    assert not np.allclose(b["closing_pressure_z"].fillna(0),
                           p["closing_pressure_z"].fillna(0))


def test_truncating_the_sample_reproduces_the_same_classifications():
    """Running on a shorter sample must give identical results on the overlap.

    This is the property that lets the study claim its event flags could have
    been produced in real time, one session at a time.
    """
    df = _panel()
    cutoff = sorted(df["session"].unique())[CUTOFF]
    full = nz.build_normalized(df)
    short = nz.build_normalized(df[df["session"] <= cutoff].copy())

    keys = ["ticker", "session"]
    a = full[full["session"] <= cutoff].sort_values(keys).reset_index(drop=True)
    b = short.sort_values(keys).reset_index(drop=True)
    pd.testing.assert_frame_equal(a[keys + EVENT_COLUMNS], b[keys + EVENT_COLUMNS])


def test_extreme_events_use_only_information_available_at_1600():
    """Every input to the event flag is dated on or before the event session."""
    df = _panel()
    d = nz.build_normalized(df)
    ev_rows = d[d["is_extreme"]]
    assert len(ev_rows) > 50
    # The percentile that defines the event is built from at least MIN_TRAILING_OBS
    # strictly earlier sessions.
    assert (ev_rows["close30_n"] >= C.MIN_TRAILING_OBS).all()
    assert (ev_rows["cvol_n"] >= C.MIN_TRAILING_OBS).all()
