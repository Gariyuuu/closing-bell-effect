"""Calendar, timezone and DST behaviour."""
from __future__ import annotations

import datetime as dt

import pandas as pd
import pytest

from closingbell import calendar_utils as cal
from closingbell import config as C


def test_timezone_is_new_york_not_utc(schedule):
    s = schedule.loc[dt.date(2024, 6, 12)]
    assert str(s["open_et"].tz) == C.TZ
    assert s["open_et"].time() == dt.time(9, 30)
    assert s["close_et"].time() == dt.time(16, 0)


def test_utc_timestamps_localise_to_the_right_wall_clock():
    """13:30 UTC is 09:30 in summer and 08:30 in winter -- the offset must move."""
    summer = pd.Timestamp("2024-06-12 13:30", tz="UTC").tz_convert(C.TZ)
    winter = pd.Timestamp("2024-01-12 13:30", tz="UTC").tz_convert(C.TZ)
    assert summer.time() == dt.time(9, 30)
    assert winter.time() == dt.time(8, 30)
    assert pd.Timestamp("2024-01-12 14:30", tz="UTC").tz_convert(C.TZ).time() == dt.time(9, 30)


def test_dst_offsets_are_detected(schedule):
    assert schedule.loc[dt.date(2024, 6, 12), "utc_offset_hours"] == -4.0
    assert schedule.loc[dt.date(2024, 1, 12), "utc_offset_hours"] == -5.0
    assert schedule.loc[dt.date(2024, 6, 12), "is_dst"]
    assert not schedule.loc[dt.date(2024, 1, 12), "is_dst"]


def test_dst_transition_sessions_are_flagged(schedule):
    trans = schedule[schedule["dst_transition"].notna()]
    assert trans.loc[dt.date(2024, 3, 11), "dst_transition"] == "spring_forward"
    assert trans.loc[dt.date(2024, 11, 4), "dst_transition"] == "fall_back"


def test_dst_transition_sessions_still_have_a_full_length_day(schedule):
    """The clocks change on Sunday; Monday is still 390 regular-hours minutes."""
    for day in [dt.date(2024, 3, 11), dt.date(2024, 11, 4)]:
        assert schedule.loc[day, "session_minutes"] == 390
        assert schedule.loc[day, "expected_bars"] == C.FULL_SESSION_BARS
        assert not schedule.loc[day, "is_early_close"]


def test_holidays_are_absent_from_the_schedule(schedule):
    for holiday in [dt.date(2024, 1, 1), dt.date(2024, 7, 4), dt.date(2024, 11, 28),
                    dt.date(2024, 12, 25), dt.date(2024, 6, 19), dt.date(2024, 3, 29)]:
        assert holiday not in schedule.index

    hol = cal.holidays("2024-01-01", "2024-12-31")
    assert pd.Timestamp("2024-11-28") in hol      # Thanksgiving
    assert pd.Timestamp("2024-03-29") in hol      # Good Friday


def test_early_closes_are_identified_with_the_right_close_time(schedule):
    early = schedule[schedule["is_early_close"]]
    assert dt.date(2024, 7, 3) in early.index
    assert dt.date(2024, 11, 29) in early.index
    assert dt.date(2024, 12, 24) in early.index
    for day in early.index:
        assert schedule.loc[day, "close_time"] == C.EARLY_CLOSE
        assert schedule.loc[day, "expected_bars"] == C.EARLY_SESSION_BARS


def test_a_full_session_is_never_treated_as_early(schedule):
    normal = schedule[~schedule["is_early_close"]]
    assert (normal["expected_bars"] == C.FULL_SESSION_BARS).all()
    assert (normal["session_minutes"] == 390).all()


def test_expected_slots_stop_at_the_actual_close():
    full = cal.expected_slots(dt.time(16, 0))
    early = cal.expected_slots(dt.time(13, 0))
    assert len(full) == C.FULL_SESSION_BARS and full[-1] == "15:55"
    assert len(early) == C.EARLY_SESSION_BARS and early[-1] == "12:55"
    assert "13:00" not in early and "15:30" not in early


def test_next_session_map_skips_weekends_and_holidays(schedule):
    nxt = cal.next_session_map(list(schedule.index))
    assert nxt[dt.date(2024, 7, 3)] == dt.date(2024, 7, 5)      # July 4th holiday
    assert nxt[dt.date(2024, 11, 27)] == dt.date(2024, 11, 29)  # Thanksgiving
    assert nxt[dt.date(2024, 6, 14)] == dt.date(2024, 6, 17)    # Friday -> Monday
