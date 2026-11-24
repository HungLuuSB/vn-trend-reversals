"""Block-D attribution: leave one global feature out, and gold vs GPR (DECISIONS.md D-018).

    uv run python -m research.dev_attribution --features-run <...> --from-run <D-017 run dir>

Development only (inside 2012-2016). The D-017 specification `ABCDx` is refitted per fold
with the hyperparameters that run chose; each block-D feature is dropped (x and x_xdir)
in turn. Paired moving-block bootstrap (2,000 resamples) on the pooled validation rows;
two-sided bootstrap p-values for the IBS change, Holm-adjusted across the 14 features.
Uno's C: point estimates per feature; 200-resample intervals for the gold/GPR models only.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pandas as pd

from research.dev_compare import TIMES
from research.dev_decompose import SPECS_D017
from research.eval.bootstrap import block_resamples
from research.eval.metrics import ibs, surv, uno_c
from research.features.assemble import FEATURES_D, add_direction_interactions
from research.models.zoo import make_model
from research.run_meta import code_version
from research.walkforward import DEV_END, DEV_FOLDS, TAU, split

REPO = Path(__file__).resolve().parents[1]
FULL = "ABCDx"
GOLD, GPR = ["gold_ret"], ["gpr_level", "gpr_chg"]
C_MODELS = (FULL, "-gold_ret", "-gold-gpr")
C_RESAMPLES = 200


def drop(features: list[str], names: list[str]) -> list[str]:
    gone = set(names) | {f"{n}_xdir" for n in names}
    return [f for f in features if f not in gone]


def variants() -> dict[str, list[str]]:
    full = SPECS_D017[FULL]
    out = {FULL: full}
    for f in FEATURES_D:
        out[f"-{f}"] = drop(full, [f])
    out["-gold-gpr"] = drop(full, GOLD + GPR)
    return out


def holm(p: np.ndarray) -> np.ndarray:
    """Holm step-down adjusted p-values."""
    p = np.asarray(p, dtype="float64")
    order = np.argsort(p)
    m = len(p)
    adj = np.maximum.accumulate((m - np.arange(m)) * p[order])
    out = np.empty(m)
    out[order] = np.minimum(adj, 1.0)
    return out


def boot_p(d: np.ndarray) -> float:
    d = d[np.isfinite(d)]
    return float(min(1.0, 2 * min((d <= 0).mean(), (d >= 0).mean())))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--features-run", required=True)
    parser.add_argument("--from-run", required=True, help="D-017 run (chosen hyperparameters)")
    parser.add_argument("--bootstrap", type=int, default=2000)
    args = parser.parse_args(argv)
    commit = code_version()

    fr = Path(args.features_run)
    chosen = json.loads((Path(args.from_run) / "metrics.json").read_text())["results"]
    ds = pd.read_parquet(fr / "dataset.parquet")
    fcfg = json.loads((fr / "config.json").read_text())
    snap = REPO / "research" / "snapshots" / fcfg["snapshot_id"]
    sessions = np.sort(pd.to_datetime(
        pd.read_parquet(snap / "sessions_hose.parquet").trade_date).to_numpy())  # fmt: skip
    ds = add_direction_interactions(ds[ds.trade_date <= DEV_END])
    specs = variants()

    run = REPO / "research" / "runs" / f"{datetime.now(UTC):%Y%m%dT%H%M%SZ}-devattribution-D-018"
    run.mkdir(parents=True)
    logf = open(run / "log.txt", "w")

    def log(msg):
        print(msg, flush=True)
        logf.write(msg + "\n")
        logf.flush()

    preds = {k: [] for k in specs}
    vals, y_train = [], None
    for year in DEV_FOLDS:
        t0 = time.time()
        train, val = split(ds, sessions, year, dev=True)
        params = chosen[str(year)]["chosen"][FULL]
        for name, feats in specs.items():
            preds[name].append(make_model("logit", feats, **params).fit(train).survival(val, TIMES))
        vals.append(val)
        y_train = surv(train.event, train.duration)  # pooled metrics use the last fold's
        log(f"{year}: {len(specs)} fits with {params} in {time.time() - t0:.0f}s")

    v = pd.concat(vals, ignore_index=True)
    p = {k: np.vstack(x) for k, x in preds.items()}
    ev, du = v.event.to_numpy(), v.duration.to_numpy()
    point = {k: {"ibs": ibs(y_train, surv(ev, du), s, TIMES),
                 "uno_c": uno_c(y_train, surv(ev, du), 1 - s[:, TAU - 1], TAU)}
             for k, s in p.items()}  # fmt: skip

    t0 = time.time()
    dates = v.trade_date.to_numpy()
    D = {k: {"ibs": [], "uno_c": []} for k in p}
    for idx in block_resamples(dates, block=20, n=args.bootstrap, seed=0):
        y = surv(ev[idx], du[idx])
        for k, s in p.items():
            D[k]["ibs"].append(ibs(y_train, y, s[idx], TIMES))
    # Uno's C is ~40x slower than IBS: 200 resamples, gold/GPR models only (D-018 amendment)
    for idx in block_resamples(dates, block=20, n=C_RESAMPLES, seed=0):
        y = surv(ev[idx], du[idx])
        for k in C_MODELS:
            D[k]["uno_c"].append(uno_c(y_train, y, 1 - p[k][idx, TAU - 1], TAU))
    D = {k: {m: np.asarray(x) for m, x in d.items()} for k, d in D.items()}
    log(f"bootstrap: IBS {args.bootstrap}, C {C_RESAMPLES} in {time.time() - t0:.0f}s")

    def diff(a, b, m):  # a minus b
        return D[a][m] - D[b][m]

    rows = []
    for f in FEATURES_D:
        dib = diff(f"-{f}", FULL, "ibs")  # > 0: dropping f hurts, so f helps
        rows.append({"feature": f,
                     "d_ibs": point[f"-{f}"]["ibs"] - point[FULL]["ibs"],
                     "d_ibs_lo": float(np.quantile(dib, 0.025)),
                     "d_ibs_hi": float(np.quantile(dib, 0.975)), "p_ibs": boot_p(dib),
                     "d_c": point[FULL]["uno_c"] - point[f"-{f}"]["uno_c"]})  # fmt: skip
    tab = pd.DataFrame(rows)
    tab["p_ibs_holm"] = holm(tab.p_ibs.to_numpy())
    tab["informative"] = (tab.p_ibs_holm < 0.05) & (tab.d_ibs > 0)

    def ci(a, b, m):
        d = diff(a, b, m)
        return {"point": float(point[a][m] - point[b][m]), "lo": float(np.quantile(d, 0.025)),
                "hi": float(np.quantile(d, 0.975)), "p": boot_p(d)}  # fmt: skip

    gold = {
        # does gold help when GPR is in the model? (IBS without gold - IBS full; > 0 = helps)
        "gold_given_gpr_ibs": ci("-gold_ret", FULL, "ibs"),
        # does GPR help when gold is out? (IBS without both - IBS without gold)
        "gpr_given_no_gold_ibs": ci("-gold-gpr", "-gold_ret", "ibs"),
        "gold_given_gpr_c": ci(FULL, "-gold_ret", "uno_c"),
        "gpr_given_no_gold_c": ci("-gold_ret", "-gold-gpr", "uno_c"),
    }
    log(tab.round(5).to_string(index=False))
    log(json.dumps(gold, indent=1))

    cfg = {"protocol": "D-018", "features_run": fr.name, "from_run": Path(args.from_run).name,
           "snapshot_id": fcfg["snapshot_id"], "git_commit": commit, "full": FULL,
           "variants": list(specs), "bootstrap": args.bootstrap, "block": 20,
           "c_resamples": C_RESAMPLES, "c_models": C_MODELS,
           "folds": DEV_FOLDS}  # fmt: skip
    (run / "config.json").write_text(json.dumps(cfg, indent=2))
    (run / "metrics.json").write_text(json.dumps(
        {"point": point, "leave_one_out": tab.to_dict("records"), "gold_vs_gpr": gold},
        indent=2, default=float))  # fmt: skip
    log(json.dumps({"run_dir": str(run), "informative": tab.feature[tab.informative].tolist()}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
