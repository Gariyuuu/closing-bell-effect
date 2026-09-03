# Research plan

## Question

> When a liquid U.S. equity experiences an unusually strong price move during the
> final 30 minutes of regular trading, does that move tend to persist or reverse
> overnight, and does abnormal closing volume distinguish persistence from
> reversal?

This is a descriptive question about conditional return distributions. It is not
a question about whether a strategy is profitable, and nothing in this repository
should be read as an answer to that second question — see
[Limits of the design](#limits-of-the-design).

## Why the question is not trivially answerable

Three things make a naive version of this analysis misleading, and the design is
built around them.

**A "strong" closing move is not a fixed number.** A 60 bp final half-hour is
unremarkable for TSLA and extreme for XOM, and it is unremarkable for any name in
October 2022 and extreme in a calm month. Events are therefore defined by each
ticker's *own trailing distribution*, never by a pooled threshold.

**Overnight returns are not centred on zero.** U.S. equities carry a positive
unconditional overnight drift. Any conditional overnight mean must be read
against that benchmark, and the "does the sign persist?" question needs a
drift-implied benchmark rather than 50%.

**The close is not the only thing that happened.** Short-horizon reversal exists
throughout the trading day. A closing effect is only interesting if it is
distinguishable from what an arbitrary 30-minute window would show, which is why
the design includes an explicit time-of-day placebo.

## Design

### Sample

Twelve liquid U.S. names — SPY, QQQ, IWM, AAPL, MSFT, NVDA, AMZN, META, GOOGL,
JPM, XOM, TSLA — over 2021-01-04 to 2026-03-31 (1,316 exchange sessions), at
5-minute resolution in `America/New_York`. Provenance and validation:
[data_sources.md](data_sources.md).

### Session admission

Sessions are validated against the XNYS exchange calendar rather than against
whatever the file contains. Holidays are absent by construction; early closes
expect 42 bars rather than 78 and are **never** treated as though 16:00 existed.
An early close is still a valid *following* session (it has an opening print and
a full session return), so it is excluded as an event but retained as an outcome.

### Primary variables

| Variable | Definition |
|---|---|
| `r_close30` | `P(16:00) / P(15:30) − 1` |
| `r_close60` | `P(16:00) / P(15:00) − 1` |
| `r_overnight` | `P_open(t+1) / P_close(t) − 1`, split- and dividend-corrected |
| `r_open30_next` | `P(10:00, t+1) / P(09:30, t+1) − 1` |
| `r_session_next` | `P(16:00, t+1) / P(09:30, t+1) − 1` |
| `r_next_close_to_close` | `P_close(t+1) / P_close(t) − 1` |

`P(16:00)` is the official closing price: the first print of the closing auction
where the feed carries a plausible auction, and the last regular-hours trade
otherwise. `P(15:30)` is the close of the 15:25 slot, so the reference price sits
strictly before the window being measured.

### Event definition

For each ticker, `r_close30` is standardised against its own previous 60 valid
sessions (minimum 40), producing a z-score, a percentile and an absolute
pressure. Extreme closing pressure is the top or bottom 5% of that trailing
distribution; 1% tails are carried as robustness.

Closing volume is aggregated over 15:30–16:00 **including the closing auction**,
since the auction is the single largest closing-period event. Abnormal volume is
`AVOL = log(V_close) − log(trailing median V_close)`, with its trailing
percentile rank. "High" closing volume is the top 30% of that rank.

### Estimation

1. **The 2×2.** Extreme up/down × high/ordinary closing volume, each cell
   reporting the mean, median, block-bootstrap intervals, same-sign probability,
   and — critically — the **excess over the unconditional overnight mean**.
2. **Panel regression.** Overnight return on the closing return, AVOL, their
   interaction, and controls (market session return, realised volatility,
   previous overnight return, day of week, month end) with ticker fixed effects.
3. **Persistence logit** on extreme events, with calibration, Brier score
   against the base rate, and AUC.
4. **Time-of-day placebo.** 09:30–10:00, 12:00–12:30 and 15:30–16:00, each
   standardised within its own slot and tested against the period that follows.
5. **Regimes.** VIX, market direction, day of week, month end, quarter end and
   monthly option expiration.

### Inference

Observations are strongly cross-correlated: twelve names share every date. All
intervals come from a **block bootstrap that resamples whole trading dates**, and
regression standard errors are **two-way clustered by ticker and date**, with
date-only, ticker-only and heteroskedasticity-robust alternatives reported side
by side.

## Pre-specified interpretation rules

Fixed before the results were examined, so that a null result is reportable:

- A cell mean is only evidence of a closing effect if its **excess over the
  unconditional overnight drift** is distinguishable from zero.
- The volume interaction is only supported if the **high-minus-ordinary
  difference** is distinguishable from zero — not merely if the two cells have
  different point estimates.
- The close is only "special" if its standardised predictive coefficient is
  distinguishable from the morning and midday coefficients.
- Regime cuts are exploratory. With seven regime variables and two directions,
  individually significant cells are expected under the null and are reported as
  such.

## Limits of the design

OHLCV bars contain prices and share counts. They do not contain quotes, depth,
order imbalance, or auction imbalance. The study can therefore establish *what*
the conditional return distribution looks like and cannot establish *why*.
Mechanisms are discussed in the report as hypotheses that this dataset cannot
adjudicate, never as findings. See [report/report.md](../report/report.md).
