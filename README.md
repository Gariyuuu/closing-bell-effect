# The Closing Bell Effect

**Intraday Liquidity, Volatility, and Overnight Persistence Near the Market Close**

Using 1.22 million real 5-minute bars across 12 liquid U.S. equities and ETFs,
this study asks whether unusually strong moves near the closing bell persist
overnight — and whether abnormal closing volume makes them more informative.

> ### Mostly no.
> Strong upward closes behave like ordinary positive overnight drift, abnormal
> closing volume adds little predictive information, and the closing window's
> predictive coefficient is statistically indistinguishable from midday.

![Is the close special? Closing window versus morning and midday placebo windows](results/figures/fig09_time_of_day_comparison.png)

**[Read the full report →](report/report.md)**

---

## 1. The close is busy. It is not uniquely predictive.

The figure above is the study's central falsification. Three non-overlapping
30-minute windows, each standardised within its own slot, each tested against the
period that immediately follows it:

| Window | Predicts | Standardised β | 95% CI | t | n |
|---|---|---:|---|---:|---:|
| 09:30–10:00 | 10:00–10:30 | +0.005 | [−0.024, +0.034] | 0.34 | 15,144 |
| 12:00–12:30 | 12:30–13:00 | **−0.050** | [−0.107, +0.007] | −1.74 | 15,136 |
| **15:30–16:00** | **overnight** | **−0.053** | [−0.092, −0.015] | −2.70 | 14,999 |

The closing coefficient is the only one significant on its own — and it is
**statistically indistinguishable from the midday coefficient**, whose point
estimate is −0.050 against the close's −0.053. The intervals overlap almost
entirely; the close's advantage is a tighter standard error, not a larger effect.

A reversal tendency of the same magnitude sits in the middle of the day, where
there is no auction, no index rebalancing, no end-of-day mark and no overnight
risk. Calling this a "closing bell effect" would attribute to the close something
the midday session does just as much of.

## 2. Zero is the wrong benchmark

U.S. equities carry a positive unconditional overnight drift. Across all 14,958
eligible sessions the mean overnight return is **+4.81 bp**, and 54% of overnight
returns are positive.

Every conditional overnight mean in this study is therefore reported as an
**excess over that drift**, not against zero. Without this, an ordinary +7 bp
overnight return following a strong up close reads as "persistence" when it is
simply what an arbitrary session already earns.

The same correction applies to directional persistence. A naive 50% coin-flip
reference makes ordinary market drift look predictively meaningful: with 54% of
overnight returns positive, an up close "persists" 54% of the time under the null
and a down close only 46% of the time. Benchmarked properly, realised persistence
sits **below** the drift-implied rate in every decile of closing pressure.

![Persistence against the drift-implied benchmark](results/figures/fig07_persistence_by_decile.png)

## 3. The asymmetry: down closes partially reverse, up closes do nothing

Extreme closing pressure is the top or bottom 5% of each ticker's own trailing
distribution — 1,974 events, mean absolute closing move 77 bp.

| Direction | Closing volume | n | Mean close₃₀ | Mean overnight | **Excess over drift** | 95% CI | p |
|---|---|---:|---:|---:|---:|---|---:|
| *baseline (all eligible)* | — | 14,958 | −0.2 bp | **+4.81 bp** | — | — | — |
| strong up | high | 625 | +83.8 bp | +7.21 bp | +2.41 bp | [−17.0, +22.1] | 0.81 |
| strong up | ordinary | 391 | +58.8 bp | +2.87 bp | −1.94 bp | [−17.6, +13.6] | 0.79 |
| **strong down** | **high** | 611 | −85.5 bp | **+29.34 bp** | **+24.53 bp** | [+2.8, +45.5] | **0.027** |
| strong down | ordinary | 347 | −69.6 bp | +18.01 bp | +13.20 bp | [−7.3, +33.0] | 0.21 |

**Strong up closes are uninformative.** Both cells sit within 3 bp of the
unconditional drift with intervals spanning zero. An 84 bp surge into the close
tells you nothing a coin toss would not.

**Strong down closes partially reverse**, recovering roughly a quarter to a third
of the closing decline before the next session opens.

This is a conditional mean, not a strategy. Within those 611 events the overnight
standard deviation is 166 bp — about six times the mean — and capturing it would
require crossing the spread twice while carrying unhedged overnight gap risk.

## 4. Abnormal closing volume does not distinguish persistence from reversal

This was the sharpest part of the question, and the answer is a null.

| Direction | Outcome | High-vol | Ordinary | Difference | 95% CI | p |
|---|---|---:|---:|---:|---|---:|
| strong up | overnight | +7.2 bp | +2.9 bp | +4.4 bp | [−17.7, +27.4] | 0.69 |
| strong down | overnight | +29.3 bp | +18.0 bp | +11.3 bp | [−16.4, +38.6] | 0.40 |

Not one contrast clears conventional significance at any horizon. The regression
agrees from the other direction: the interaction term is

```
β₃ = −0.0061     t = −0.06
```

about as close to a precise zero as this data produces.

The point estimates lean toward heavier volume meaning *more* reversal after down
closes — the opposite of a "conviction" reading — but with p = 0.40 that
direction is not supported either.

## 5. Where trading concentrates ≠ where direction becomes predictable

The descriptive microstructure result is strong, and it is worth keeping separate
from the predictive one.

![Volume is U-shaped across the trading day](results/figures/fig01_volume_ucurve.png)

| | Close relative to the midday trough |
|---|---:|
| Volume | **6.7×** |
| Volatility (mean abs. 5-minute return) | **1.4×** |

**Order flow concentrates near the close far more strongly than price movement
does.** The 15:30–16:00 window carries a median 21% of regular-hours volume
(11% for TSLA to 31% for JPM), of which the closing auction alone is a median 7%
— while being roughly *average* in volatility for the day.

That gap is a clean descriptive finding about liquidity. It is **not** evidence
of predictability, and the sections above show it does not become one.

## 6. The small relationship is not stable through time

![Rolling close-to-overnight relationship](results/figures/fig08_rolling_relationship.png)

The rolling 252-session slope runs from **+0.066 to −0.471**. It is near zero
through 2021–2022, strongly negative from mid-2023 into early 2025, and back near
zero by the end of the sample. For most of the window the confidence band
includes zero.

A full-sample point estimate averages over regimes that look genuinely different.

### Explanatory power is very low

```
Panel regression R²          = 0.005
Persistence classifier AUC   = 0.600   (in-sample)
```

Directional discrimination is modest even in-sample and was not developed into a
trading model. The p-values are not the point; the magnitudes are.

## 7. Data validation

Genuine 1-minute consolidated U.S. equity bars from the Hugging Face dataset
[`mito0o852/OHLCV-1m`](https://huggingface.co/datasets/mito0o852/OHLCV-1m),
aggregated to 5-minute regular-hours bars in `America/New_York` on the XNYS
exchange calendar.

| | |
|---|---|
| Universe | SPY, QQQ, IWM, AAPL, MSFT, NVDA, AMZN, META, GOOGL, JPM, XOM, TSLA |
| Period | 2021-01-04 → 2026-03-31 (1,316 sessions, 10 early closes) |
| Bars | 1,220,267 regular-hours 5-minute bars |
| Completeness | 99.4% of expected bars; 98.9% of ticker-sessions usable |
| Closing auction | captured on 96.6% of ticker-sessions |

### Cross-validated against an independent daily vendor

The 5-minute panel is aggregated back to daily bars and compared against a
separate daily source, after undoing that vendor's split adjustment:

| Measure | Result |
|---|---|
| Median absolute closing-price discrepancy | **0.0–1.0 bp** per ticker |
| 99th-percentile closing discrepancy | 5.4–24.8 bp |
| Sessions disagreeing by more than 50 bp | 2–5 per ticker (of ~1,300) |
| Volume reconciliation | **86.0–95.4%** |

The sources do **not** match perfectly, and the volume figure is not expected to
reach 100%: vendor daily volume includes pre- and post-market trading that the
regular-hours panel excludes by construction. The 5–14% shortfall is that
extended-hours activity.

### Three real data problems, found and handled

Each is caught by an automated check that remains active in the pipeline.

**Symbol identity around the Facebook/Meta rename.** Facebook traded as `FB`
until 2022-06-08 and as `META` afterwards, but the symbol `META` was already in
use by an unrelated issuer trading near \$15 while Facebook traded near \$370.
Renaming `FB → META` without fencing the alias in *both* directions interleaves
two different issuers' histories inside the same bars and produces overnight
returns above +2,000%. The alias is now date-fenced both ways, and a generic
session-range guard rejects any session spanning more than 50% regardless of
which symbol was reused.

**The 2023-01-24 NYSE opening-auction malfunction.** A documented exchange
malfunction produced erroneous opening prints, later busted, which survive in
tape data. A bar-level range guard (15%) sits inside a wide empirical gap: the
three worst bars in the sample span 18–28% within five minutes, while the widest
genuine bar — the 2025-04-07 reversal — spans 9.6%.

**Missing closing auctions for XOM.** For much of 2021–2024 the bar stamped at
16:00 for XOM contains a stray one-share print rather than the closing auction.
Taking its price as the official close would put a meaningless tick at the end of
the closing window, and counting its volume as auction volume would understate
closing activity by orders of magnitude. The closing bar is now accepted as an
auction only if it is at least 0.5% of regular-hours volume — far below any
genuine auction (1.5–20%) and far above any stray print.

Full account: **[docs/data_sources.md](docs/data_sources.md)**.

## 8. Methodology

- **Events** are the top/bottom 5% of each ticker's *own trailing 60-session*
  distribution of final-30-minute returns — never a pooled threshold, never a
  full-sample quantile. 1% tails carried as robustness.
- **Abnormal volume** is `AVOL = log(V_close) − log(trailing median V_close)`
  over 15:30–16:00 including the closing auction.
- **Inference** uses a block bootstrap that resamples whole trading dates, and
  two-way clustered standard errors, because twelve correlated names share every
  trading date. Date-only, ticker-only and HC1 alternatives are reported side by
  side rather than the most favourable one being chosen.
- **Corporate actions** are corrected explicitly: the feed is unadjusted, so an
  uncorrected 10:1 split reads as a −90% overnight return.
- **Every conditional mean is reported against the unconditional overnight
  drift**, and every persistence rate against a drift-implied benchmark.

## 9. Leakage controls

Every event flag is built from strictly earlier sessions; the current session is
never part of its own reference distribution.

The claim is tested directly rather than asserted: the pipeline is run on the
full sample and on a truncated sample, and every event classification on the
overlap must be **byte-identical**. A companion test confirms the check is not
vacuous by verifying that the poisoned future would in fact have been detected.

```bash
make test     # 67 tests
```

Covering timezone localisation and DST transitions, early closes, holiday
handling, 1-minute→5-minute aggregation, closing-window and auction aggregation,
overnight arithmetic with split and dividend corrections, next-session matching
across holidays and data gaps, trailing normalisation, block-bootstrap inference,
session quality control, and end-to-end absence of look-ahead.

Full audit: **[docs/data_leakage_audit.md](docs/data_leakage_audit.md)**.

## 10. Limitations

**The mechanism is not observed.** OHLCV bars contain prices and share counts.
They do **not** contain bid-ask spreads, quoted depth, signed order flow, dealer
inventory, or closing-auction imbalance — and none of these is fabricated,
estimated or proxied anywhere in this repository. Liquidity provision, index
rebalancing and informed trading are all consistent with what was found and
**cannot be distinguished with this data**. They appear in the report as
hypotheses, never as findings.

**In-sample estimation.** No hold-out period and no walk-forward validation. The
study is free of look-ahead bias, which is a weaker claim than out-of-sample
validity.

**Cross-sectional dependence.** Twelve highly correlated mega-caps is effectively
far fewer than twelve independent series; the effective sample is closer to 1,316
dates than to 14,958 observations.

**Multiple comparisons.** Four outcome horizons, two tail definitions, seven
regime variables and a specification ladder. The regime results in particular are
exploratory.

**Sample.** Twelve mega-cap names over five years and one quarter, spanning an
unusual macro sequence. Findings may not extend to smaller or less liquid names,
or to other periods.

## 11. Reproduction

```bash
make venv          # virtualenv + package
make external      # daily bars, splits, dividends, VIX      (~1 min)
make data          # download and ingest 5-minute bars       (~25 min, ~20 GB transferred)
make pipeline      # full analysis -> results/               (~6 min)
make figures       # rebuild every figure from saved tables
make test          # 67 tests
```

Raw monthly files are deleted as they are consumed; peak disk use is roughly one
400 MB file per worker. `data/` is gitignored — this repository ships code and
results, not redistributed vendor data.

### Repository layout

```
src/closingbell/
  config.py           universe, paths, session and estimation constants
  calendar_utils.py   XNYS sessions, early closes, DST, next-session mapping
  ingest.py           download -> filter -> 1-minute to 5-minute aggregation
  external.py         daily bars, splits, dividends, VIX
  validation.py       cross-validation against the independent vendor
  sessions.py         session quality control and exclusion accounting
  seasonality.py      intraday profile and U-shape diagnostics
  features.py         prices, window returns, overnight, corporate actions
  normalize.py        trailing z-scores, percentiles, AVOL   (leak-free core)
  events.py           2x2 experiment, date-block bootstrap, deciles
  regressions.py      panel regression, persistence logit, rolling estimates
  timeofday.py        morning / midday / close placebo comparison
  regimes.py          VIX, market direction, calendar regimes
  plots.py            all ten figures
  pipeline.py         end-to-end orchestration
  figures.py          figure entry point

notebooks/            01 audit · 02 intraday · 03 core · 04 regressions · 05 robustness
docs/                 research_plan · data_sources · data_leakage_audit
report/report.md      the write-up
results/tables/       40 CSVs · results/figures/ 10 PNGs · results/summary.json
tests/                67 tests
```

### Figures

| | |
|---|---|
| `fig01` volume U-curve | `fig06` overnight by decile × volume regime |
| `fig02` volatility U-curve | `fig07` persistence vs the drift-implied benchmark |
| `fig03` closing-pressure distribution | `fig08` rolling close→overnight relationship |
| `fig04` close₃₀ vs overnight scatter | **`fig09` morning / midday / close comparison** |
| `fig05` overnight by decile | `fig10` per-ticker coefficient forest plot |

### Documentation

- **[report/report.md](report/report.md)** — the findings, in full
- **[docs/research_plan.md](docs/research_plan.md)** — design and pre-specified interpretation rules
- **[docs/data_sources.md](docs/data_sources.md)** — provenance, validation, and the three defects found
- **[docs/data_leakage_audit.md](docs/data_leakage_audit.md)** — every leakage channel, and the test that guards it
