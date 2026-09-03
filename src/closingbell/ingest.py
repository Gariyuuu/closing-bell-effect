"""Ingestion of genuine 1-minute consolidated U.S. equity bars -> 5-minute RTH bars.

Source
------
Hugging Face dataset ``mito0o852/OHLCV-1m``: monthly parquet files of
consolidated 1-minute OHLCV bars for U.S. listed symbols, timestamped in UTC,
covering pre-market, regular hours and post-market.

The raw feed is *unadjusted* (prices are as-traded), which is why
``corporate_actions.py`` exists.  See ``docs/data_sources.md`` for the
provenance checks that were run against an independent daily vendor.

What this module produces
-------------------------
``data/interim/bars5m_YYYY-MM.parquet``
    5-minute regular-trading-hours bars, ``America/New_York``, one row per
    (ticker, session, slot).  A slot is labelled by its LEFT edge.
``data/interim/auction_YYYY-MM.parquet``
    The closing-auction minute bar (the 1-minute bar stamped at the session's
    official close time), carried separately because it is not a regular
    5-minute slot and because its volume must be attributable to the close.
"""
from __future__ import annotations

import datetime as dt
import shutil
import time
import urllib.request
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow.compute as pc
import pyarrow.parquet as pq

from . import config as C
from . import calendar_utils as cal

HF_BASE = ("https://huggingface.co/datasets/mito0o852/OHLCV-1m/resolve/main/data/"
           "ohlcv_{month}.parquet")

#: Symbols requested from the raw feed (includes historical aliases).
REQUEST_SYMBOLS = sorted(set(C.UNIVERSE) | set(C.TICKER_ALIASES))

#: Facebook -> Meta ticker change.  Facebook traded as FB through this session
#: and as META from the next one.  Crucially, the symbol "META" was in use by an
#: unrelated issuer *before* the rename, so those earlier META rows are a
#: different company and must be discarded rather than merged.
FB_LAST_SESSION = dt.date(2022, 6, 8)


def months_in_range(start: str = C.SAMPLE_START, end: str = C.SAMPLE_END) -> list[str]:
    idx = pd.period_range(pd.Timestamp(start), pd.Timestamp(end), freq="M")
    return [p.strftime("%Y-%m") for p in idx]


def download_month(month: str, dest_dir: Path = C.RAW, timeout: int = 900,
                   retries: int = 4) -> Path:
    """Fetch one monthly file, verifying that the whole file arrived.

    Large transfers over a flaky link truncate silently, which surfaces much
    later as an unreadable parquet footer.  The declared ``Content-Length`` is
    checked against the bytes written and the transfer is retried, so a short
    read can never be mistaken for a month with less data in it.
    """
    dest = dest_dir / f"ohlcv_{month}.parquet"
    if dest.exists() and dest.stat().st_size > 0:
        return dest
    url = HF_BASE.format(month=month)
    tmp = dest.with_suffix(".part")
    last = None
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(url, timeout=timeout) as r:
                expected = r.headers.get("Content-Length")
                expected = int(expected) if expected is not None else None
                with open(tmp, "wb") as f:
                    shutil.copyfileobj(r, f, length=1 << 20)
            got = tmp.stat().st_size
            if expected is not None and got != expected:
                raise OSError(f"truncated download: {got} of {expected} bytes")
            tmp.rename(dest)
            return dest
        except Exception as exc:  # noqa: BLE001 - retry any transport failure
            last = exc
            tmp.unlink(missing_ok=True)
            time.sleep(3 * (attempt + 1))
    raise RuntimeError(f"download failed for {month} after {retries} attempts: {last}")


def _apply_aliases(df: pd.DataFrame) -> pd.DataFrame:
    """Map historical tickers onto their modern symbol, date-fenced both ways.

    Two rows must be removed, not renamed:

    * ``FB`` after the rename session -- Facebook no longer reports under it.
    * ``META`` on or before the rename session -- that symbol belonged to an
      unrelated issuer at the time.  Keeping those rows silently interleaves a
      $15 stock with a $370 one inside the same bars.
    """
    stale_fb = df["ticker"].eq("FB") & (df["session"] > FB_LAST_SESSION)
    stale_meta = df["ticker"].eq("META") & (df["session"] <= FB_LAST_SESSION)
    df = df.loc[~(stale_fb | stale_meta)].copy()
    df.loc[df["ticker"].eq("FB"), "ticker"] = "META"
    return df


def load_month_minutes(path: Path) -> pd.DataFrame:
    """Read one raw monthly file, keep our symbols, localise to New York."""
    tbl = pq.read_table(path, filters=[("ticker", "in", REQUEST_SYMBOLS)])
    df = tbl.to_pandas()
    if df.empty:
        return df
    ts = pd.to_datetime(df["timestamp"], utc=True)
    df["ts_et"] = ts.dt.tz_convert(C.TZ)
    df["session"] = df["ts_et"].dt.date
    df = _apply_aliases(df)
    return df


def to_five_minute_bars(minutes: pd.DataFrame, schedule: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Aggregate 1-minute bars into 5-minute regular-hours bars.

    Regular hours are taken per session from the exchange calendar, so an
    early-close session is truncated at *its* close (13:00) rather than at a
    hard-coded 16:00.  The auction minute -- the bar stamped exactly at the
    session close -- is split out into its own frame.
    """
    if minutes.empty:
        return minutes, minutes

    m = minutes[minutes["session"].isin(schedule.index)].copy()
    if m.empty:
        return m, m

    sess_close = m["session"].map(schedule["close_time"])
    tod = m["ts_et"].dt.time

    in_rth = (tod >= C.RTH_OPEN) & (tod < sess_close)
    is_auction = tod == sess_close

    auction = m.loc[is_auction, ["ticker", "session", "ts_et", "open", "high",
                                 "low", "close", "volume"]].copy()
    # The official closing print is the first trade of the auction minute.
    auction = (auction.sort_values("ts_et")
                      .groupby(["ticker", "session"], as_index=False)
                      .agg(auction_ts=("ts_et", "first"),
                           auction_price=("open", "first"),
                           auction_volume=("volume", "sum")))

    rth = m.loc[in_rth].copy()
    if rth.empty:
        return rth, auction

    floor = rth["ts_et"].dt.floor(f"{C.BAR_MINUTES}min")
    rth["slot_ts"] = floor
    rth["slot"] = floor.dt.strftime("%H:%M")
    rth = rth.sort_values(["ticker", "ts_et"])
    bars = (rth.groupby(["ticker", "session", "slot"], as_index=False)
               .agg(slot_ts=("slot_ts", "first"),
                    open=("open", "first"),
                    high=("high", "max"),
                    low=("low", "min"),
                    close=("close", "last"),
                    volume=("volume", "sum"),
                    n_minutes=("close", "size")))
    return bars, auction


def ingest_month(month: str, schedule: pd.DataFrame, keep_raw: bool = False,
                 out_dir: Path = C.INTERIM) -> dict:
    bars_path = out_dir / f"bars5m_{month}.parquet"
    auc_path = out_dir / f"auction_{month}.parquet"
    if bars_path.exists() and auc_path.exists():
        return {"month": month, "status": "cached"}

    raw = download_month(month)
    try:
        minutes = load_month_minutes(raw)
    except Exception:
        # A cached raw file that will not parse is discarded and re-fetched once.
        raw.unlink(missing_ok=True)
        raw = download_month(month)
        minutes = load_month_minutes(raw)
    bars, auction = to_five_minute_bars(minutes, schedule)
    bars.to_parquet(bars_path, index=False)
    auction.to_parquet(auc_path, index=False)
    if not keep_raw:
        raw.unlink(missing_ok=True)
    return {"month": month, "status": "ok", "bars": len(bars),
            "auctions": len(auction), "tickers": int(bars["ticker"].nunique()) if len(bars) else 0}


def build_panel(out_path: Path | None = None) -> pd.DataFrame:
    """Concatenate every ingested month into the analysis-ready 5-minute panel."""
    out_path = out_path or (C.PROCESSED / "bars5m.parquet")
    files = sorted(C.INTERIM.glob("bars5m_*.parquet"))
    if not files:
        raise FileNotFoundError("no ingested months found; run the ingest first")
    bars = pd.concat([pd.read_parquet(f) for f in files], ignore_index=True)
    bars = bars.sort_values(["ticker", "session", "slot"]).reset_index(drop=True)
    bars.to_parquet(out_path, index=False)

    auc = pd.concat([pd.read_parquet(f) for f in sorted(C.INTERIM.glob("auction_*.parquet"))],
                    ignore_index=True)
    auc = auc.sort_values(["ticker", "session"]).reset_index(drop=True)
    auc.to_parquet(C.PROCESSED / "auction.parquet", index=False)
    return bars


def main(argv=None) -> int:
    import argparse
    p = argparse.ArgumentParser(description="Ingest 5-minute RTH bars.")
    p.add_argument("--start", default=C.SAMPLE_START)
    p.add_argument("--end", default=C.SAMPLE_END)
    p.add_argument("--keep-raw", action="store_true")
    p.add_argument("--workers", type=int, default=1)
    a = p.parse_args(argv)

    schedule = cal.session_schedule(a.start, a.end)
    months = months_in_range(a.start, a.end)

    def _one(month: str) -> dict:
        try:
            return ingest_month(month, schedule, keep_raw=a.keep_raw)
        except Exception as exc:  # noqa: BLE001 - report and continue
            return {"month": month, "status": f"FAILED {type(exc).__name__}: {exc}"}

    if a.workers > 1:
        from concurrent.futures import ThreadPoolExecutor
        with ThreadPoolExecutor(max_workers=a.workers) as ex:
            for info in ex.map(_one, months):
                print(f"[ingest] {info}", flush=True)
    else:
        for month in months:
            print(f"[ingest] {_one(month)}", flush=True)
    build_panel()
    print("[ingest] panel written", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
