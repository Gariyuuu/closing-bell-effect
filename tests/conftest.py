"""Synthetic fixtures.

The tests deliberately do not touch the downloaded dataset: they build minute
bars with known contents so that a failure points at the code rather than at the
vendor.
"""
from __future__ import annotations

import datetime as dt

import numpy as np
import pandas as pd
import pytest

from closingbell import calendar_utils as cal
from closingbell import config as C


def make_minutes(session: dt.date, ticker: str = "TEST", close_time: dt.time = C.RTH_CLOSE,
                 start_price: float = 100.0, step: float = 0.01,
                 volume: float = 1000.0, include_extended: bool = True,
                 include_auction: bool = True, auction_volume: float = 50_000.0
                 ) -> pd.DataFrame:
    """One session of 1-minute bars with a deterministic price ramp."""
    open_ts = pd.Timestamp(session).tz_localize(C.TZ) + pd.Timedelta(hours=9, minutes=30)
    close_ts = (pd.Timestamp(session).tz_localize(C.TZ)
                + pd.Timedelta(hours=close_time.hour, minutes=close_time.minute))
    rows = []
    if include_extended:
        for k in range(30):                        # 04:00 pre-market stub
            ts = pd.Timestamp(session).tz_localize(C.TZ) + pd.Timedelta(hours=4, minutes=k)
            rows.append((ts, 99.0, 99.0, 99.0, 99.0, 10.0))
    ts = open_ts
    i = 0
    while ts < close_ts:
        p = start_price + i * step
        # open=p, close=p+step, with high/low bracketing both so that the bar
        # satisfies low <= min(open, close) <= max(open, close) <= high.
        rows.append((ts, p, p + step * 1.5, p - step * 0.5, p + step, volume))
        ts += pd.Timedelta(minutes=1)
        i += 1
    if include_auction:
        p = start_price + i * step
        rows.append((close_ts, p, p, p, p, auction_volume))
    if include_extended:
        for k in range(1, 20):                     # post-close stub
            rows.append((close_ts + pd.Timedelta(minutes=k), 99.0, 99.0, 99.0, 99.0, 5.0))

    df = pd.DataFrame(rows, columns=["ts_et", "open", "high", "low", "close", "volume"])
    df["ticker"] = ticker
    df["timestamp"] = df["ts_et"].dt.tz_convert("UTC")
    df["session"] = df["ts_et"].dt.date
    return df


@pytest.fixture
def schedule():
    return cal.session_schedule("2024-01-01", "2024-12-31")


@pytest.fixture
def normal_session_minutes():
    return make_minutes(dt.date(2024, 6, 12))


@pytest.fixture
def early_close_minutes():
    # 2024-07-03 is a 13:00 ET early close.
    return make_minutes(dt.date(2024, 7, 3), close_time=dt.time(13, 0))
