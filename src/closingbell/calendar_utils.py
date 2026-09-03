"""U.S. equity session calendar helpers.

Everything downstream depends on knowing, for each date, whether the market was
open, and if so at what wall-clock time it closed.  We take that from the
``exchange_calendars`` XNYS calendar rather than assuming 16:00 always existed.
"""
from __future__ import annotations

import datetime as dt
import functools

import exchange_calendars as xc
import numpy as np
import pandas as pd

from . import config as C


@functools.lru_cache(maxsize=4)
def get_calendar(name: str = C.EXCHANGE) -> xc.ExchangeCalendar:
    return xc.get_calendar(name)


def session_schedule(start: str = C.SAMPLE_START, end: str = C.SAMPLE_END,
                     name: str = C.EXCHANGE) -> pd.DataFrame:
    """Per-session open/close in America/New_York plus session classification.

    Returns a frame indexed by ``session`` (a ``datetime.date``) with columns:

    ``open_et``, ``close_et``      -- tz-aware session boundaries
    ``session_minutes``            -- regular-hours minutes
    ``is_early_close``             -- close earlier than 16:00 ET
    ``expected_bars``              -- number of 5-minute bars the session should hold
    ``utc_offset_hours``           -- -5 (EST) or -4 (EDT)
    ``is_dst``                     -- True when the session is on daylight time
    ``dst_transition``             -- 'spring_forward' / 'fall_back' / None
    """
    cal = get_calendar(name)
    sched = cal.schedule.loc[start:end].copy()
    open_et = sched["open"].dt.tz_convert(C.TZ)
    close_et = sched["close"].dt.tz_convert(C.TZ)

    out = pd.DataFrame(index=pd.Index([d.date() for d in sched.index], name="session"))
    # ``.values`` on a tz-aware series yields naive UTC and would silently drop the
    # timezone, so the boundaries are re-localised explicitly.
    out["open_et"] = pd.Series(pd.DatetimeIndex(open_et), index=out.index)
    out["close_et"] = pd.Series(pd.DatetimeIndex(close_et), index=out.index)
    minutes = (out["close_et"] - out["open_et"]) / pd.Timedelta(minutes=1)
    out["session_minutes"] = minutes.astype(int)
    out["close_time"] = [t.time() for t in out["close_et"]]
    out["is_early_close"] = out["close_time"] != C.RTH_CLOSE
    out["expected_bars"] = (out["session_minutes"] // C.BAR_MINUTES).astype(int)
    offs = np.array([t.utcoffset().total_seconds() / 3600.0 for t in out["open_et"]])
    out["utc_offset_hours"] = offs
    out["is_dst"] = offs == -4.0

    # A DST transition *session* is the first session on the new offset.
    trans = pd.Series(None, index=out.index, dtype=object)
    prev = out["utc_offset_hours"].shift(1)
    trans[(prev == -5.0) & (out["utc_offset_hours"] == -4.0)] = "spring_forward"
    trans[(prev == -4.0) & (out["utc_offset_hours"] == -5.0)] = "fall_back"
    out["dst_transition"] = trans
    return out


def expected_slots(close_time: dt.time) -> list[str]:
    """Canonical 5-minute slot labels for a session ending at ``close_time``."""
    all_slots = C.five_minute_slots()
    cutoff = close_time.hour * 60 + close_time.minute
    return [s for s in all_slots
            if int(s[:2]) * 60 + int(s[3:]) < cutoff]


def holidays(start: str = C.SAMPLE_START, end: str = C.SAMPLE_END,
             name: str = C.EXCHANGE) -> pd.DatetimeIndex:
    """Weekdays inside the range on which the exchange was closed."""
    cal = get_calendar(name)
    sessions = pd.DatetimeIndex([pd.Timestamp(d) for d in cal.sessions_in_range(start, end)])
    weekdays = pd.bdate_range(start, end)
    return weekdays.difference(sessions)


def next_session_map(sessions: list[dt.date]) -> dict:
    """Map each session to the session that follows it on the exchange calendar.

    Used for overnight / next-day matching.  Built from the *calendar*, never
    from a simple ``shift(-1)`` over whatever rows happen to be present, so a
    ticker with a missing session cannot be silently matched across a gap.
    """
    s = sorted(sessions)
    return {a: b for a, b in zip(s[:-1], s[1:])}
