"""H2 directional and bank parts (D-027 item 5): explanatory, in-sample evidence, not
forecasting evidence.

    uv run python -m vnbank.research.survival.final.h2 --features-run <dir> \
        --cache <main cache> --evaluate-run <passed evaluation> --final --i-confirm-final-run

Full-sample landmark logit on ``ABCDx_bank`` (rows 2012 to 2026-11-20, labels censored at the
study end), ridge C = 100 only for convergence, date-clustered and two-way (date x ticker)
errors, the larger p deciding. Pre-registered signs, one-sided, Holm across the three:
``spx_ret_xdir`` < 0, ``nasdaq_ret_xdir`` < 0, ``vix_chg_xdir`` > 0. Bank part: joint Wald test
of the six ``bank_x_*`` terms. Descriptive: how many yearly ABCDx fits have each predicted sign
(binomial test against one half).
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats as sst

from vnbank.common import paths
from vnbank.research.shared.config import load
from vnbank.research.shared.run_meta import code_version
from vnbank.research.survival.dev_attribution import holm
from vnbank.research.survival.final import rq4
from vnbank.research.survival.final.specs import SPECS

CFG = load(1)
FEATS = SPECS["ABCDx_bank"][1]
SIGNS = {"spx_ret_xdir": -1, "nasdaq_ret_xdir": -1, "vix_chg_xdir": +1}
BANK_TERMS = [f for f in FEATS if f.startswith("bank_x_")]


def run(ds: pd.DataFrame, sessions: np.ndarray, end: pd.Timestamp) -> dict:
    d = rq4.censor_at(ds, sessions, end)
    X, y, g, t, _, _ = rq4.landmark(d, FEATS)
    b, Vd, V2 = rq4.fit_clustered(X, y, g, t)
    signs = {f: rq4.one_sided(b, Vd, V2, FEATS.index(f), s) for f, s in SIGNS.items()}
    adj = holm(np.array([v["p"] for v in signs.values()]))
    for v, a in zip(signs.values(), adj, strict=True):
        v["p_holm"] = float(a)
        v["supported"] = bool(a < 0.05)
    bank = rq4.joint_wald(b, Vd, V2, [FEATS.index(f) for f in BANK_TERMS])
    coef = dict(zip(FEATS, np.round(b[: len(FEATS)], 6).tolist(), strict=True))
    return {"signs": signs, "bank_joint": bank, "bank_terms": BANK_TERMS, "rows": int(len(d)),
            "coef_std": coef}  # fmt: skip


def yearly_sign_counts(metas: dict) -> dict:
    out = {}
    for f, s in SIGNS.items():
        v = [m.get("abcdx_coef_std", {}).get(f) for m in metas.values()]
        v = [x for x in v if x is not None]
        hits = sum(np.sign(x) == s for x in v)
        nz = sum(x != 0 for x in v)
        p = float(sst.binomtest(hits, nz, 0.5, alternative="greater").pvalue) if nz else None
        out[f] = {"predicted_sign_years": int(hits), "nonzero_years": int(nz), "years": len(v),
                  "binomial_p": p}  # fmt: skip
    return out


def main(argv: list[str] | None = None) -> int:  # pragma: no cover - CLI wiring
    from vnbank.research.survival.features.assemble import (
        add_bank_interactions,
        add_direction_interactions,
    )
    from vnbank.research.survival.final.evaluate import require_passed_evaluation

    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--features-run", required=True)
    ap.add_argument("--cache", required=True, type=Path)
    ap.add_argument("--evaluate-run", required=True, type=Path)
    ap.add_argument("--final", action="store_true")
    ap.add_argument("--i-confirm-final-run", action="store_true")
    a = ap.parse_args(argv)
    if not (a.final and a.i_confirm_final_run):
        raise SystemExit("H2 uses the test years: it needs --final --i-confirm-final-run")
    fr = Path(a.features_run)
    fcfg = json.loads((fr / "config.json").read_text())
    require_passed_evaluation(a.evaluate_run, cache=a.cache, snapshot=fcfg["snapshot_id"])
    commit = code_version()
    snap = paths.SNAPSHOTS / fcfg["snapshot_id"]
    sessions = np.sort(pd.to_datetime(
        pd.read_parquet(snap / "sessions_hose.parquet").trade_date).to_numpy())  # fmt: skip
    ds = add_bank_interactions(add_direction_interactions(pd.read_parquet(fr / "dataset.parquet")))
    ds["trade_date"], ds["end_date"] = pd.to_datetime(ds.trade_date), pd.to_datetime(ds.end_date)
    res = run(ds, sessions, pd.Timestamp(CFG["study"]["end"]))
    metas = {p.name: json.loads((p / "meta.json").read_text())
             for p in sorted(a.cache.iterdir()) if p.is_dir() and p.name.isdigit()}  # fmt: skip
    res["yearly_signs"] = yearly_sign_counts(metas)
    run_dir = paths.runs_dir(1) / f"{datetime.now(UTC):%Y%m%dT%H%M%SZ}-final-h2"
    run_dir.mkdir(parents=True)
    (run_dir / "config.json").write_text(json.dumps({
        "git_commit": commit, "features_run": fr.name, "snapshot_id": fcfg["snapshot_id"],
        "evaluate_run": a.evaluate_run.name, "signs": SIGNS, "ridge_C": rq4.RIDGE_C,
        "protocol": "D-027 item 5"}, indent=2))  # fmt: skip
    (run_dir / "metrics.json").write_text(json.dumps(res, indent=1, default=float))
    print(f"done: {run_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
