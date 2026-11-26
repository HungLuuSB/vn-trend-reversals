"""Final run, pooled evaluation (FINAL_RUN_PROTOCOL.md sections 3, 4 and 6; D-026).

    uv run python -m vnbank.research.survival.final.evaluate --cache <dir> \
        --final --i-confirm-final-run

Reads the per-year caches written by ``final.year``. The **stop rules run first** (section 6):
any pooled Uno C above ``too_good_c`` or a shuffled-label control whose mean C lies outside
0.5 +/- 0.03 writes ``STOP.json`` with only those numbers and exits without computing anything
else. Otherwise it writes metrics.json: per-year and pooled metrics for every cached
specification, the pre-registered paired differences with their decision rule (C interval
above zero AND IBS interval below zero), the D-025 block-length sensitivity, the D-018
attribution, Diebold-Mariano tests, the slices of section 5c and the RQ3 shape table.

Pooled IPCW metrics use the last year's training outcomes for the censoring distribution, as
in development.
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
from scipy import stats as sst

from vnbank.common import paths
from vnbank.research.shared.config import load
from vnbank.research.shared.run_meta import code_version
from vnbank.research.survival.aging import empirical
from vnbank.research.survival.dev_attribution import boot_p, holm
from vnbank.research.survival.evaluation.bootstrap import block_resamples
from vnbank.research.survival.evaluation.metrics import calibration, ibs, surv, td_auc, uno_c
from vnbank.research.survival.final import specs as S

CFG = load(1)
TEST_YEARS = tuple(CFG["walkforward"]["test_years"])
TAU = CFG["evaluation"]["tau"]
TIMES = np.arange(1, TAU + 1)
HORIZONS = np.array(CFG["evaluation"]["horizons"])
H = CFG["evaluation"]["main_horizon"]
TOO_GOOD_C = CFG["evaluation"]["too_good_c"]
BOOT = CFG["evaluation"]["bootstrap"]
SHUFFLE_BAND = 0.03  # FINAL_RUN_PROTOCOL.md section 6
ATTRIB_RESAMPLES = 2000  # D-018 amendment
BLOCK_SENS = (40, 60)  # D-025
SUBPERIODS = {"2017-2019": (2017, 2019), "2020-2021": (2020, 2021), "2022": (2022, 2022),
              "2023-2026": (2023, 2026)}  # fmt: skip
SLICE_SPECS = ("km", "M", "ABCDx")
H2_TERMS = ("spx_ret_xdir", "nasdaq_ret_xdir", "vix_chg_xdir")


IDENTITY = (
    "git_commit",
    "snapshot_id",
    "snapshot_manifest_id",
    "features_run",
    "k",
    "dataset_sha256",
)  # every year must come from the same run (D-026)


def load_caches(cache: Path, years) -> dict:
    """Concatenate the years: keys, predictions per spec (same set in every year), training
    outcomes, per-year metas. Refuses years written by different code, snapshot or dataset."""
    from vnbank.research.survival.final.year import load_preds

    out = {"keys": [], "bank_keys": [], "preds": {}, "bank_preds": {}, "year_of": [],
           "bank_year_of": [], "meta": {}, "train_y": {}}  # fmt: skip
    names = bank_names = None
    for y in years:
        d = cache / str(y)
        meta = json.loads((d / "meta.json").read_text())
        out["meta"][y] = meta
        first = out["meta"][years[0]]
        for k in IDENTITY:
            if meta.get(k) != first.get(k):
                raise SystemExit(f"{y}: {k} = {meta.get(k)} differs from {years[0]}'s")
        keys = pd.read_parquet(d / "keys.parquet")
        p = load_preds(d, "preds")
        names = names or set(p)
        if set(p) != names:
            raise SystemExit(f"{y}: cached specs differ from the first year's: "
                             f"{sorted(set(p) ^ names)}")  # fmt: skip
        out["keys"].append(keys)
        out["year_of"].append(np.full(len(keys), y))
        for k, v in p.items():
            out["preds"].setdefault(k, []).append(v)
        bp = load_preds(d, "bank_preds") if (d / "bank_preds").exists() else {}
        bank_names = set(bp) if bank_names is None else bank_names
        if set(bp) != bank_names:
            raise SystemExit(f"{y}: cached block E specs differ from the first year's")
        if bp:
            bk = pd.read_parquet(d / "bank_keys.parquet")
            out["bank_keys"].append(bk)
            out["bank_year_of"].append(np.full(len(bk), y))
            for k, v in bp.items():
                out["bank_preds"].setdefault(k, []).append(v)
            out["train_y"].setdefault("bank", {})[y] = dict(np.load(d / "bank_train_y.npz"))
        out["train_y"][y] = dict(np.load(d / "train_y.npz"))
    out["keys"] = pd.concat(out["keys"], ignore_index=True)
    out["year_of"] = np.concatenate(out["year_of"])
    out["preds"] = {k: np.concatenate(v) for k, v in out["preds"].items()}
    if out["bank_keys"]:
        out["bank_keys"] = pd.concat(out["bank_keys"], ignore_index=True)
        out["bank_year_of"] = np.concatenate(out["bank_year_of"])
        out["bank_preds"] = {k: np.concatenate(v) for k, v in out["bank_preds"].items()}
    return out


def _y(keys: pd.DataFrame):
    return surv(keys.event, keys.duration)


def metrics(y_train, keys: pd.DataFrame, s: np.ndarray) -> dict:
    y = _y(keys)
    out = {"uno_c": uno_c(y_train, y, 1 - s[:, TAU - 1], TAU),
           "ibs": ibs(y_train, y, s, TIMES),
           "td_auc": dict(zip(map(str, HORIZONS), td_auc(y_train, y, 1 - s[:, HORIZONS - 1],
                                                         HORIZONS).round(4).tolist(),
                              strict=True))}  # fmt: skip
    for h in HORIZONS:
        cal = calibration(1 - s[:, h - 1], keys.event.to_numpy(), keys.duration.to_numpy(), h)
        out[f"calibration_{h}d"] = cal.round(4).to_dict("list")
    return out


def stop_checks(c: dict, years) -> dict:
    """Section 6 stop rules, before anything else (D-026 clarification 1):
    - any pooled Uno C (all-row specs and block E specs) above too_good_c;
    - the shuffled-label control, checked per year as in development (each year's model is
      trained on permuted outcomes and scored on that year's test rows): the mean over years of
      the per-year mean C must lie within 0.5 +/- 0.03. Pooled shuffled C is reported only
      (pooling mixes ten models whose risk differs mainly between years)."""
    keys, y_last = c["keys"], _ytrain(c, years[-1])
    y = _y(keys)
    pooled_c = {k: uno_c(y_last, y, 1 - v[:, TAU - 1], TAU)
                for k, v in c["preds"].items() if v.ndim == 2 and v.shape[1] == TAU}  # fmt: skip
    if len(c["bank_keys"]):
        yb, yl = _y(c["bank_keys"]), _ytrain(c, years[-1], bank=True)
        pooled_c.update({k: uno_c(yl, yb, 1 - v[:, TAU - 1], TAU)
                         for k, v in c["bank_preds"].items()})  # fmt: skip
    shuffled = {}
    for k, v in c["preds"].items():
        if not k.startswith("shuffled:"):
            continue
        per_year = {}
        for yr in years:
            m = c["year_of"] == yr
            yy = _y(keys[m])
            per_year[str(yr)] = float(np.mean([uno_c(_ytrain(c, yr), yy, v[m, j], TAU)
                                               for j in range(v.shape[1])]))  # fmt: skip
        shuffled[k] = {"per_year_mean": per_year, "mean": float(np.mean(list(per_year.values()))),
                       "pooled": float(np.mean([uno_c(y_last, y, v[:, j], TAU)
                                                for j in range(v.shape[1])]))}  # fmt: skip
    too_good = {k: v for k, v in pooled_c.items() if v > TOO_GOOD_C}
    bad_shuffle = {k: v["mean"] for k, v in shuffled.items()
                   if abs(v["mean"] - 0.5) > SHUFFLE_BAND}  # fmt: skip
    return {"stop": bool(too_good or bad_shuffle), "too_good_c": too_good,
            "shuffled_outside_band": bad_shuffle, "shuffled": shuffled}  # fmt: skip


def _ytrain(c: dict, year: int, bank: bool = False):
    t = c["train_y"]["bank"][year] if bank else c["train_y"][year]
    return surv(t["event"], t["duration"])


_W: dict = {}  # per-worker state, set once by _init (avoids pickling predictions per task)


def _init(y_train, ev, du, preds, models) -> None:
    _W.update(y_train=y_train, ev=ev, du=du, preds=preds, models=models)


def _one_resample(idx) -> dict[str, tuple[float, float, float]]:
    y_train, preds = _W["y_train"], _W["preds"]
    yi = surv(_W["ev"][idx], _W["du"][idx])
    out = {}
    for m in _W["models"]:
        p = preds[m][idx]
        out[m] = (uno_c(y_train, yi, 1 - p[:, TAU - 1], TAU), ibs(y_train, yi, p, TIMES),
                  float(td_auc(y_train, yi, 1 - p[:, H - 1:H], np.array([H]))[0]))  # fmt: skip
    return out


def resampled(y_train, keys, preds, models, block, n, seed=0, n_jobs=None) -> dict:
    """Each model's (C, IBS, 5-day td-AUC) on the same n moving-block resamples of test dates,
    computed once per model and resample (paired differences are formed afterwards)."""
    import multiprocessing as mp
    import os
    from concurrent.futures import ProcessPoolExecutor

    idxs = list(block_resamples(keys.trade_date.to_numpy(), block, n, seed))
    state = (y_train, keys.event.to_numpy(), keys.duration.to_numpy(),
             {m: preds[m] for m in models}, list(models))  # fmt: skip
    n_jobs = n_jobs or min(8, os.cpu_count() or 2)
    if n_jobs > 1 and n > 1:
        ctx = mp.get_context("forkserver")
        with ProcessPoolExecutor(n_jobs, mp_context=ctx, initializer=_init,
                                 initargs=state) as ex:  # fmt: skip
            rows = list(ex.map(_one_resample, idxs, chunksize=max(1, n // (4 * n_jobs))))
    else:
        _init(*state)
        rows = [_one_resample(i) for i in idxs]
    return {m: np.array([r[m] for r in rows]) for m in models}


def _ci(a: np.ndarray) -> dict:
    a = a[np.isfinite(a)]
    return {"lo": float(np.quantile(a, 0.025)), "hi": float(np.quantile(a, 0.975)),
            "n": int(len(a))}  # fmt: skip


def paired(y_train, keys, preds, diffs, block, n, seed=0, include_levels=True) -> dict:
    """Pre-registered paired differences: 95% percentile intervals on the same resamples;
    an improvement needs the C interval above zero AND the IBS interval below zero."""
    models = sorted({x for d in diffs for x in d})
    r = resampled(y_train, keys, preds, models, block, n, seed)
    ci = {}
    names = ("uno_c", "ibs", "auc5")
    if include_levels:
        for m in models:
            for j, nm in enumerate(names):
                ci[f"{m}:{nm}"] = _ci(r[m][:, j])
    for hi, lo in diffs:
        for j, nm in enumerate(names):
            ci[f"{hi}-{lo}:{nm}"] = _ci(r[hi][:, j] - r[lo][:, j])
    improves = {}
    for hi, lo in diffs:
        d = f"{hi}-{lo}"
        improves[d] = bool(ci[f"{d}:uno_c"]["lo"] > 0 and ci[f"{d}:ibs"]["hi"] < 0)
    return {"ci": ci, "improves": improves, "block": block, "resamples": n}


GOLD_C_MODELS = ("ABCDx", "loo-gold_ret", "loo-gold-gpr")  # D-018 amendment
GOLD_C_RESAMPLES = 200


def attribution(y_train, keys, preds, n=ATTRIB_RESAMPLES, block=BOOT["block"]) -> dict:
    """D-018 as in development (dev_attribution.main): per block-D feature, IBS(without) -
    IBS(ABCDx) on 2,000 paired block resamples (seed 0), two-sided bootstrap p, Holm across the
    14 features, informative if Holm p < 0.05 and the difference > 0; d_c = C(full) -
    C(without) as a point estimate. Gold vs GPR: the four contrasts of D-018 with C intervals
    from 200 resamples for the three gold/GPR models."""
    names = [k for k in preds if k.startswith("loo")]
    ev, du = keys.event.to_numpy(), keys.duration.to_numpy()
    y = _y(keys)
    point = {k: {"ibs": ibs(y_train, y, preds[k], TIMES),
                 "uno_c": uno_c(y_train, y, 1 - preds[k][:, TAU - 1], TAU)}
             for k in ["ABCDx", *names]}  # fmt: skip
    D = {k: {"ibs": [], "uno_c": []} for k in ["ABCDx", *names]}
    dates = keys.trade_date.to_numpy()
    for idx in block_resamples(dates, block, n, seed=0):
        yi = surv(ev[idx], du[idx])
        for k in D:
            D[k]["ibs"].append(ibs(y_train, yi, preds[k][idx], TIMES))
    gold_models = [m for m in GOLD_C_MODELS if m in D]
    for idx in block_resamples(dates, block, GOLD_C_RESAMPLES, seed=0):
        yi = surv(ev[idx], du[idx])
        for k in gold_models:
            D[k]["uno_c"].append(uno_c(y_train, yi, 1 - preds[k][idx, TAU - 1], TAU))
    D = {k: {m: np.asarray(x) for m, x in d.items()} for k, d in D.items()}
    singles = [k for k in names if k != "loo-gold-gpr"]
    rows = {}
    for k in singles:
        d = D[k]["ibs"] - D["ABCDx"]["ibs"]  # > 0: dropping the feature hurts, so it helps
        rows[k] = {"d_ibs": point[k]["ibs"] - point["ABCDx"]["ibs"],
                   "d_ibs_lo": float(np.quantile(d, 0.025)),
                   "d_ibs_hi": float(np.quantile(d, 0.975)), "p_ibs": boot_p(d),
                   "d_c": point["ABCDx"]["uno_c"] - point[k]["uno_c"]}  # fmt: skip
    adj = holm(np.array([rows[k]["p_ibs"] for k in singles]))
    for k, a in zip(singles, adj, strict=True):
        rows[k]["p_ibs_holm"] = float(a)
        rows[k]["informative"] = bool(a < 0.05 and rows[k]["d_ibs"] > 0)

    def ci(a, b, m):
        d = D[a][m] - D[b][m]
        return {"point": float(point[a][m] - point[b][m]), "lo": float(np.quantile(d, 0.025)),
                "hi": float(np.quantile(d, 0.975)), "p": boot_p(d)}  # fmt: skip

    gold = {}
    if {"loo-gold_ret", "loo-gold-gpr"} <= set(D):
        gold = {"gold_given_gpr_ibs": ci("loo-gold_ret", "ABCDx", "ibs"),
                "gpr_given_no_gold_ibs": ci("loo-gold-gpr", "loo-gold_ret", "ibs"),
                "gold_given_gpr_c": ci("ABCDx", "loo-gold_ret", "uno_c"),
                "gpr_given_no_gold_c": ci("loo-gold_ret", "loo-gold-gpr", "uno_c")}  # fmt: skip
    return {"point": point, "leave_one_out": rows, "gold_vs_gpr": gold, "ibs_resamples": n,
            "c_resamples": GOLD_C_RESAMPLES}  # fmt: skip


def diebold_mariano(keys, preds, a: str, b: str, h: int = H, lags: int = BOOT["block"]) -> dict:
    """DM test on the daily mean Brier loss of P(reversal within h days), rows whose h-day
    outcome is known (event, or followed for at least h days). Newey-West variance with
    `lags` = the bootstrap block length (20 sessions), two-sided normal p-value."""
    known = ((keys.event == 1) | (keys.duration >= h)).to_numpy()
    k = keys[known]
    y = ((k.event == 1) & (k.duration <= h)).to_numpy(float)
    la = (y - (1 - preds[a][known, h - 1])) ** 2
    lb = (y - (1 - preds[b][known, h - 1])) ** 2
    d = pd.Series(la - lb).groupby(k.trade_date.to_numpy()).mean().to_numpy()
    T = len(d)
    u = d - d.mean()
    v = u @ u / T
    for j in range(1, min(lags, T - 1) + 1):
        v += 2 * (1 - j / (lags + 1)) * (u[j:] @ u[:-j]) / T
    stat = d.mean() / np.sqrt(v / T) if v > 0 else float("nan")
    return {"mean_loss_diff": float(d.mean()), "dm": float(stat),
            "p": float(2 * sst.norm.sf(abs(stat))), "days": int(T)}  # fmt: skip


def slices(keys, year_of) -> dict[str, np.ndarray]:
    out = {name: (year_of >= a) & (year_of <= b) for name, (a, b) in SUBPERIODS.items()}
    out["banks"] = keys.is_bank.astype(bool).to_numpy()
    out["vn30_non_banks"] = (keys.in_vn30.astype(bool) & ~keys.is_bank.astype(bool)).to_numpy()
    # rule 6: never guess a limit; rows whose last 5 days all had a known limit
    out["no_limit_close"] = ((keys.close_at_limit.fillna(0) == 0)
                             & (keys.limit_known_5 == 1)).to_numpy()  # fmt: skip
    return out


def evaluate(c: dict, years, n_boot: int = BOOT["resamples"], log=print,
             strict: bool = False) -> dict:  # fmt: skip
    """strict (the main run): every pre-registered comparison must be computable."""
    keys, preds = c["keys"], c["preds"]
    y_last = _ytrain(c, years[-1])
    stop = stop_checks(c, years)
    if stop["stop"]:
        return {"STOP": stop}
    if strict:
        need = {x for d in S.DIFFS for x in d} | {f"shuffled:{k}" for k in S.SHUFFLED}
        need |= {f"loo{k}" for k in S.LOO} | {f"boundary:{b}" for b in S.BOUNDARY}
        bneed = {x for d in S.BANK_DIFFS for x in d}
        bneed |= {f"{n}@{v}" for n in S.E_VARIANT_SPECS for v in S.E_VARIANTS}
        missing = sorted(need - set(preds)) + sorted(bneed - set(c["bank_preds"] or {}))
        if missing:
            raise SystemExit(f"pre-registered specs missing from the cache: {missing}")
    res = {"stop_checks": stop, "per_year": {}, "pooled": {}}
    main = {k: v for k, v in preds.items() if v.ndim == 2 and v.shape[1] == TAU}
    for y in years:
        m = c["year_of"] == y
        yt = _ytrain(c, y)
        kk = keys[m].reset_index(drop=True)
        res["per_year"][str(y)] = {k: metrics(yt, kk, p[m]) for k, p in main.items()
                                   if not k.startswith("loo")}  # fmt: skip
        log(f"  per-year metrics {y}")
    res["pooled"]["metrics"] = {k: metrics(y_last, keys, p) for k, p in main.items()
                                if not k.startswith("loo")}  # fmt: skip
    diffs = [d for d in S.DIFFS if d[0] in preds and d[1] in preds]
    res["pooled"]["paired"] = paired(y_last, keys, preds, diffs, BOOT["block"], n_boot)
    log("  pooled paired differences")
    res["pooled"]["paired_block_sensitivity"] = {
        str(b): paired(y_last, keys, preds, diffs, b, n_boot, include_levels=False)
        for b in BLOCK_SENS}  # fmt: skip
    bd = [(f"boundary:{a}", f"boundary:{b}") for a, b in S.DIFFS
          if f"boundary:{a}" in preds and f"boundary:{b}" in preds]  # fmt: skip
    if bd:
        res["pooled"]["paired_boundary_censoring"] = paired(y_last, keys, preds, bd,
                                                            BOOT["block"], n_boot)  # fmt: skip
    if any(k.startswith("loo") for k in preds):
        res["pooled"]["attribution_d018"] = attribution(y_last, keys, preds)
        log("  D-018 attribution")
    res["pooled"]["diebold_mariano"] = {f"{a}-{b}": diebold_mariano(keys, preds, a, b)
                                        for a, b in diffs}  # fmt: skip
    sl = {}
    for name, m in slices(keys, c["year_of"]).items():
        kk = keys[m].reset_index(drop=True)
        pp = {k: preds[k][m] for k in SLICE_SPECS if k in preds}
        if len(kk) < 100 or len(pp) < len(SLICE_SPECS):
            continue
        sl[name] = {"n": int(m.sum()),
                    "metrics": {k: {x: v for x, v in metrics(y_last, kk, p).items()
                                    if not x.startswith("calibration")} for k, p in pp.items()},
                    "paired": paired(y_last, kk, pp, [("ABCDx", "km"), ("ABCDx", "M")],
                                     BOOT["block"], n_boot, include_levels=False)}  # fmt: skip
    res["pooled"]["slices"] = sl
    log("  slices")
    if len(c["bank_keys"]):
        bk, bp = c["bank_keys"], c["bank_preds"]
        yb = _ytrain(c, years[-1], bank=True)
        bdiffs = [d for d in S.BANK_DIFFS if d[0] in bp and d[1] in bp]
        for v in S.E_VARIANTS:
            bdiffs += [(f"{a}@{v}", b) for a, b in S.BANK_DIFFS if f"{a}@{v}" in bp]
        per_year = {}
        for y in years:
            m = c["bank_year_of"] == y
            kk = bk[m].reset_index(drop=True)
            per_year[str(y)] = {k: metrics(_ytrain(c, y, bank=True), kk, p[m])
                                for k, p in bp.items()}  # fmt: skip
        res["pooled"]["block_e"] = {
            "metrics": {k: metrics(yb, bk, p) for k, p in bp.items()},
            "per_year": per_year,
            "paired": paired(yb, bk, bp, bdiffs, BOOT["block"], n_boot),
            "paired_block_sensitivity": {str(b): paired(yb, bk, bp, bdiffs, b, n_boot,
                                                        include_levels=False)
                                         for b in BLOCK_SENS},
            "diebold_mariano": {f"{a}-{b}": diebold_mariano(bk, bp, a, b) for a, b in bdiffs},
        }  # fmt: skip
        log("  block E")
    res["h2_coefficients"] = {str(y): {t: c["meta"][y].get("abcdx_coef_std", {}).get(t)
                                       for t in H2_TERMS} for y in years}  # fmt: skip
    res["rq3_shape"] = empirical(keys).to_dict("list")
    res["chosen"] = {str(y): c["meta"][y]["chosen"] for y in years}
    return res


def require_passed_evaluation(run_dir: Path, cache: Path | None = None,
                              snapshot: str | None = None) -> dict:  # fmt: skip
    """Protocol section 6: later steps (trading test, RQ4) run only after an evaluation of the
    same cache and snapshot finished without a stop rule firing."""
    run_dir = Path(run_dir)
    if (run_dir / "STOP.json").exists():
        raise SystemExit(f"{run_dir.name}: a stop rule fired; run the leakage-audit skill")
    if not (run_dir / "metrics.json").exists():
        raise SystemExit(f"{run_dir.name}: no completed evaluation (metrics.json missing)")
    cfg = json.loads((run_dir / "config.json").read_text())
    if cache is not None and Path(cfg["cache"]).resolve() != Path(cache).resolve():
        raise SystemExit(f"evaluation {run_dir.name} is of {cfg['cache']}, not {cache}")
    if snapshot is not None and set(cfg["snapshot_id"].values()) != {snapshot}:
        raise SystemExit(f"evaluation {run_dir.name} used snapshot {cfg['snapshot_id']}")
    return cfg


def main(argv: list[str] | None = None) -> int:  # pragma: no cover - CLI wiring
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--cache", required=True, type=Path)
    ap.add_argument("--final", action="store_true")
    ap.add_argument("--i-confirm-final-run", action="store_true")
    ap.add_argument("--label", default="main")
    a = ap.parse_args(argv)
    if not (a.final and a.i_confirm_final_run):
        raise SystemExit("the final evaluation needs --final --i-confirm-final-run (D-026)")
    commit = code_version()
    years = sorted(int(p.name) for p in a.cache.iterdir() if p.is_dir() and p.name.isdigit())
    if tuple(years) != TEST_YEARS:
        raise SystemExit(f"caches for {years}, expected every test year {TEST_YEARS}")
    run = paths.runs_dir(1) / f"{datetime.now(UTC):%Y%m%dT%H%M%SZ}-final-evaluate-{a.label}"
    run.mkdir(parents=True)
    logf = open(run / "log.txt", "w")

    def log(msg):
        print(msg, flush=True)
        logf.write(msg + "\n")
        logf.flush()

    t0 = time.time()
    c = load_caches(a.cache, years)
    res = evaluate(c, years, log=log, strict=a.label == "main")
    metas = c["meta"]
    cfg = {"git_commit": commit, "cache": str(a.cache), "years": years,
           "year_commits": {y: metas[y].get("git_commit") for y in years},
           "snapshot_id": {y: metas[y].get("snapshot_id") for y in years},
           "machines": {y: metas[y].get("machine") for y in years},
           "protocol": "D-026"}  # fmt: skip
    (run / "config.json").write_text(json.dumps(cfg, indent=2, default=str))
    if "STOP" in res:
        (run / "STOP.json").write_text(json.dumps(res["STOP"], indent=2, default=float))
        log("STOP: a section-6 stop rule fired; run the leakage-audit skill before anything else")
        return 2
    (run / "metrics.json").write_text(json.dumps(res, indent=1, default=float))
    log(f"done in {time.time() - t0:.0f}s: {run}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
