"""D-027 item 1 validation: the random-walk null scored on the development folds (2014-2016,
inside the first training window only; descriptive).

    uv run python -m vnbank.research.survival.final.rw_dev_check --features-run <dir>

Same folds, purge, embargo and development censoring as D-014. Reports Uno C, IBS, 5-day td-AUC
and 5-day calibration of RW next to Kaplan-Meier, per fold and pooled.
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
from vnbank.research.shared.run_meta import code_version
from vnbank.research.survival.dev_compare import metrics
from vnbank.research.survival.evaluation.metrics import surv
from vnbank.research.survival.final.rw_null import rw_survival
from vnbank.research.survival.models.zoo import make_model
from vnbank.research.survival.walkforward import DEV_FOLDS, IBS_TIMES, split


def main(argv: list[str] | None = None) -> int:  # pragma: no cover - CLI wiring
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--features-run", required=True)
    a = ap.parse_args(argv)
    commit = code_version()
    fr = Path(a.features_run)
    fcfg = json.loads((fr / "config.json").read_text())
    snap = paths.SNAPSHOTS / fcfg["snapshot_id"]
    sessions = np.sort(pd.to_datetime(
        pd.read_parquet(snap / "sessions_hose.parquet").trade_date).to_numpy())  # fmt: skip
    cols = ["ticker", "trade_date", "high_adj", "low_adj", "close_adj"]
    px = pd.read_parquet(snap / "prices_adjusted.parquet", columns=cols)
    px["trade_date"] = pd.to_datetime(px.trade_date)
    px = px[px.trade_date.isin(set(sessions.astype("datetime64[ns]")))]
    ds = pd.read_parquet(fr / "dataset.parquet")
    ds["trade_date"], ds["end_date"] = pd.to_datetime(ds.trade_date), pd.to_datetime(ds.end_date)
    res, pooled = {}, {"val": [], "rw": [], "km": []}
    last_y = None
    for year in DEV_FOLDS:
        train, val = split(ds, sessions, year, dev=True)
        val = val.reset_index(drop=True)
        y_train = surv(train.event, train.duration)
        s_rw = rw_survival(px, val[["ticker", "trade_date"]], fcfg["k"])
        s_km = make_model("km", []).fit(train).survival(val, IBS_TIMES)
        res[str(year)] = {"rw": metrics(y_train, val, s_rw), "km": metrics(y_train, val, s_km),
                          "n": len(val)}  # fmt: skip
        pooled["val"].append(val)
        pooled["rw"].append(s_rw)
        pooled["km"].append(s_km)
        last_y = y_train
        print(
            year,
            "C rw",
            round(res[str(year)]["rw"]["uno_c"], 3),
            "IBS rw",
            round(res[str(year)]["rw"]["ibs"], 4),
            "km",
            round(res[str(year)]["km"]["ibs"], 4),
        )
    v = pd.concat(pooled["val"], ignore_index=True)
    res["pooled"] = {k: metrics(last_y, v, np.vstack(pooled[k])) for k in ("rw", "km")}
    run = paths.runs_dir(1) / f"{datetime.now(UTC):%Y%m%dT%H%M%SZ}-devcheck-D-027-rw"
    run.mkdir(parents=True)
    cfg = {
        "git_commit": commit,
        "features_run": fr.name,
        "snapshot_id": fcfg["snapshot_id"],
        "protocol": "D-027 item 1",
    }
    (run / "config.json").write_text(json.dumps(cfg, indent=2))
    (run / "metrics.json").write_text(json.dumps(res, indent=1, default=float))
    print(json.dumps({"run_dir": str(run), "pooled_rw": {k: res["pooled"]["rw"][k]
                                                         for k in ("uno_c", "ibs", "td_auc")},
                      "pooled_km_ibs": res["pooled"]["km"]["ibs"]}))  # fmt: skip
    return 0


if __name__ == "__main__":
    sys.exit(main())
