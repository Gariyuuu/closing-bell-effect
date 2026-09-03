"""Primary variables: window returns, next-session matching, overnight arithmetic."""
from __future__ import annotations

import datetime as dt

import numpy as np
import pandas as pd
import pytest

from closingbell import calendar_utils as cal
from closingbell import config as C
from closingbell import features as ft
from closingbell import sessions as sq
from closingbell.ingest import to_five_minute_bars
from tests.conftest import make_minutes


def _build(sessions, schedule, ticker="TEST", **kw):
    mins = pd.concat([make_minutes(s, ticker=ticker, **kw) for s in sessions],
                     ignore_index=True)
    bars, auction = to_five_minute_bars(mins, schedule)
    return bars, auction


@pytest.fixture
def three_sessions(schedule):
    days = [dt.date(2024, 6, 11), dt.date(2024, 6, 12), dt.date(2024, 6, 13)]
    frames = []
    for i, d in enumerate(days):
        frames.append(make_minutes(d, start_price=100.0 + 10 * i, step=0.01))
    mins = pd.concat(frames, ignore_index=True)
    return to_five_minute_bars(mins, schedule)


def test_reference_prices_use_the_close_of_the_preceding_slot(schedule, three_sessions):
    bars, auction = three_sessions
    qc = sq.session_quality(bars, auction, schedule)
    s = ft.build_session_table(bars, auction, qc, schedule)
    row = s[s["session"] == dt.date(2024, 6, 12)].iloc[0]
    # Prices ramp by 0.01 per minute from 110.00 at 09:30.
    assert row["open_0930"] == pytest.approx(110.00)
    assert row["p_1000"] == pytest.approx(110.30)     # 30 minutes in
    assert row["p_1530"] == pytest.approx(113.60)     # 360 minutes in
    assert row["p_1600"] == pytest.approx(113.90)     # auction print


def test_window_returns_match_their_definitions(schedule, three_sessions):
    bars, auction = three_sessions
    qc = sq.session_quality(bars, auction, schedule)
    s = ft.add_window_returns(ft.build_session_table(bars, auction, qc, schedule))
    row = s[s["session"] == dt.date(2024, 6, 12)].iloc[0]
    assert row["r_close30"] == pytest.approx(row["p_1600"] / row["p_1530"] - 1)
    assert row["r_close60"] == pytest.approx(row["p_1600"] / row["p_1500"] - 1)
    assert row["r_open30"] == pytest.approx(row["p_1000"] / row["open_0930"] - 1)
    assert row["r_session"] == pytest.approx(row["p_1600"] / row["open_0930"] - 1)


def test_close30_uses_1530_not_the_open_of_the_1530_slot(schedule, three_sessions):
    """The 15:30 reference must sit strictly before the window being measured."""
    bars, auction = three_sessions
    qc = sq.session_quality(bars, auction, schedule)
    s = ft.build_session_table(bars, auction, qc, schedule)
    row = s[s["session"] == dt.date(2024, 6, 12)].iloc[0]
    slot_1530_open = bars[(bars["session"] == dt.date(2024, 6, 12)) &
                          (bars["slot"] == "15:30")]["open"].iloc[0]
    assert row["p_1530"] == pytest.approx(slot_1530_open)   # equal here by construction
    prior_close = bars[(bars["session"] == dt.date(2024, 6, 12)) &
                       (bars["slot"] == "15:25")]["close"].iloc[0]
    assert row["p_1530"] == pytest.approx(prior_close)


def test_closing_window_volume_includes_the_auction(schedule, three_sessions):
    bars, auction = three_sessions
    qc = sq.session_quality(bars, auction, schedule)
    s = ft.build_session_table(bars, auction, qc, schedule)
    row = s[s["session"] == dt.date(2024, 6, 12)].iloc[0]
    assert row["close30_volume_bars"] == pytest.approx(30 * 1000.0)
    assert row["auction_volume"] == pytest.approx(50_000.0)
    assert row["close30_volume"] == pytest.approx(30 * 1000.0 + 50_000.0)


def test_early_close_session_has_no_closing_window(schedule):
    bars, auction = _build([dt.date(2024, 7, 3)], schedule,
                           close_time=dt.time(13, 0))
    qc = sq.session_quality(bars, auction, schedule)
    s = ft.add_window_returns(ft.build_session_table(bars, auction, qc, schedule))
    row = s.iloc[0]
    assert row["is_early_close"]
    assert np.isnan(row["r_close30"]) and np.isnan(row["r_close60"])
    assert not row["event_eligible"]
    # It is still a perfectly good session for the data it does have.
    assert row["usable"]
    assert not np.isnan(row["r_open30"])


def test_overnight_return_links_close_to_the_next_open(schedule, three_sessions):
    bars, auction = three_sessions
    qc = sq.session_quality(bars, auction, schedule)
    s = ft.build_features(bars, auction, qc, schedule)
    a = s[s["session"] == dt.date(2024, 6, 11)].iloc[0]
    b = s[s["session"] == dt.date(2024, 6, 12)].iloc[0]
    assert a["next_session"] == dt.date(2024, 6, 12)
    assert a["r_overnight"] == pytest.approx(b["open_0930"] / a["p_1600"] - 1)


def test_next_session_matching_crosses_a_holiday_correctly(schedule):
    bars, auction = _build([dt.date(2024, 7, 3), dt.date(2024, 7, 5)], schedule)
    qc = sq.session_quality(bars, auction, schedule)
    s = ft.build_features(bars, auction, qc, schedule)
    row = s[s["session"] == dt.date(2024, 7, 3)].iloc[0]
    assert row["next_session"] == dt.date(2024, 7, 5)     # not July 4th
    assert not np.isnan(row["r_overnight"])


def test_a_missing_next_session_yields_no_overnight_return(schedule):
    """With 6/12 absent, 6/11 must not be matched to 6/13."""
    bars, auction = _build([dt.date(2024, 6, 11), dt.date(2024, 6, 13)], schedule)
    qc = sq.session_quality(bars, auction, schedule)
    s = ft.build_features(bars, auction, qc, schedule)
    row = s[s["session"] == dt.date(2024, 6, 11)].iloc[0]
    assert row["next_session"] == dt.date(2024, 6, 12)
    assert np.isnan(row["r_overnight"])


def test_overnight_is_corrected_for_splits():
    """An unadjusted 10:1 split would otherwise read as a -90% overnight move."""
    d = pd.DataFrame({
        "ticker": ["T", "T"],
        "session": [dt.date(2024, 6, 7), dt.date(2024, 6, 10)],
        "p_1600": [1200.0, 121.0], "open_0930": [1190.0, 120.0],
        "p_1000": [1195.0, 120.5], "r_open30": [0.0, 0.0], "r_session": [0.0, 0.0],
        "split_ratio": [1.0, 10.0], "dividend": [0.0, 0.0],
        "is_exdiv": [False, False], "usable": [True, True],
        "rv_5m": [0.0, 0.0], "realized_vol": [0.0, 0.0],
    })
    sched = cal.session_schedule("2024-06-01", "2024-06-30")
    out = ft.add_next_session_links(d, sched)
    row = out[out["session"] == dt.date(2024, 6, 7)].iloc[0]
    assert row["r_overnight_raw"] == pytest.approx(120.0 / 1200.0 - 1)   # -90%, wrong
    assert row["r_overnight"] == pytest.approx(1200.0 / 1200.0 - 1)      # 0%, right
    assert row["overnight_corp_action"]


def test_overnight_is_corrected_for_cash_dividends():
    d = pd.DataFrame({
        "ticker": ["T", "T"],
        "session": [dt.date(2024, 6, 11), dt.date(2024, 6, 12)],
        "p_1600": [100.0, 99.5], "open_0930": [100.0, 99.5],
        "p_1000": [100.0, 99.5], "r_open30": [0.0, 0.0], "r_session": [0.0, 0.0],
        "split_ratio": [1.0, 1.0], "dividend": [0.0, 0.50],
        "is_exdiv": [False, True], "usable": [True, True],
        "rv_5m": [0.0, 0.0], "realized_vol": [0.0, 0.0],
    })
    sched = cal.session_schedule("2024-06-01", "2024-06-30")
    out = ft.add_next_session_links(d, sched)
    row = out.iloc[0]
    assert row["r_overnight_raw"] == pytest.approx(-0.005)
    assert row["r_overnight"] == pytest.approx(0.0)        # the drop was the dividend
    assert row["overnight_corp_action"]


def test_previous_overnight_control_is_backward_looking(schedule, three_sessions):
    bars, auction = three_sessions
    qc = sq.session_quality(bars, auction, schedule)
    s = ft.build_features(bars, auction, qc, schedule).sort_values("session")
    assert np.isnan(s["r_overnight_prev"].iloc[0])
    assert s["r_overnight_prev"].iloc[1] == pytest.approx(s["r_overnight"].iloc[0])
    assert s["r_overnight_prev"].iloc[2] == pytest.approx(s["r_overnight"].iloc[1])


def test_month_end_and_quarter_end_use_trading_days():
    d = pd.DataFrame({
        "ticker": "T",
        "session": [dt.date(2024, 3, 27), dt.date(2024, 3, 28), dt.date(2024, 4, 1)],
    })
    out = ft.add_calendar_flags(d)
    # Good Friday 2024-03-29 was a holiday, so 3/28 is the last trading day of Q1.
    assert list(out["is_month_end"]) == [False, True, True]
    assert list(out["is_quarter_end"]) == [False, True, True]
    assert list(out["dow"]) == ["Wednesday", "Thursday", "Monday"]


def test_stray_closing_print_is_not_treated_as_the_auction(schedule):
    """A one-share 16:00 print must not become the official close."""
    bars, auction = _build([dt.date(2024, 6, 12)], schedule)
    auction = auction.copy()
    auction.loc[:, "auction_volume"] = 1.0          # a stray print, not an auction
    auction.loc[:, "auction_price"] = 999.0         # at an absurd price
    qc = sq.session_quality(bars, auction, schedule)
    s = ft.build_session_table(bars, auction, qc, schedule)
    row = s.iloc[0]
    assert row["auction_rejected"]
    assert not row["close_is_auction"]
    assert row["p_1600"] == pytest.approx(row["last_rth_close"])
    assert row["p_1600"] != 999.0
    # The stray share is not counted as closing-window volume either.
    assert row["close30_volume"] == pytest.approx(row["close30_volume_bars"])


def test_a_genuine_auction_is_accepted(schedule):
    bars, auction = _build([dt.date(2024, 6, 12)], schedule)
    qc = sq.session_quality(bars, auction, schedule)
    s = ft.build_session_table(bars, auction, qc, schedule)
    row = s.iloc[0]
    assert not row["auction_rejected"]
    assert row["close_is_auction"]
    assert row["p_1600"] == pytest.approx(row["auction_price"])
    assert row["close30_volume"] > row["close30_volume_bars"]
