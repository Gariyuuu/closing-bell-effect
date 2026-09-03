# Data leakage audit

Every quantity used to classify an event, and every quantity used to predict an
outcome, must have been knowable at the moment the classification is claimed to
be made — 16:00 ET on the event session. This document enumerates each place
information could travel backwards in time, states what the code does, and points
at the test that fails if it stops doing it.

## The claim being audited

> Every event flag in this study could have been produced in real time, at 16:00
> on the session in question, using only sessions that had already closed.

`tests/test_no_leakage_end_to_end.py::test_truncating_the_sample_reproduces_the_same_classifications`
establishes this directly: normalisation and event tagging are run on the full
sample and on a truncated sample, and every classification on the overlap is
required to be identical.

## Audit table

| # | Where leakage could enter | What the code does | Test |
|---|---|---|---|
| 1 | Standardising the closing move | Trailing mean/std over the **previous** 60 valid sessions; the current session is never in its own reference window | `test_current_observation_is_excluded_from_its_own_reference` |
| 2 | Percentile used to define extremes | Rank of today's value **among earlier values only**, not a full-sample quantile | `test_percentile_is_computed_against_earlier_sessions_only` |
| 3 | Median closing volume in AVOL | Trailing median over previous sessions | `test_avol_is_log_volume_less_trailing_median_log_free` |
| 4 | Any statistic reaching forward | Overwriting every value after session *t* leaves all statistics at *t* byte-identical | `test_no_future_information_leaks_backwards` |
| 5 | Whole-pipeline leakage | Full-sample and truncated-sample runs agree on the overlap | `test_truncating_the_sample_reproduces_the_same_classifications` |
| 6 | Overnight matching | Next session comes from the **exchange calendar**, not `shift(-1)` over present rows | `test_next_session_matching_crosses_a_holiday_correctly` |
| 7 | Matching across a data gap | A ticker missing session *t+1* yields NaN, never a match to *t+2* | `test_a_missing_next_session_yields_no_overnight_return` |
| 8 | Previous-overnight control | Read from the previous session's row, which ends at *t*'s open | `test_previous_overnight_control_is_backward_looking` |
| 9 | Insufficient history | No z-score, percentile or AVOL emitted below 40 trailing observations | `test_minimum_history_is_enforced` |
| 10 | Windows consuming invalid rows | Windows count **valid observations**; a session where the variable does not exist does not consume a slot | `test_window_counts_valid_observations_not_calendar_rows` |
| 11 | Cross-ticker contamination | Normalisation is strictly within ticker | `test_normalisation_is_per_ticker` |
| 12 | Early closes | No 15:30–16:00 window is manufactured; such sessions are not event-eligible | `test_early_close_session_has_no_closing_window` |

## Places where information deliberately flows forward

These are outcomes, not predictors, and are only ever on the left-hand side:

- `r_overnight`, `r_open30_next`, `r_session_next`, `r_next_close_to_close`
- `n_split_ratio`, `n_dividend` — next-session corporate actions, used **only** to
  strip mechanical price changes out of the outcome. A split ratio is announced
  weeks ahead, so this is not private information, but it is also never a
  regressor.

## Quantities that are contemporaneous, not forward-looking

Available at or before 16:00 on the event session, and used as controls:

- `mkt_r_session` — SPY's session return, complete at 16:00.
- `realized_vol` — built from that session's own 5-minute returns.
- `vix` — that session's close.
- `is_month_end`, `is_quarter_end`, `is_opex`, `dow` — calendar facts.

## Data-quality filters and their timing

Three filters remove observations, and each is evaluated on information available
within the session itself:

| Filter | Uses |
|---|---|
| `MAX_MISSING_FRAC` (incomplete session) | that session's bar count against the calendar |
| `MAX_BAR_RANGE` / `MAX_SESSION_RANGE` (erroneous prints) | that session's own bars |
| `MIN_AUCTION_SHARE` (implausible auction) | that session's auction and regular-hours volume |

None consults a later session. They do use the full-sample *choice of threshold*,
which is a researcher-degrees-of-freedom issue rather than a look-ahead issue;
the thresholds are set from a visible gap in the data and are stated in
[data_sources.md](data_sources.md) with the observations that motivated them.

## Deliberate non-claims

The study is leak-free in time. It is **not** an out-of-sample backtest:

- Model coefficients are estimated on the same sample they are reported for.
  There is no hold-out period, and the logit's AUC (0.598) is an in-sample figure.
- The sample window, universe and tail definitions were chosen once, up front,
  but they were chosen with general knowledge of U.S. equity microstructure.
- The regime analysis runs many cuts. Individually significant cells among them
  are expected under the null and are labelled exploratory in the report.

Absence of look-ahead bias means the results are not an artefact of using
tomorrow's data today. It does not mean they would replicate out of sample.
