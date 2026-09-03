"""Figure entry point.

Rebuilds every figure from the artefacts the pipeline has already written, so
plots can be iterated on without re-running the estimation.
"""
from __future__ import annotations

import pandas as pd

from . import config as C
from . import events as ev
from . import plots


def load_context() -> dict:
    sess = pd.read_parquet(C.PROCESSED / "sessions.parquet")
    universe = ev.event_panel(sess)
    main_coef = (pd.read_csv(C.TABLES / "regression_main.csv")
                   .set_index("term").loc["r_close", "coef"])

    class _Res:                      # a stand-in for the fitted model object
        params = {"r_close": float(main_coef)}

    return {"sessions": sess, "universe": universe, "main": _Res(),
            "baseline_bps": float(universe["r_overnight"].mean() * 1e4)}


def main() -> int:
    ctx = load_context()
    for p in plots.build_all(ctx):
        print(f"[figures] {p.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
