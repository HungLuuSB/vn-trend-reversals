"""Nested feature-set comparisons (research/paper1/DECISIONS.md D-015, D-016).

    uv run python -m vnbank.research.survival.dev_decompose --features-run <...> [--protocol D-016]

Development only (inside 2012-2016, folds 2014/15/16, same protocol as D-014). The tuned
logistic hazard is fitted on nested feature sets AGE < A < AB < ABC and compared with KM and
with each other (paired moving-block bootstrap).
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

from vnbank.common import paths
from vnbank.research.shared.run_meta import code_version
from vnbank.research.survival.dev_compare import HORIZONS, TIMES, metrics, tune
from vnbank.research.survival.evaluation.bootstrap import paired_ci
from vnbank.research.survival.evaluation.metrics import ibs, surv, td_auc, uno_c
from vnbank.research.survival.features.assemble import (
    BLOCKS,
    FEATURES_MECH,
    add_bank_interactions,
    add_direction_interactions,
    bank_features,
    xdir,
)
from vnbank.research.survival.features.block_e import add_block_e
from vnbank.research.survival.features.sequence import SEQ, add_sequences
from vnbank.research.survival.models.zoo import CFG, make_model
from vnbank.research.survival.walkforward import DEV_END, DEV_FOLDS, TAU, TOO_GOOD_C, split

REPO = paths.REPO
RUNS = paths.runs_dir(1)  # research/paper1/runs
SPECS = {
    "AGE": ["swing_age", "log_age"],
    "A": list(BLOCKS["A"]),
    "AB": [*BLOCKS["A"], *BLOCKS["B"]],
    "ABC": [*BLOCKS["A"], *BLOCKS["B"], *BLOCKS["C"]],
}
DIFFS = [("A", "AGE"), ("AB", "A"), ("ABC", "AB"), ("ABC", "AGE")]

# D-016: incremental value over the mechanical baseline M (swing age + swing_dist)
SPECS_D016 = {
    "M": list(FEATURES_MECH),
    "MB": [*FEATURES_MECH, *BLOCKS["B"]],
    "MBC": [*FEATURES_MECH, *BLOCKS["B"], *BLOCKS["C"]],
    "MD": [*FEATURES_MECH, *BLOCKS["D"]],
    "ABC": [*BLOCKS["A"], *BLOCKS["B"], *BLOCKS["C"]],
    "ABCD": [*BLOCKS["A"], *BLOCKS["B"], *BLOCKS["C"], *BLOCKS["D"]],
}
DIFFS_D016 = [("ABC", "M"), ("MB", "M"), ("MBC", "MB"), ("MD", "M"), ("ABCD", "ABC")]
# D-017: direction-specific slopes for blocks B-D; a spec is a feature list (logistic hazard)
# or a (model, features) pair
_A, _B, _C, _D = (list(BLOCKS[b]) for b in "ABCD")
_BCx = [*_B, *xdir(_B), *_C, *xdir(_C)]
_Dx = [*_D, *xdir(_D)]
SPECS_D017 = {
    "M": list(FEATURES_MECH),
    "MBC": [*FEATURES_MECH, *_B, *_C],
    "MBCx": [*FEATURES_MECH, *_BCx],
    "MBCDx": [*FEATURES_MECH, *_BCx, *_Dx],
    "ABCx": [*_A, *_BCx],
    "ABCDx": [*_A, *_BCx, *_Dx],
}
DIFFS_D017 = [("MBCx", "MBC"), ("ABCDx", "ABCx"), ("MBCDx", "MBCx"), ("ABCx", "M")]
SPECS_D017_GBM = {"gbm_ABC": ("gbm", [*_A, *_B, *_C]), "gbm_ABCD": ("gbm", [*_A, *_B, *_C, *_D])}
DIFFS_D017_GBM = [("gbm_ABCD", "gbm_ABC")]
# D-019: RQ3, does swing age matter once swing_dist is known? ("km" is always fitted)
SPECS_D019 = {
    "DIST": ["swing_dist"],
    "M": list(FEATURES_MECH),
    "AGE": ["swing_age", "log_age"],
}
DIFFS_D019 = [("M", "DIST"), ("AGE", "km"), ("DIST", "km")]
# D-020: RQ2 bank x rate/dollar channels on top of the D-017 specification
SPECS_D020 = {"ABCDx": SPECS_D017["ABCDx"], "ABCDx_bank": [*SPECS_D017["ABCDx"], *bank_features()]}
DIFFS_D020 = [("ABCDx_bank", "ABCDx")]
# D-022: neural hazard (GRU over the last 60 days + logistic-hazard head)
_ABCD = [*_A, *_B, *_C, *_D]
SPECS_D022 = {
    "nn_seq_ABCD": ("nn", [*_ABCD, SEQ]),
    "nn_seq_ABC": ("nn", [*_A, *_B, *_C, SEQ]),
    "nn_static_ABCD": ("nn", _ABCD),
    "ABCDx": SPECS_D017["ABCDx"],
    "M": list(FEATURES_MECH),
}
DIFFS_D022 = [("nn_seq_ABCD", "nn_static_ABCD"), ("nn_seq_ABCD", "ABCDx"), ("nn_seq_ABCD", "M"),
              ("nn_seq_ABCD", "nn_seq_ABC")]  # fmt: skip
# D-023: block E (first-released NPL, news attention) on bank rows only
FEATURES_E = ["npl_ratio", "npl_change", "news_count", "news_rel_20"]
SPECS_D023 = {
    "M": SPECS_D016["M"],
    "M_E": [*SPECS_D016["M"], *FEATURES_E],
    "ABCDx": SPECS_D017["ABCDx"],
    "ABCDx_E": [*SPECS_D017["ABCDx"], *FEATURES_E],
}
DIFFS_D023 = [("ABCDx_E", "ABCDx"), ("M_E", "M")]
OUTER_EXTRA = {"nn": {"seeds": CFG["neural"]["outer_seeds"]}}  # D-022: seed-averaged outer refit
SHUFFLED = {"D-022": "nn_seq_ABCD"}  # spec that gets the shuffled-label control
PROTOCOLS = {
    "D-015": (SPECS, DIFFS),
    "D-016": (SPECS_D016, DIFFS_D016),
    "D-017": (SPECS_D017, DIFFS_D017),
    "D-017-gbm": (SPECS_D017_GBM, DIFFS_D017_GBM),
    "D-019": (SPECS_D019, DIFFS_D019),
    "D-020": (SPECS_D020, DIFFS_D020),
    "D-022": (SPECS_D022, DIFFS_D022),
    "D-023": (SPECS_D023, DIFFS_D023),
    "D-023-ocr-only": (SPECS_D023, DIFFS_D023),  # robustness: no visually transcribed values
}


def model_and_features(spec) -> tuple[str, list[str]]:
    return spec if isinstance(spec, tuple) else ("logit", spec)


def boot(y_train, val, preds: dict[str, np.ndarray], n: int, seed: int, diffs=DIFFS) -> dict:
    ev, du = val.event.to_numpy(), val.duration.to_numpy()

    def c(m):
        return lambda i: uno_c(y_train, surv(ev[i], du[i]), 1 - preds[m][i, TAU - 1], TAU)

    def b(m):
        return lambda i: ibs(y_train, surv(ev[i], du[i]), preds[m][i], TIMES)

    def a5(m):
        return lambda i: float(td_auc(y_train, surv(ev[i], du[i]), 1 - preds[m][i, 4:5],
                                      np.array([5]))[0])  # fmt: skip

    stats = {}
    for m in preds:
        stats[f"{m}:uno_c"], stats[f"{m}:ibs"], stats[f"{m}:auc5"] = c(m), b(m), a5(m)
    for hi, lo in diffs:
        for key, f in (("uno_c", c), ("ibs", b), ("auc5", a5)):
            stats[f"{hi}-{lo}:{key}"] = lambda i, f=f, hi=hi, lo=lo: f(hi)(i) - f(lo)(i)
    return paired_ci(val.trade_date.to_numpy(), stats, block=20, n=n, seed=seed)


def shuffled_control(mname, feats, params, train, val, y_train, log) -> dict:
    """Outcomes permuted across training rows (D-013); one seed per permutation (D-022)."""
    cs = []
    for k in range(CFG["neural"]["shuffle_controls"]):
        perm = np.random.default_rng(k).permutation(len(train))
        shuf = train.copy()
        shuf["duration"] = train.duration.to_numpy()[perm]
        shuf["event"] = train.event.to_numpy()[perm]
        s = make_model(mname, feats, **params, seed=k).fit(shuf).survival(val, np.array([TAU]))
        cs.append(uno_c(y_train, surv(val.event, val.duration), 1 - s[:, 0], TAU))
    log(f"  shuffled C mean {np.mean(cs):.3f} values {np.round(cs, 3).tolist()}")
    return {"values": np.round(cs, 4).tolist(), "mean": float(np.mean(cs))}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--features-run", required=True)
    parser.add_argument("--bootstrap", type=int, default=200)
    parser.add_argument("--protocol", choices=sorted(PROTOCOLS), default="D-015")
    args = parser.parse_args(argv)
    specs, diffs = PROTOCOLS[args.protocol]

    commit = code_version()  # at the start: the code this run actually executes
    fr = Path(args.features_run)
    ds = pd.read_parquet(fr / "dataset.parquet")
    fcfg = json.loads((fr / "config.json").read_text())
    snap = REPO / "data" / "snapshots" / fcfg["snapshot_id"]
    sessions = np.sort(pd.to_datetime(
        pd.read_parquet(snap / "sessions_hose.parquet").trade_date).to_numpy())  # fmt: skip
    ds = ds[ds.trade_date <= DEV_END]
    if args.protocol.startswith(("D-017", "D-020", "D-022", "D-023")):
        ds = add_direction_interactions(ds)
    if args.protocol == "D-022":
        cols = ["ticker", "trade_date", "open_adj", "high_adj", "low_adj", "close_adj", "volume"]
        prices = pd.read_parquet(snap / "prices_adjusted.parquet", columns=cols)
        prices["trade_date"] = pd.to_datetime(prices.trade_date)
        ds = add_sequences(ds.reset_index(drop=True), prices[prices.trade_date <= DEV_END])
    if args.protocol == "D-020":
        ds = add_bank_interactions(ds)
    block_e = {}
    if args.protocol.startswith("D-023"):
        ds, block_e = add_block_e(ds, ocr_values_only=args.protocol.endswith("ocr-only"))

    run = RUNS / f"{datetime.now(UTC):%Y%m%dT%H%M%SZ}-devdecompose-{args.protocol}"
    run.mkdir(parents=True)
    logf = open(run / "log.txt", "w")

    def log(msg):
        print(msg, flush=True)
        logf.write(msg + "\n")
        logf.flush()

    results, pooled_preds, pooled_val, last_y_train = {}, {}, [], None
    for year in DEV_FOLDS:
        t0 = time.time()
        train, val = split(ds, sessions, year, dev=True)
        inner_train, inner_val = split(train, sessions, year - 1, dev=False)
        log(f"{year}: train {len(train):,} val {len(val):,}")
        y_train = surv(train.event, train.duration)
        preds, fold = {}, {"chosen": {}, "metrics": {}}
        preds["km"] = make_model("km", []).fit(train).survival(val, TIMES)
        fold["metrics"]["km"] = metrics(y_train, val, preds["km"])
        for spec, entry in specs.items():
            mname, feats = model_and_features(entry)
            params = tune(mname, feats, inner_train, inner_val, log)
            fold["chosen"][spec] = params
            fit_params = {**params, **OUTER_EXTRA.get(mname, {})}
            preds[spec] = make_model(mname, feats, **fit_params).fit(train).survival(val, TIMES)
            fold["metrics"][spec] = metrics(y_train, val, preds[spec])
            m = fold["metrics"][spec]
            log(f"  {spec} {params}: C {m['uno_c']:.3f} IBS {m['ibs']:.4f} td-AUC {m['td_auc']}")
            if SHUFFLED.get(args.protocol) == spec:
                fold["shuffled_uno_c"] = shuffled_control(mname, feats, params, train, val,
                                                          y_train, log)  # fmt: skip
        fold["bootstrap"] = boot(y_train, val, preds, args.bootstrap, seed=year, diffs=diffs)
        results[str(year)] = fold
        for k, v in preds.items():
            pooled_preds.setdefault(k, []).append(v)
        pooled_val.append(val)
        last_y_train = y_train
        log(f"  fold done in {time.time() - t0:.0f}s")

    pv = pd.concat(pooled_val, ignore_index=True)
    pp = {k: np.vstack(v) for k, v in pooled_preds.items()}
    results["pooled"] = {
        "metrics": {k: metrics(last_y_train, pv, v) for k, v in pp.items()},
        "bootstrap": boot(last_y_train, pv, pp, args.bootstrap, seed=0, diffs=diffs),
    }

    pm = results["pooled"]["metrics"]
    if args.protocol == "D-015":  # interpretation rule (pooled, 5-day td-AUC)
        age, full = pm["AGE"]["td_auc"]["5"] - 0.5, pm["ABC"]["td_auc"]["5"] - 0.5
        results["age_share_auc5"] = age / full if full > 0 else float("nan")
        results["mainly_age_effect"] = bool(full > 0 and age >= 0.8 * full)
    else:  # an improvement counts only if both pooled intervals exclude zero (D-016, D-017)
        b = results["pooled"]["bootstrap"]

        def better(hi, lo):
            return bool(b[f"{hi}-{lo}:uno_c"]["lo"] > 0 and b[f"{hi}-{lo}:ibs"]["hi"] < 0)

        results["improves"] = {f"{hi}-{lo}": better(hi, lo) for hi, lo in diffs}
        if args.protocol == "D-016":
            results["beats_mechanical"] = results["improves"]["ABC-M"]

    warnings = [f"{y} {s}: C {m['uno_c']:.3f} > {TOO_GOOD_C}: STOP, run the leakage-audit skill"
                for y in map(str, DEV_FOLDS) for s, m in results[y]["metrics"].items()
                if m["uno_c"] > TOO_GOOD_C]  # fmt: skip
    cfg = {"protocol": args.protocol, "features_run": fr.name, "snapshot_id": fcfg["snapshot_id"],
           "git_commit": commit, "specs": specs, "diffs": diffs, "folds": DEV_FOLDS,
           "horizons": HORIZONS.tolist(), "bootstrap": args.bootstrap, "block": 20,
           **({"block_e": block_e} if block_e else {})}  # fmt: skip
    (run / "config.json").write_text(json.dumps(cfg, indent=2))
    (run / "metrics.json").write_text(json.dumps({"results": results, "warnings": warnings},
                                                 indent=2, default=float))  # fmt: skip
    keys = ("age_share_auc5", "mainly_age_effect", "beats_mechanical", "improves")
    summary = {k: results[k] for k in keys if k in results}
    log(json.dumps({"run_dir": str(run), **summary, "warnings": warnings}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
