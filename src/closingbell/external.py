"""External reference series: daily bars, corporate actions, VIX.

The intraday feed is *unadjusted*, so two corporate-action effects would
otherwise contaminate the overnight return:

* **Splits.**  An unadjusted 10:1 split shows up as a -90% overnight return.
  These are mechanically removed.
* **Cash dividends.**  On the ex-date the price drops by roughly the dividend
  with no information content.  We flag these sessions and control for /
  exclude them rather than silently absorbing them into the result.

Daily bars from an independent vendor are also used to *cross-validate* the
intraday feed (see ``docs/data_sources.md``): if aggregated 5-minute bars did
not reproduce an independent daily OHLC we would not trust them.
"""
from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from pathlib import Path

import pandas as pd

from . import config as C

CHART = ("https://query1.finance.yahoo.com/v8/finance/chart/{sym}"
         "?interval=1d&period1={p1}&period2={p2}&events=div%2Csplit")
_UA = {"User-Agent": "Mozilla/5.0 (research; closing-bell-effect)"}


def _get_json(url: str, retries: int = 4, pause: float = 1.5) -> dict:
    last = None
    for i in range(retries):
        try:
            req = urllib.request.Request(url, headers=_UA)
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.load(r)
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            last = exc
            time.sleep(pause * (i + 1))
    raise RuntimeError(f"failed to fetch {url}: {last}")


def fetch_daily(symbol: str, start: str = C.SAMPLE_START,
                end: str = C.SAMPLE_END) -> dict[str, pd.DataFrame]:
    p1 = int(pd.Timestamp(start, tz="UTC").timestamp())
    p2 = int(pd.Timestamp(end, tz="UTC").timestamp()) + 86400
    raw = _get_json(CHART.format(sym=symbol, p1=p1, p2=p2))
    res = raw["chart"]["result"][0]
    q = res["indicators"]["quote"][0]
    idx = [pd.Timestamp(t, unit="s", tz="UTC").tz_convert(C.TZ).date() for t in res["timestamp"]]
    daily = pd.DataFrame({
        "session": idx, "ticker": symbol,
        "d_open": q["open"], "d_high": q["high"], "d_low": q["low"],
        "d_close": q["close"], "d_volume": q["volume"],
    })
    adj = res["indicators"].get("adjclose")
    if adj:
        daily["d_adjclose"] = adj[0]["adjclose"]
    daily = daily.dropna(subset=["d_close"]).reset_index(drop=True)

    ev = res.get("events", {})
    divs = pd.DataFrame([
        {"ticker": symbol,
         "session": pd.Timestamp(int(v["date"]), unit="s", tz="UTC").tz_convert(C.TZ).date(),
         "dividend": float(v["amount"])}
        for v in ev.get("dividends", {}).values()
    ])
    splits = pd.DataFrame([
        {"ticker": symbol,
         "session": pd.Timestamp(int(v["date"]), unit="s", tz="UTC").tz_convert(C.TZ).date(),
         "split_ratio": float(v["numerator"]) / float(v["denominator"])}
        for v in ev.get("splits", {}).values()
    ])
    return {"daily": daily, "dividends": divs, "splits": splits}


def build_external(symbols: list[str] | None = None,
                   start: str = C.SAMPLE_START, end: str = C.SAMPLE_END,
                   out_dir: Path = C.EXTERNAL) -> dict[str, pd.DataFrame]:
    symbols = symbols or C.UNIVERSE
    dailies, divs, splits = [], [], []
    for s in symbols:
        got = fetch_daily(s, start, end)
        dailies.append(got["daily"])
        if len(got["dividends"]):
            divs.append(got["dividends"])
        if len(got["splits"]):
            splits.append(got["splits"])
        time.sleep(0.4)

    daily = pd.concat(dailies, ignore_index=True)
    dividends = (pd.concat(divs, ignore_index=True) if divs
                 else pd.DataFrame(columns=["ticker", "session", "dividend"]))
    splt = (pd.concat(splits, ignore_index=True) if splits
            else pd.DataFrame(columns=["ticker", "session", "split_ratio"]))

    vix = fetch_daily("^VIX", start, end)["daily"].rename(columns={"d_close": "vix"})
    vix = vix[["session", "vix"]]

    daily.to_parquet(out_dir / "daily_bars.parquet", index=False)
    dividends.to_parquet(out_dir / "dividends.parquet", index=False)
    splt.to_parquet(out_dir / "splits.parquet", index=False)
    vix.to_parquet(out_dir / "vix.parquet", index=False)
    return {"daily": daily, "dividends": dividends, "splits": splt, "vix": vix}


def load_external(out_dir: Path = C.EXTERNAL) -> dict[str, pd.DataFrame]:
    return {name: pd.read_parquet(out_dir / f"{fn}.parquet") for name, fn in
            [("daily", "daily_bars"), ("dividends", "dividends"),
             ("splits", "splits"), ("vix", "vix")]}


if __name__ == "__main__":
    got = build_external()
    for k, v in got.items():
        print(k, v.shape)
