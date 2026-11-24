"""Walk-forward runner (CLAUDE.md research rules; docs/proposal.md, Evaluation design).

    uv run python -m research.walkforward --features-run <research/runs/...-features-...>

Development mode (default; research/DECISIONS.md D-012): evaluation stays inside the first
training window (sessions <= 2016-12-31). Folds validate on 2014, 2015 and 2016 in turn, each
with an expanding training window from 2012:
  - purge: training rows whose swing ends (event or censoring) on/after the fold start
  - embargo: training rows in the 20 HOSE sessions before the fold start
  - validation labels reaching past 2016-12-31 are censored there (no test-year prices)
Models: Kaplan-Meier baseline (no features), discrete-time logistic hazard on blocks A-D, and
the same hazard model trained on shuffled labels (control: C-index ~ 0.5).

Final mode (`--final --i-confirm-final-run`) evaluates test years 2017-2026. It is the only
thing allowed to touch test years and must not be run during development.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pandas as pd

from research.eval.metrics import calibration, ibs, surv, td_auc, uno_c
from research.features.assemble import BLOCKS
from research.models.hazard import LogisticHazard
from research.models.km import KaplanMeier

REPO = Path(__file__).resolve().parents[1]
DEV_END = pd.Timestamp("2016-12-31")
DEV_FOLDS = (2014, 2015, 2016)
EMBARGO_SESSIONS = 20
HORIZONS = np.array([5, 10, 20])
IBS_TIMES = np.arange(1, 21)
TAU = 20
TOO_GOOD_C = 0.70  # CLAUDE.md: a C-index far above the baseline -> stop, run leakage-audit


def split(ds: pd.DataFrame, sessions: np.ndarray, val_year: int, dev: bool):
    start = pd.Timestamp(f"{val_year}-01-01")
    end = pd.Timestamp(f"{val_year}-12-31")
    k = np.searchsorted(sessions, start.to_datetime64())
    embargo_start = sessions[max(0, k - EMBARGO_SESSIONS)]
    train = ds[(ds.trade_date < embargo_start) & (ds.end_date < start)]
    val = ds[(ds.trade_date >= start) & (ds.trade_date <= end)].copy()
    if dev:
        # censor validation labels at the end of the development window
        past = val.end_date > DEV_END
        val.loc[past, "event"] = 0
        val.loc[past, "duration"] = val.loc[past, "days_to_dev_end"]
        val = val[val.duration > 0]
    return train, val


def shuffled_controls(train, val, features, seeds) -> dict:
    """Shuffled-label control over several seeds. A single shuffle is noisy because validation
    rows of one swing are strongly correlated; the check uses the mean over seeds."""
    ytr, yva = surv(train.event, train.duration), surv(val.event, val.duration)
    cs = []
    for seed in seeds:
        perm = np.random.default_rng(seed).permutation(len(train))
        m = LogisticHazard(features, seed=seed).fit(
            train, train.duration.to_numpy()[perm], train.event.to_numpy()[perm]
        )
        cs.append(uno_c(ytr, yva, 1 - m.survival(val, np.array([TAU]))[:, 0], TAU))
    cs = np.array(cs)
    return {"seeds": list(seeds), "uno_c": cs.round(4).tolist(), "mean": float(cs.mean()),
            "sd": float(cs.std(ddof=1)) if len(cs) > 1 else float("nan")}  # fmt: skip


def evaluate(train: pd.DataFrame, val: pd.DataFrame, features: list[str], seed: int) -> dict:
    ytr, yva = surv(train.event, train.duration), surv(val.event, val.duration)
    out = {"n_train": len(train), "n_val": len(val), "val_event_share": float(val.event.mean())}

    km = KaplanMeier().fit(train.duration, train.event)
    s_km = np.tile(km.survival(IBS_TIMES), (len(val), 1))
    out["km"] = {"uno_c": uno_c(ytr, yva, np.zeros(len(val)), TAU),
                 "ibs": ibs(ytr, yva, s_km, IBS_TIMES),
                 "p_event_5d": float(1 - km.survival(5))}  # fmt: skip

    perm = np.random.default_rng(seed).permutation(len(train))
    outcomes = {
        "hazard": (train.duration.to_numpy(), train.event.to_numpy()),
        # D-013: permute the (duration, event) pairs across rows, then expand
        "shuffled": (train.duration.to_numpy()[perm], train.event.to_numpy()[perm]),
    }
    for name, (dur, ev) in outcomes.items():
        m = LogisticHazard(features, seed=seed).fit(train, dur, ev)
        s = m.survival(val, IBS_TIMES)
        risk = 1 - s[:, TAU - 1]
        res = {"uno_c": uno_c(ytr, yva, risk, TAU), "ibs": ibs(ytr, yva, s, IBS_TIMES)}
        if name == "hazard":
            auc = td_auc(ytr, yva, 1 - s[:, HORIZONS - 1], HORIZONS).round(4)
            res["td_auc"] = dict(zip(map(str, HORIZONS), auc, strict=True))
            cal = calibration(1 - s[:, 4], val.event.to_numpy(), val.duration.to_numpy(), 5)
            res["calibration_5d"] = cal.round(4).to_dict("list")
        out[name] = res
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--features-run", required=True)
    parser.add_argument("--blocks", default="ABCD", help="feature blocks, e.g. ABC for ablation")
    parser.add_argument("--final", action="store_true")
    parser.add_argument("--i-confirm-final-run", action="store_true")
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--shuffle-seeds", type=int, default=10,
                        help="number of shuffled-label controls per fold")  # fmt: skip
    args = parser.parse_args(argv)
    if args.final and not args.i_confirm_final_run:
        raise SystemExit("final mode touches test years 2017-2026; it needs --i-confirm-final-run")
    if args.final:
        raise SystemExit("final mode is not enabled yet: it is reserved for the final run")

    fr = Path(args.features_run)
    ds = pd.read_parquet(fr / "dataset.parquet")
    fcfg = json.loads((fr / "config.json").read_text())
    snap = REPO / "research" / "snapshots" / fcfg["snapshot_id"]
    sessions = np.sort(pd.to_datetime(
        pd.read_parquet(snap / "sessions_hose.parquet").trade_date).to_numpy())  # fmt: skip
    ds = ds[ds.trade_date <= DEV_END]  # development: nothing after the first training window
    features = [c for b in args.blocks for c in BLOCKS[b]]

    folds = {}
    for year in DEV_FOLDS:
        train, val = split(ds, sessions, year, dev=True)
        folds[str(year)] = evaluate(train, val, features, args.seed)
        f = folds[str(year)]
        f["shuffled_multi"] = shuffled_controls(train, val, features, range(args.shuffle_seeds))
        print(f"{year}: train {f['n_train']:,} val {f['n_val']:,} | C km {f['km']['uno_c']:.3f} "
              f"hazard {f['hazard']['uno_c']:.3f} shuffled {f['shuffled_multi']['mean']:.3f}"
              f"±{f['shuffled_multi']['sd']:.3f} | IBS km "
              f"{f['km']['ibs']:.4f} hazard {f['hazard']['ibs']:.4f}", flush=True)  # fmt: skip

    warnings = []
    for y, f in folds.items():
        if f["hazard"]["uno_c"] > TOO_GOOD_C:
            warnings.append(f"{y}: C-index {f['hazard']['uno_c']:.3f} > {TOO_GOOD_C}: STOP, run "
                            "the leakage-audit skill before using this result")  # fmt: skip
        sm = f["shuffled_multi"]
        se = sm["sd"] / np.sqrt(len(sm["seeds"]))
        if abs(sm["mean"] - 0.5) > max(0.02, 3 * se):
            warnings.append(f"{y}: mean shuffled-label C-index {sm['mean']:.3f} is not ~0.5: "
                            "investigate leakage")  # fmt: skip
    commit = subprocess.run(["git", "rev-parse", "HEAD"], cwd=REPO, capture_output=True,
                            text=True, check=True).stdout.strip()  # fmt: skip
    run = (
        REPO
        / "research"
        / "runs"
        / (f"{datetime.now(UTC):%Y%m%dT%H%M%SZ}-walkforward-dev-{args.blocks}")
    )
    run.mkdir(parents=True)
    cfg = {"mode": "dev", "features_run": fr.name, "snapshot_id": fcfg["snapshot_id"],
           "git_commit": commit, "blocks": args.blocks, "features": features,
           "folds": DEV_FOLDS, "embargo_sessions": EMBARGO_SESSIONS, "tau": TAU,
           "model": {"logistic_hazard": {"C": 1.0, "l1_ratio": 0.5}},
           "seed": args.seed}  # fmt: skip
    (run / "config.json").write_text(json.dumps(cfg, indent=2))
    metrics = {"folds": folds, "warnings": warnings}
    (run / "metrics.json").write_text(json.dumps(metrics, indent=2, default=float))
    print(json.dumps({"run_dir": str(run), "warnings": warnings}, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
