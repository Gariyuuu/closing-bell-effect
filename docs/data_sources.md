# Data sources and provenance

## Intraday bars

**Source.** Hugging Face dataset [`mito0o852/OHLCV-1m`](https://huggingface.co/datasets/mito0o852/OHLCV-1m)
— monthly parquet files of 1-minute consolidated OHLCV bars for U.S. listed
symbols, timestamped in UTC, covering 04:00–20:00 ET.

**What we take.** 63 monthly files (2021-01 through 2026-03), filtered to the
twelve-name universe, restricted to regular trading hours, and aggregated to
5-minute bars labelled by their left edge. Downloads are size-verified against
`Content-Length`; a truncated transfer is retried rather than silently parsed as
a month with less data in it.

**Result.** 1,220,267 5-minute regular-hours bars across 1,316 exchange sessions.

### Why this source was used

Multi-year 5-minute U.S. equity history is not freely available from the obvious
places. Yahoo's chart API refuses intraday intervals older than 60 days
(`"5m data not available ... must be within the last 60 days"`); Alpaca, Polygon,
Alpha Vantage, Twelve Data and FMP all require credentials. This dataset is the
only keyless source located that carries several years of intraday bars for the
whole requested universe, so it was accepted only after the validation below.

### Known characteristics

| Property | Value |
|---|---|
| Timestamps | UTC in the file, converted to `America/New_York` |
| Coverage | pre-market, regular hours, post-market |
| Adjustment | **unadjusted** (as-traded prices and share counts) |
| Bar sparsity | bars exist only where trades occurred |
| Regular-hours completeness | 99.5% of expected bars present |

Because prices are unadjusted, splits and cash dividends are corrected
explicitly — see [Corporate actions](#corporate-actions).

## Validation against an independent vendor

The 5-minute panel is aggregated back to daily OHLCV and compared with daily bars
fetched separately from Yahoo Finance. Vendor prices are split-adjusted while the
intraday feed is raw, so vendor prices are multiplied by the cumulative ratio of
every split with an ex-date after the session (and vendor volume divided by it).

Agreement, per ticker, over ~1,300 sessions each
(`results/tables/data_crossvalidation.csv`):

| Measure | Result |
|---|---|
| Median absolute close error | 0.0–1.0 bp |
| 99th percentile close error | 5–25 bp |
| Sessions disagreeing by more than 50 bp | 2–5 per ticker |
| Regular-hours + auction volume ÷ vendor daily volume | 0.86–0.95 |

The volume ratio is *expected* to sit below one: vendor daily volume includes
pre- and post-market trading that the regular-hours panel excludes by
construction. The remaining 5–14% is that extended-hours activity.

Prices that match an unrelated vendor to well under a basis point, and volume
that reconciles to the fraction extended-hours trading accounts for, is what
genuine consolidated tape data looks like.

## Problems found and how they were handled

Three real defects surfaced during validation. All three are caught by automated
checks that remain in the pipeline, not by one-off patches.

### 1. Symbol reuse: `META` before the Facebook rename

Facebook traded as `FB` until 2022-06-08 and as `META` afterwards — but the
symbol `META` was already in use by an unrelated issuer trading near \$15 while
Facebook traded near \$370. Naively renaming `FB → META` interleaved the two
price series inside the same bars, producing 5-minute bars whose high and low
came from different companies and overnight returns of +2,400%.

*Handling.* `ingest._apply_aliases` date-fences the alias in **both**
directions: `FB` rows after the rename are dropped, and `META` rows on or before
it are dropped. `sessions.MAX_SESSION_RANGE` independently rejects any session
whose high/low span exceeds 50%, which catches this class of contamination
generically without knowing which symbol was reused.

### 2. Erroneous prints

Two sessions carried bad ticks: XOM on 2023-01-24 (the NYSE opening-auction
error, whose trades were later busted) and a stray SPY low on 2022-01-25. The
empirical gap is wide — the three worst bars span 18–28% within five minutes,
while the widest genuine bar in the sample, the 2025-04-07 reversal, spans 9.6%.

*Handling.* `sessions.MAX_BAR_RANGE = 0.15` sits inside that gap; affected
sessions are excluded with reason `erroneous_print` (2 ticker-sessions of 15,792).

### 3. Missing closing auctions

For XOM between mid-2021 and mid-2024 the bar stamped at 16:00 contains a stray
one-share print rather than the closing auction. Taking its price as the official
close would place a meaningless tick at the end of the closing window, and
counting its volume as auction volume would understate closing activity by orders
of magnitude.

*Handling.* `features.MIN_AUCTION_SHARE = 0.005` requires the closing bar to be
at least 0.5% of regular-hours volume before it is accepted as the auction. Real
auctions in this sample run 1.5–20% of regular-hours volume, so the floor is far
below any genuine auction and far above any stray print. Rejected sessions fall
back to the last regular-hours trade as the close.

## Exchange calendar

`exchange_calendars` XNYS. Over the sample: 1,316 sessions, 10 early closes
(all 13:00 ET), and holidays absent by construction. Daylight-saving transitions
are identified from the UTC offset of each session's open.

## Corporate actions

Splits and cash dividends come from the same daily endpoint as the validation
bars. Over the sample there are 5 splits (NVDA 4:1 and 10:1, AMZN 20:1,
GOOGL 20:1, TSLA 3:1) and 186 dividend events.

- **Splits** are mechanical: an unadjusted 10:1 split reads as a −90% overnight
  return. Corrected in `features.add_next_session_links`.
- **Dividends** drop the price on the ex-date with no information content. The
  dividend is added back, and `overnight_corp_action` flags every affected
  session so the whole set can be excluded as robustness
  (`results/tables/regression_ex_corp_actions.csv`).

## Reference series

`^VIX` daily closes, from the same endpoint, used only for regime splits. The VIX
attached to a session is that session's close, which is known by 16:00 that day.

## What is deliberately absent

No FOMC calendar. Reproducing one would mean hard-coding dates this repository
cannot verify from any data it ships, and a mislabelled event calendar would
silently corrupt the comparison. Monthly option expiration *is* included because
it is a rule (third Friday, rolled back when that Friday is a holiday) rather
than a list.

## Reproducing

```bash
make data       # ~25 min, ~20 GB transferred, raw files deleted as they are consumed
make pipeline   # ~6 min
```

Raw monthly files are deleted after each month is processed; peak disk use is one
file (~400 MB) per worker. `data/` is gitignored: this repository ships code and
results, not redistributed vendor data.
