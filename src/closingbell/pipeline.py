"""End-to-end analysis pipeline.

Run ``python -m closingbell.pipeline`` after ingestion.  Every stage writes its
output to ``results/tables`` so that the notebooks, the figures and the report
all read the same numbers.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from . import calendar_utils as cal
from . import config as C
from . import events as ev
from . import external as ext
from . import features as ft
from . import normalize as nz
from . import regimes as rg
from . import regressions as rx
from . import seasonality as sea
from . import sessions as sq


def _save(df: pd.DataFrame, name: str) -> pd.DataFrame:
    df.to_csv(C.TABLES / f"{name}.csv", index=False)
    return df


def load_bars() -> tuple[pd.DataFrame, pd.DataFrame]:
    bars = pd.read_parquet(C.PROCESSED / "bars5m.parquet")
    auction = pd.read_parquet(C.PROCESSED / "auction.parquet")
    return bars, auction


def run(verbose: bool = True) -> dict:
    log = print if verbose else (lambda *a, **k: None)
    bars, auction = load_bars()
    lo, hi = str(bars["session"].min()), str(bars["session"].max())
    schedule = cal.session_schedule(lo, hi)
    log(f"[pipeline] {len(bars):,} 5-minute bars, {bars.ticker.nunique()} tickers, {lo} -> {hi}")

    # ---- 1. session quality -------------------------------------------------
    qc = sq.session_quality(bars, auction, schedule)
    _save(qc, "session_quality")
    _save(sq.quality_summary(qc), "session_quality_summary")
    _save(sq.exclusion_breakdown(qc), "session_exclusions")
    _save(sq.dst_check(qc), "dst_sessions")
    _save(sq.early_close_check(qc), "early_close_sessions")
    log(f"[pipeline] QC: {int(qc.usable.sum()):,} usable of {len(qc):,} ticker-sessions")

    # ---- 2. intraday seasonality -------------------------------------------
    prof = sea.intraday_profile(bars)
    prof_n = sea.normalize_profile(prof)
    _save(prof_n, "intraday_profile")
    _save(sea.cross_sectional_profile(prof_n), "intraday_profile_cross_section")
    _save(sea.u_shape_diagnostics(prof_n), "u_shape_diagnostics")
    _save(sea.closing_share(bars, auction), "closing_volume_share")

    # ---- 3. features and normalisation --------------------------------------
    external = ext.load_external()
    sess = ft.build_features(bars, auction, qc, schedule, external)
    sess = nz.build_normalized(sess)
    sess = rg.build_regimes(sess, external["vix"], schedule)
    sess.to_parquet(C.PROCESSED / "sessions.parquet", index=False)

    # Provenance: does the rebuilt daily bar match an independent vendor?
    from . import validation as val
    _save(val.crossvalidate_daily(sess, external["daily"], external["splits"]),
          "data_crossvalidation")
    _save(val.worst_disagreements(sess, external["daily"], external["splits"]),
          "data_crossvalidation_worst")
    log(f"[pipeline] session table: {len(sess):,} rows")

    # ---- 4. event samples ---------------------------------------------------
    universe = ev.event_panel(sess)
    events = universe[universe["is_extreme"]].copy()
    events_1pct = universe[universe["is_extreme_1pct"]].copy()
    log(f"[pipeline] eligible sessions {len(universe):,}; "
        f"5% tail events {len(events):,}; 1% tail events {len(events_1pct):,}")

    # ---- 5. the central 2x2 -------------------------------------------------
    _save(ev.central_table(events, universe=universe), "central_2x2")
    _save(ev.two_by_two(events, "r_overnight", universe=universe),
          "central_2x2_overnight")
    _save(ev.volume_contrast(events), "volume_contrast_overnight")
    _save(pd.concat([ev.volume_contrast(events, o) for o in ev.OUTCOMES],
                    ignore_index=True), "volume_contrast_all")
    _save(ev.central_table(events_1pct, "extreme_dir_1pct", universe), "central_2x2_1pct")
    _save(ev.two_by_two(events_1pct, "r_overnight", "extreme_dir_1pct", universe),
          "central_2x2_overnight_1pct")

    # ---- 6. deciles ---------------------------------------------------------
    _save(ev.decile_table(universe, "r_overnight"), "overnight_by_decile")
    _save(ev.decile_table(universe, "r_overnight", split_volume=True),
          "overnight_by_decile_volume")
    _save(ev.decile_table(universe, "r_open30_next"), "open30_by_decile")

    # ---- 7. regressions -----------------------------------------------------
    main = rx.fit_ols(universe, cluster="two_way")
    _save(rx.tidy(main), "regression_main")
    _save(rx.tidy(main, keep_fe=True), "regression_main_with_fe")
    _save(rx.se_comparison(universe), "regression_se_comparison")
    _save(rx.spec_ladder(universe), "regression_spec_ladder")
    _save(rx.per_ticker_coefficients(universe), "per_ticker_coefficients")

    main60 = rx.fit_ols(universe, cluster="two_way", main_var="r_close60")
    _save(rx.tidy(main60), "regression_close60")
    # Closing move measured to the last regular trade, so predictor and outcome
    # share no price: isolates mechanical measurement-error correlation.
    _save(rx.tidy(rx.fit_ols(universe, cluster="two_way",
                             main_var="r_close30_ex_auction")),
          "regression_no_shared_price")
    ex_corp = universe[~universe["overnight_corp_action"].fillna(False)]
    _save(rx.tidy(rx.fit_ols(ex_corp, cluster="two_way")), "regression_ex_corp_actions")

    on_events = rx.fit_ols(events, cluster="two_way")
    _save(rx.tidy(on_events), "regression_events_only")

    # outcome robustness
    rows = []
    for outcome in ["r_open30_next", "r_session_next", "r_next_close_to_close"]:
        u = universe.rename(columns={"r_overnight": "_keep", outcome: "r_overnight"})
        t = rx.tidy(rx.fit_ols(u, cluster="two_way")).assign(outcome=outcome)
        rows.append(t)
    _save(pd.concat(rows, ignore_index=True), "regression_other_outcomes")

    # ---- 8. persistence -----------------------------------------------------
    logit = rx.fit_persistence_logit(events)
    _save(rx.tidy(logit), "persistence_logit")
    _save(rx.calibration_table(logit), "persistence_calibration")
    _save(rx.persistence_by_decile(universe), "persistence_by_decile")
    _save(rx.persistence_by_decile(universe, split_volume=False),
          "persistence_by_decile_pooled")
    fit_stats = rx.brier_and_auc(logit)
    _save(rx.rolling_relationship(universe), "rolling_relationship")

    # ---- 9. time of day -----------------------------------------------------
    from . import timeofday as tod
    _save(tod.tod_regressions(sess), "time_of_day_regressions")
    _save(tod.tod_regressions(sess, restrict_to_extremes=True),
          "time_of_day_regressions_extremes")
    _save(tod.tod_persistence_rates(sess), "time_of_day_persistence")
    _save(tod.window_volatility_scale(sess), "time_of_day_scale")

    # ---- 10. regimes --------------------------------------------------------
    _save(rg.all_regime_tables(events), "regime_tables")

    summary = {
        "bars": int(len(bars)),
        "tickers": sorted(bars["ticker"].unique().tolist()),
        "sample_start": lo, "sample_end": hi,
        "calendar_sessions": int(len(schedule)),
        "early_closes": int(schedule["is_early_close"].sum()),
        "ticker_sessions": int(len(qc)),
        "usable_ticker_sessions": int(qc["usable"].sum()),
        "eligible_sessions": int(len(universe)),
        "events_5pct": int(len(events)),
        "events_1pct": int(len(events_1pct)),
        "logit_fit": fit_stats,
        "main_coefs": {k: float(main.params[k]) for k in
                       ["r_close", "avol", "r_close_x_avol"]},
        "main_tstats": {k: float(main.tvalues[k]) for k in
                        ["r_close", "avol", "r_close_x_avol"]},
    }
    (C.RESULTS / "summary.json").write_text(json.dumps(summary, indent=2, default=str))
    log("[pipeline] done")
    return {"sessions": sess, "universe": universe, "events": events,
            "qc": qc, "summary": summary, "main": main, "logit": logit}


if __name__ == "__main__":
    run()
