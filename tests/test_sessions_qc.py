"""Session quality control: missing data, integrity, exclusion accounting."""
from __future__ import annotations

import datetime as dt

import numpy as np
import pandas as pd
import pytest

from closingbell import config as C
from closingbell import sessions as sq
from closingbell.ingest import to_five_minute_bars
from tests.conftest import make_minutes


def _bars(days, schedule, ticker="TEST"):
    mins = pd.concat([make_minutes(d, ticker=ticker) for d in days], ignore_index=True)
    return to_five_minute_bars(mins, schedule)


def test_clean_session_is_usable_and_event_eligible(schedule):
    bars, auction = _bars([dt.date(2024, 6, 12)], schedule)
    qc = sq.session_quality(bars, auction, schedule)
    row = qc[qc["session"] == dt.date(2024, 6, 12)].iloc[0]
    assert row["observed_bars"] == C.FULL_SESSION_BARS
    assert row["expected_bars"] == C.FULL_SESSION_BARS
    assert row["missing_pct"] == 0.0
    assert row["usable"] and row["event_eligible"]
    assert row["exclusion_reason"] == ""
    assert row["has_auction"]


def test_a_trading_day_with_no_rows_is_reported_not_omitted(schedule):
    bars, auction = _bars([dt.date(2024, 6, 12)], schedule)
    qc = sq.session_quality(bars, auction, schedule)
    # Every session on the exchange calendar appears for the ticker.
    assert len(qc) == len(schedule)
    absent = qc[qc["session"] == dt.date(2024, 6, 13)].iloc[0]
    assert absent["observed_bars"] == 0
    assert absent["exclusion_reason"] == "no_data"
    assert not absent["usable"]


def test_a_holiday_never_appears_as_a_missing_session(schedule):
    bars, auction = _bars([dt.date(2024, 6, 12)], schedule)
    qc = sq.session_quality(bars, auction, schedule)
    for holiday in [dt.date(2024, 7, 4), dt.date(2024, 12, 25), dt.date(2024, 11, 28)]:
        assert holiday not in set(qc["session"])


def test_early_close_expects_42_bars_not_78(schedule):
    mins = make_minutes(dt.date(2024, 7, 3), close_time=dt.time(13, 0))
    bars, auction = to_five_minute_bars(mins, schedule)
    qc = sq.session_quality(bars, auction, schedule)
    row = qc[qc["session"] == dt.date(2024, 7, 3)].iloc[0]
    assert row["is_early_close"]
    assert row["expected_bars"] == C.EARLY_SESSION_BARS
    assert row["observed_bars"] == C.EARLY_SESSION_BARS
    assert row["missing_pct"] == 0.0                 # complete, not 46% missing
    assert row["usable"]
    assert not row["event_eligible"]
    assert row["event_exclusion_reason"] == "early_close_no_closing_window"


def test_heavily_incomplete_session_is_excluded(schedule):
    mins = make_minutes(dt.date(2024, 6, 12), include_extended=False)
    thinned = mins[mins["ts_et"].dt.hour < 12]        # lose the afternoon
    bars, auction = to_five_minute_bars(thinned, schedule)
    qc = sq.session_quality(bars, auction, schedule)
    row = qc[qc["session"] == dt.date(2024, 6, 12)].iloc[0]
    assert row["missing_pct"] > sq.MAX_MISSING_FRAC
    assert row["exclusion_reason"] == "incomplete_session"
    assert not row["usable"]


def test_a_small_gap_is_tolerated(schedule):
    mins = make_minutes(dt.date(2024, 6, 12), include_extended=False)
    thinned = mins[~mins["ts_et"].dt.strftime("%H:%M").str.startswith("11:0")]
    bars, auction = to_five_minute_bars(thinned, schedule)
    qc = sq.session_quality(bars, auction, schedule)
    row = qc[qc["session"] == dt.date(2024, 6, 12)].iloc[0]
    assert 0 < row["missing_pct"] <= sq.MAX_MISSING_FRAC
    assert row["usable"]


def test_missing_closing_slot_blocks_event_eligibility_only(schedule):
    mins = make_minutes(dt.date(2024, 6, 12), include_extended=False)
    thinned = mins[~mins["ts_et"].dt.strftime("%H:%M").str.startswith("15:5")]
    bars, auction = to_five_minute_bars(thinned, schedule)
    qc = sq.session_quality(bars, auction, schedule)
    row = qc[qc["session"] == dt.date(2024, 6, 12)].iloc[0]
    assert row["usable"]
    assert not row["event_eligible"]
    assert row["event_exclusion_reason"] == "missing_closing_slot"


def test_broken_bars_are_caught(schedule):
    bars, auction = _bars([dt.date(2024, 6, 12)], schedule)
    bars.loc[10, "high"] = bars.loc[10, "low"] - 1.0
    qc = sq.session_quality(bars, auction, schedule)
    row = qc[qc["session"] == dt.date(2024, 6, 12)].iloc[0]
    assert row["bad_bars"] >= 1
    assert row["exclusion_reason"] == "bar_integrity"
    assert not row["usable"]


def test_dst_and_early_close_reports_are_populated(schedule):
    days = [dt.date(2024, 3, 11), dt.date(2024, 11, 4), dt.date(2024, 6, 12)]
    mins = pd.concat([make_minutes(d) for d in days], ignore_index=True)
    mins = pd.concat([mins, make_minutes(dt.date(2024, 7, 3), close_time=dt.time(13, 0))],
                     ignore_index=True)
    bars, auction = to_five_minute_bars(mins, schedule)
    qc = sq.session_quality(bars, auction, schedule)

    dst = sq.dst_check(qc)
    assert set(dst["dst_transition"]) == {"spring_forward", "fall_back"}
    for _, r in dst.iterrows():
        assert r["expected_bars"] == C.FULL_SESSION_BARS

    early = sq.early_close_check(qc)
    assert (early["expected_bars"] == C.EARLY_SESSION_BARS).all()
    assert (early["bars_after_1300"] == 0).all()      # nothing at 15:25 on an early close


def test_exclusion_breakdown_accounts_for_every_dropped_session(schedule):
    bars, auction = _bars([dt.date(2024, 6, 12), dt.date(2024, 6, 13)], schedule)
    qc = sq.session_quality(bars, auction, schedule)
    br = sq.exclusion_breakdown(qc)
    assert br["sessions"].sum() == int((~qc["usable"]).sum())


def test_quality_summary_is_internally_consistent(schedule):
    bars, auction = _bars([dt.date(2024, 6, 12), dt.date(2024, 6, 13)], schedule)
    qc = sq.session_quality(bars, auction, schedule)
    summ = sq.quality_summary(qc).iloc[0]
    assert summ["calendar_sessions"] == len(schedule)
    assert summ["sessions_with_data"] == 2
    assert summ["usable_sessions"] == 2
    assert 0 < summ["missing_bar_pct"] < 1
