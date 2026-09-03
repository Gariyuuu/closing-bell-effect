"""Central configuration: universe, paths, session constants."""
from __future__ import annotations

import datetime as dt
from pathlib import Path

import pandas as pd

# --------------------------------------------------------------------------
# Paths
# --------------------------------------------------------------------------
ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data"
RAW = DATA / "raw"
INTERIM = DATA / "interim"
PROCESSED = DATA / "processed"
EXTERNAL = DATA / "external"
RESULTS = ROOT / "results"
FIGURES = RESULTS / "figures"
TABLES = RESULTS / "tables"

for _p in (RAW, INTERIM, PROCESSED, EXTERNAL, FIGURES, TABLES):
    _p.mkdir(parents=True, exist_ok=True)

# --------------------------------------------------------------------------
# Universe
# --------------------------------------------------------------------------
ETFS = ["SPY", "QQQ", "IWM"]
STOCKS = ["AAPL", "MSFT", "NVDA", "AMZN", "META", "GOOGL", "JPM", "XOM", "TSLA"]
UNIVERSE = ETFS + STOCKS

#: Historical ticker aliases. Facebook traded as FB until 2022-06-09.
TICKER_ALIASES = {"FB": "META"}

#: Symbol used as the market factor in controls / regime splits.
MARKET_PROXY = "SPY"

# --------------------------------------------------------------------------
# Sample window
# --------------------------------------------------------------------------
SAMPLE_START = "2021-01-01"
SAMPLE_END = "2026-03-31"

# --------------------------------------------------------------------------
# Session constants  (all times are wall-clock America/New_York)
# --------------------------------------------------------------------------
TZ = "America/New_York"
EXCHANGE = "XNYS"

RTH_OPEN = dt.time(9, 30)
RTH_CLOSE = dt.time(16, 0)
EARLY_CLOSE = dt.time(13, 0)

BAR_MINUTES = 5
#: Number of 5-minute bars in a full 09:30-16:00 session.
FULL_SESSION_BARS = 78
#: Number of 5-minute bars in a 09:30-13:00 early-close session.
EARLY_SESSION_BARS = 42

#: Left edge of the final-30-minute window.
CLOSE30_START = dt.time(15, 30)
#: Left edge of the final-60-minute window.
CLOSE60_START = dt.time(15, 0)
#: Right edge of the first-30-minutes-of-trading window.
OPEN30_END = dt.time(10, 0)

# --------------------------------------------------------------------------
# Estimation constants
# --------------------------------------------------------------------------
#: Trailing window (in sessions) used for every historical normalisation.
#: The current session is ALWAYS excluded -- see docs/data_leakage_audit.md.
TRAILING_WINDOW = 60
#: Minimum trailing observations required before a normalised value is emitted.
MIN_TRAILING_OBS = 40

#: Primary tail definition for "extreme" closing pressure.
TAIL_PCT = 0.05
#: Robustness tail definition.
TAIL_PCT_ROBUST = 0.01

#: Abnormal-volume cut: AVOL percentile above which closing volume is "high".
AVOL_HIGH_PCTILE = 0.70

#: Bootstrap replications for confidence intervals.
N_BOOT = 10_000
BOOT_SEED = 20240930

# --------------------------------------------------------------------------
# Time-of-day placebo windows  (30 minutes each, non-overlapping)
# --------------------------------------------------------------------------
TOD_WINDOWS = {
    "morning": (dt.time(9, 30), dt.time(10, 0)),
    "midday": (dt.time(12, 0), dt.time(12, 30)),
    "close": (dt.time(15, 30), dt.time(16, 0)),
}

#: The window each placebo window is tested as a predictor of.
TOD_FOLLOWING = {
    "morning": ("morning_next", dt.time(10, 0), dt.time(10, 30)),
    "midday": ("midday_next", dt.time(12, 30), dt.time(13, 0)),
    "close": ("overnight", None, None),
}


def slot_label(t: dt.time) -> str:
    return t.strftime("%H:%M")


def five_minute_slots() -> list[str]:
    """The 78 canonical 5-minute slot labels of a full RTH session.

    A slot is labelled by its *left* (opening) edge: '09:30' spans
    09:30:00-09:34:59.  '15:55' is the final regular-hours slot.
    """
    idx = pd.date_range("2020-01-02 09:30", "2020-01-02 15:55", freq="5min")
    return [t.strftime("%H:%M") for t in idx]
