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


def load_caches(cache: Path, years) -> dict:
    """Concatenate the years: keys, predictions per spec (same set in every year), the last
    year's training outcomes, per-year metas."""
    out = {"keys": [], "bank_keys": [], "preds": {}, "bank_preds": {}, "year_of": [],
           "bank_year_of": [], "meta": {}, "train_y": {}}  # fmt: skip
    names = None
    for y in years:
        d = cache / str(y)
        keys = pd.read_parquet(d / "keys.parquet")
        p = np.load(d / "preds.npz")
        if names is None:
            names = set(p.files)
        elif set(p.files) != names:
            raise SystemExit(f"{y}: cached specs differ from the first year's")
        out["keys"].append(keys)
        out["year_of"].append(np.full(len(keys), y))
        for k in p.files:
            out["preds"].setdefault(k, []).append(p[k])
        if (d / "bank_preds.npz").exists():
            bk = pd.read_parquet(d / "bank_keys.parquet")
            out["bank_keys"].append(bk)
            out["bank_year_of"].append(np.full(len(bk), y))
            bp = np.load(d / "bank_preds.npz")
            for k in bp.files:
                out["bank_preds"].setdefault(k, []).append(bp[k])
        out["train_y"][y] = dict(np.load(d / "train_y.npz"))
        out["meta"][y] = json.loads((d / "meta.json").read_text())
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


def stop_checks(c: dict, keys, y_train) -> dict:
    """Section 6 stop rules on pooled test rows; nothing else is computed before these."""
    y = _y(keys)
    pooled_c = {k: uno_c(y_train, y, 1 - v[:, TAU - 1], TAU)
                for k, v in c["preds"].items() if v.ndim == 2 and v.shape[1] == TAU}  # fmt: skip
    shuffled = {}
    for k, v in c["preds"].items():
        if k.startswith("shuffled:"):
            cs = [uno_c(y_train, y, v[:, j], TAU) for j in range(v.shape[1])]
            shuffled[k] = {"values": np.round(cs, 4).tolist(), "mean": float(np.mean(cs))}
    too_good = {k: v for k, v in pooled_c.items() if v > TOO_GOOD_C}
    bad_shuffle = {k: v["mean"] for k, v in shuffled.items()
                   if abs(v["mean"] - 0.5) > SHUFFLE_BAND}  # fmt: skip
    return {"stop": bool(too_good or bad_shuffle), "too_good_c": too_good,
            "shuffled_outside_band": bad_shuffle, "shuffled": shuffled}  # fmt: skip


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


def attribution(y_train, keys, preds, n=ATTRIB_RESAMPLES, block=BOOT["block"]) -> dict:
    """D-018: per block-D feature, IBS(without) - IBS(ABCDx) on 2,000 paired block resamples,
    two-sided bootstrap p-value, Holm across the 14 features; C differences as points."""
    names = [k for k in preds if k.startswith("loo")]
    ev, du = keys.event.to_numpy(), keys.duration.to_numpy()
    y = _y(keys)
    base_ibs = ibs(y_train, y, preds["ABCDx"], TIMES)
    base_c = uno_c(y_train, y, 1 - preds["ABCDx"][:, TAU - 1], TAU)
    draws = {k: [] for k in names}
    for idx in block_resamples(keys.trade_date.to_numpy(), block, n, seed=1):
        yi = surv(ev[idx], du[idx])
        b0 = ibs(y_train, yi, preds["ABCDx"][idx], TIMES)
        for k in names:
            draws[k].append(ibs(y_train, yi, preds[k][idx], TIMES) - b0)
    out = {}
    singles = [k for k in names if k != "loo-gold-gpr"]
    p = np.array([boot_p(np.array(draws[k])) for k in singles])
    adj = dict(zip(singles, holm(p), strict=True))
    for k in names:
        d = np.array(draws[k])
        out[k] = {"d_ibs": ibs(y_train, y, preds[k], TIMES) - base_ibs,
                  "d_ibs_lo": float(np.quantile(d, 0.025)),
                  "d_ibs_hi": float(np.quantile(d, 0.975)), "p": boot_p(d),
                  "p_holm": float(adj.get(k, np.nan)),
                  "d_uno_c": uno_c(y_train, y, 1 - preds[k][:, TAU - 1], TAU) - base_c}  # fmt: skip
        out[k]["informative"] = bool(k in adj and adj[k] < 0.05 and out[k]["d_ibs"] > 0)
    return out


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
    out["no_limit_close"] = (keys.close_at_limit.fillna(0) == 0).to_numpy()
    return out


def evaluate(c: dict, years, n_boot: int = BOOT["resamples"], log=print) -> dict:
    keys, preds = c["keys"], c["preds"]
    y_last = surv(c["train_y"][years[-1]]["event"], c["train_y"][years[-1]]["duration"])
    stop = stop_checks(c, keys, y_last)
    if stop["stop"]:
        return {"STOP": stop}
    res = {"stop_checks": stop, "per_year": {}, "pooled": {}}
    main = {k: v for k, v in preds.items() if v.ndim == 2 and v.shape[1] == TAU}
    for y in years:
        m = c["year_of"] == y
        yt = surv(c["train_y"][y]["event"], c["train_y"][y]["duration"])
        kk = keys[m].reset_index(drop=True)
        res["per_year"][str(y)] = {k: {kk2: v for kk2, v in metrics(yt, kk, p[m]).items()
                                       if not kk2.startswith("calibration")}
                                   for k, p in main.items() if not k.startswith("loo")}  # fmt: skip
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
        yb = surv(c["train_y"][years[-1]]["bank_event"], c["train_y"][years[-1]]["bank_duration"])
        bdiffs = [d for d in S.BANK_DIFFS if d[0] in bp and d[1] in bp]
        for v in S.E_VARIANTS:
            bdiffs += [(f"{a}@{v}", b) for a, b in S.BANK_DIFFS if f"{a}@{v}" in bp]
        res["pooled"]["block_e"] = {
            "metrics": {k: {x: y for x, y in metrics(yb, bk, p).items()
                            if not x.startswith("calibration")} for k, p in bp.items()},
            "paired": paired(yb, bk, bp, bdiffs, BOOT["block"], n_boot)}  # fmt: skip
        log("  block E")
    res["h2_coefficients"] = {str(y): {t: c["meta"][y].get("abcdx_coef_std", {}).get(t)
                                       for t in H2_TERMS} for y in years}  # fmt: skip
    res["rq3_shape"] = empirical(keys).to_dict("list")
    res["chosen"] = {str(y): c["meta"][y]["chosen"] for y in years}
    return res


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
    res = evaluate(c, years, log=log)
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
