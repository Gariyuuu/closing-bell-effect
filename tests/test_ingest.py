"""Bar aggregation: 1-minute -> 5-minute, regular hours, early closes, auctions."""
from __future__ import annotations

import datetime as dt

import pandas as pd
import pytest

from closingbell import config as C
from closingbell.ingest import to_five_minute_bars
from tests.conftest import make_minutes


def test_full_session_produces_78_five_minute_bars(schedule, normal_session_minutes):
    bars, auction = to_five_minute_bars(normal_session_minutes, schedule)
    assert len(bars) == C.FULL_SESSION_BARS
    assert bars["slot"].min() == "09:30"
    assert bars["slot"].max() == "15:55"
    assert len(auction) == 1


def test_extended_hours_bars_are_excluded(schedule, normal_session_minutes):
    bars, _ = to_five_minute_bars(normal_session_minutes, schedule)
    # The synthetic pre/post-market stubs are priced at 99.0; nothing at that
    # price may survive into the regular-hours panel.
    assert (bars["close"] != 99.0).all()
    assert bars["slot"].between("09:30", "15:55").all()


def test_five_minute_ohlcv_aggregation_is_correct(schedule):
    minutes = make_minutes(dt.date(2024, 6, 12), start_price=100.0, step=0.01,
                           volume=1000.0, include_extended=False)
    bars, _ = to_five_minute_bars(minutes, schedule)
    first = bars[bars["slot"] == "09:30"].iloc[0]
    # Minute i has open 100 + 0.01i, close 100 + 0.01(i+1); the first slot holds i = 0..4.
    assert first["open"] == pytest.approx(100.00)
    assert first["close"] == pytest.approx(100.05)
    assert first["high"] == pytest.approx(100.055)   # max over the 5 minutes
    assert first["low"] == pytest.approx(99.995)     # min over the 5 minutes
    assert first["volume"] == pytest.approx(5000.0)
    assert first["n_minutes"] == 5


def test_slot_labels_use_the_left_edge(schedule, normal_session_minutes):
    bars, _ = to_five_minute_bars(normal_session_minutes, schedule)
    for slot in ["09:30", "12:00", "15:30", "15:55"]:
        row = bars[bars["slot"] == slot].iloc[0]
        assert row["slot_ts"].strftime("%H:%M") == slot
        assert str(row["slot_ts"].tz) == C.TZ


def test_closing_window_holds_exactly_six_slots(schedule, normal_session_minutes):
    bars, _ = to_five_minute_bars(normal_session_minutes, schedule)
    close_slots = bars[bars["slot"] >= "15:30"]
    assert sorted(close_slots["slot"]) == ["15:30", "15:35", "15:40", "15:45",
                                           "15:50", "15:55"]
    assert close_slots["volume"].sum() == pytest.approx(30 * 1000.0)


def test_early_close_session_stops_at_1300(schedule, early_close_minutes):
    bars, auction = to_five_minute_bars(early_close_minutes, schedule)
    assert len(bars) == C.EARLY_SESSION_BARS
    assert bars["slot"].max() == "12:55"
    # There is no 15:30-16:00 window on an early-close day at all.
    assert bars[bars["slot"] >= "13:00"].empty
    assert auction["auction_ts"].iloc[0].time() == dt.time(13, 0)


def test_early_close_does_not_absorb_post_close_trading(schedule, early_close_minutes):
    """Trading continues after a 13:00 close; none of it is regular-hours data."""
    bars, _ = to_five_minute_bars(early_close_minutes, schedule)
    assert (bars["close"] != 99.0).all()
    assert bars["volume"].sum() == pytest.approx(210 * 1000.0)   # 210 regular minutes


def test_auction_is_the_first_print_at_the_official_close(schedule):
    minutes = make_minutes(dt.date(2024, 6, 12), auction_volume=123_456.0,
                           include_extended=False)
    bars, auction = to_five_minute_bars(minutes, schedule)
    row = auction.iloc[0]
    assert row["auction_volume"] == pytest.approx(123_456.0)
    assert row["auction_ts"].time() == dt.time(16, 0)
    # The auction minute is never double-counted inside a 5-minute slot.
    assert bars["volume"].sum() == pytest.approx(390 * 1000.0)


def test_session_missing_from_the_calendar_is_dropped(schedule):
    """A holiday must not enter the panel even if the feed carries bars for it."""
    minutes = make_minutes(dt.date(2024, 7, 4))          # Independence Day
    bars, auction = to_five_minute_bars(minutes, schedule)
    assert bars.empty and auction.empty


def test_missing_minutes_leave_the_slot_short_not_wrong(schedule):
    minutes = make_minutes(dt.date(2024, 6, 12), include_extended=False)
    thinned = minutes[~minutes["ts_et"].dt.strftime("%H:%M").isin(
        ["10:01", "10:02", "10:03"])]
    bars, _ = to_five_minute_bars(thinned, schedule)
    slot = bars[bars["slot"] == "10:00"].iloc[0]
    assert slot["n_minutes"] == 2
    assert slot["volume"] == pytest.approx(2000.0)
    assert len(bars) == C.FULL_SESSION_BARS      # the slot still exists


def test_a_fully_missing_slot_is_absent_rather_than_interpolated(schedule):
    minutes = make_minutes(dt.date(2024, 6, 12), include_extended=False)
    gone = minutes[~minutes["ts_et"].dt.strftime("%H:%M").str.startswith("11:0")]
    bars, _ = to_five_minute_bars(gone, schedule)
    assert "11:00" not in set(bars["slot"])
    assert "11:05" not in set(bars["slot"])
    assert len(bars) < C.FULL_SESSION_BARS


def test_ticker_alias_is_date_fenced():
    from closingbell.ingest import _apply_aliases
    df = pd.DataFrame({
        "ticker": ["FB", "FB", "META"],
        "session": [dt.date(2022, 5, 2), dt.date(2023, 5, 2), dt.date(2023, 5, 2)],
    })
    out = _apply_aliases(df)
    assert set(out["ticker"]) == {"META"}
    # The stale post-rename FB row is dropped, not renamed onto META.
    assert len(out) == 2
    assert sorted(out["session"]) == [dt.date(2022, 5, 2), dt.date(2023, 5, 2)]
