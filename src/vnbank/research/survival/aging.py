"""Descriptive shape of the reversal hazard by swing age (research/paper1/DECISIONS.md D-019).

    uv run python -m vnbank.research.survival.aging --features-run <dir> --from-run <D-019 run>

Development rows only (trade_date <= dev_end; labels reaching later are censored there).
1. Empirical share of rows reversing within 5 days, by age bucket x swing_dist tercile.
2. The mechanical model M (swing age + swing_dist), fitted on all development rows with the
   2016 fold's chosen hyperparameters: predicted 5-day reversal probability by age bucket at
   the median swing_dist.
No test, no tuning: this only describes the shape.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pandas as pd

from vnbank.common import paths
from vnbank.research.shared.config import load
from vnbank.research.shared.run_meta import code_version
from vnbank.research.survival.features.assemble import FEATURES_MECH
from vnbank.research.survival.models.zoo import make_model
from vnbank.research.survival.walkforward import DEV_END

CFG = load(1)
H = CFG["evaluation"]["main_horizon"]
RUNS = paths.runs_dir(1)
AGE_EDGES = [0, 5, 10, 20, 40, 80, np.inf]
AGE_LABELS = ["1-5", "6-10", "11-20", "21-40", "41-80", ">80"]


def dev_censor(ds: pd.DataFrame) -> pd.DataFrame:
    """Censor labels reaching past the development end (as walkforward.split does)."""
    ds = ds[ds.trade_date <= DEV_END].copy()
    past = ds.end_date > DEV_END
    ds.loc[past, "event"] = 0
    ds.loc[past, "duration"] = ds.loc[past, "days_to_dev_end"]
    return ds[ds.duration > 0]


def empirical(ds: pd.DataFrame) -> pd.DataFrame:
    """Share reversing within H days among rows whose outcome by H is known."""
    known = (ds.event == 1) | (ds.duration >= H)
    d = ds[known].assign(rev=lambda x: ((x.event == 1) & (x.duration <= H)).astype(float))
    d["age_bucket"] = pd.cut(d.swing_age, AGE_EDGES, labels=AGE_LABELS)
    d["dist_tercile"] = pd.qcut(d.swing_dist, 3, labels=["far", "mid", "near"])
    g = d.groupby(["dist_tercile", "age_bucket"], observed=True).rev
    return g.agg(share="mean", n="size").reset_index()


def model_shape(ds: pd.DataFrame, params: dict) -> pd.DataFrame:
    m = make_model("logit", FEATURES_MECH, **params).fit(ds)
    mids = [3, 8, 15, 30, 60, 120]
    grid = pd.DataFrame({"swing_age": mids, "log_age": np.log1p(mids),
                         "swing_dist": float(ds.swing_dist.median())})  # fmt: skip
    p = 1 - m.survival(grid, np.array([H]))[:, 0]
    return pd.DataFrame({"age_bucket": AGE_LABELS, "age_used": mids, f"p_reversal_{H}d": p})


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--features-run", required=True)
    parser.add_argument("--from-run", required=True, help="D-019 dev_decompose run")
    args = parser.parse_args(argv)
    commit = code_version()
    ds = dev_censor(pd.read_parquet(Path(args.features_run) / "dataset.parquet"))
    chosen = json.loads((Path(args.from_run) / "metrics.json").read_text())["results"]
    params = chosen["2016"]["chosen"]["M"]
    emp, shape = empirical(ds), model_shape(ds, params)
    print(
        emp.pivot_table(
            index="age_bucket", columns="dist_tercile", values="share", observed=True
        ).round(3)
    )
    print(shape.round(3).to_string(index=False))
    run = RUNS / f"{datetime.now(UTC):%Y%m%dT%H%M%SZ}-aging-D-019"
    run.mkdir(parents=True)
    (run / "config.json").write_text(json.dumps({"protocol": "D-019 descriptive",
        "features_run": Path(args.features_run).name, "from_run": Path(args.from_run).name,
        "git_commit": commit, "params": params, "horizon": H,
        "age_buckets": AGE_LABELS}, indent=2))  # fmt: skip
    (run / "metrics.json").write_text(json.dumps({"empirical": emp.to_dict("records"),
        "model_shape": shape.to_dict("records")}, indent=2, default=float))  # fmt: skip
    print(json.dumps({"run_dir": str(run)}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
