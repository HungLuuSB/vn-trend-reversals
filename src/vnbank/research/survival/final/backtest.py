"""Final run, trading test (RQ5; D-021 rules, FINAL_RUN_PROTOCOL.md sections 4 and 5b).

    uv run python -m vnbank.research.survival.final.backtest --cache <dir> --snapshot <id> \
        --final --i-confirm-final-run [--k 2]

Uses the cached 5-day reversal probabilities of ``ABCDx`` (model exit) and ``M`` (mechanical
exit): tau is chosen each year on the inner year from the inner-train fit (as in development),
then applied to the test year. Benchmarks: directional-change exit and buy-and-hold. Main costs
0.40% round trip; sensitivities 0.20% / 0.80%, no trading under unknown limits, sell fails on a
floor close, and execution at the close of t+1 instead of the open (5b; tau re-chosen under the
same execution). Deflated Sharpe ratio with N = 16 (8 tau x 2 hazard strategies); paired
moving-block bootstrap of Sharpe differences (20 sessions; 40 and 60 as D-025 sensitivity).
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
from vnbank.research.shared.config import load
from vnbank.research.shared.run_meta import code_version
from vnbank.research.survival.backtest.dev_backtest import (
    COST_SENS,
    TAUS,
    build_stocks,
    p5_by_stock,
    portfolio,
    summary,
)
from vnbank.research.survival.backtest.metrics import deflated_sharpe, sharpe, sharpe_diff_ci
from vnbank.research.survival.final.evaluate import require_passed_evaluation
from vnbank.research.survival.final.year import load_preds

CFG = load(1)
TEST_YEARS = tuple(CFG["walkforward"]["test_years"])
H = CFG["evaluation"]["main_horizon"]
STUDY_END = pd.Timestamp(CFG["study"]["end"])
HAZARD = {"model": "ABCDx", "mech": "M"}  # D-021: strategy -> cached spec
PAIRS = (("model", "dc"), ("model", "bh"), ("model", "mech"), ("mech", "dc"), ("dc", "bh"))
SUBPERIODS = {"2017-2019": (2017, 2019), "2020-2021": (2020, 2021), "2022": (2022, 2022),
              "2023-2026": (2023, 2026)}  # fmt: skip


def year_window(y: int) -> tuple[pd.Timestamp, pd.Timestamp]:
    return pd.Timestamp(f"{y}-01-01"), min(pd.Timestamp(f"{y}-12-31"), STUDY_END)


def choose_tau(stocks, sessions, inner: pd.DataFrame, spec: str, year: int) -> tuple:
    """Largest net Sharpe on the inner year at 0.40% costs; ties go to the larger tau."""
    ip = p5_by_stock(stocks, inner, inner[f"p5:{spec}"].to_numpy())
    win = year_window(year - 1)
    sh = [sharpe(portfolio(stocks, "model", win, sessions, ip, tau)["daily"].to_numpy())
          for tau in TAUS]  # fmt: skip
    best = max(range(len(TAUS)), key=lambda j: (np.nan_to_num(sh[j], nan=-9), TAUS[j]))
    return TAUS[best], sh


def run_years(stocks, sessions, cache: Path, years, log=print, tag: str = "") -> tuple:
    folds, pooled = {}, {}
    for y in years:
        t0 = time.time()
        d = cache / str(y)
        keys = pd.read_parquet(d / "keys.parquet")
        preds = load_preds(d, "preds")
        inner = pd.read_parquet(d / "inner_p5.parquet")
        inner["trade_date"] = pd.to_datetime(inner.trade_date)
        win = year_window(y)
        mism = sum(int(stocks[t].swing_dir[np.searchsorted(stocks[t].dates, d.to_datetime64())]
                       != v) for t, d, v in keys[["ticker", "trade_date", "swing_dir"]]
                   .itertuples(index=False) if t in stocks)  # fmt: skip
        if mism:
            raise SystemExit(f"{y}: swing_dir differs between the backtest and the cache ({mism})")
        fold = {"tau": {}, "inner_sharpe": {}, "strategies": {}, "sensitivity": {}}
        p5 = {}
        for strat, spec in HAZARD.items():
            fold["tau"][strat], fold["inner_sharpe"][strat] = choose_tau(stocks, sessions, inner,
                                                                         spec, y)  # fmt: skip
            p5[strat] = p5_by_stock(stocks, keys, 1 - preds[spec][:, H - 1])
        res = {s: portfolio(stocks, "model", win, sessions, p5[s], fold["tau"][s]) for s in HAZARD}
        res["dc"] = portfolio(stocks, "dc", win, sessions)
        res["bh"] = portfolio(stocks, "bh", win, sessions)
        for k, v in res.items():
            fold["strategies"][k] = summary(v)
            pooled.setdefault(k, []).append(v["daily"])
        for s in HAZARD:  # all 16 configurations (DSR trials)
            for tau in TAUS:
                v = portfolio(stocks, "model", win, sessions, p5[s], tau)["daily"]
                pooled.setdefault(f"trial:{s}:{tau}", []).append(v)
        for label, c in COST_SENS.items():
            for k in (*HAZARD, "dc", "bh"):
                kw = dict(p5=p5[k], tau=fold["tau"][k]) if k in HAZARD else {}
                v = portfolio(stocks, "model" if k in HAZARD else k, win, sessions, costs=c, **kw)
                fold["sensitivity"][f"{k}@{label}"] = summary(v)
                pooled.setdefault(f"{k}@{label}", []).append(v["daily"])
        for label, kw in (("skip_unknown_limits", {"unknown_limit": "skip"}),
                          ("fail_on_floor_close", {"fail_on_floor_close": True})):  # fmt: skip
            for k in ("model", "dc", "bh"):
                extra = dict(p5=p5["model"], tau=fold["tau"]["model"]) if k == "model" else {}
                v = portfolio(stocks, "model" if k == "model" else k, win, sessions, **extra, **kw)
                fold["sensitivity"][f"{k}@{label}"] = summary(v)
                pooled.setdefault(f"{k}@{label}", []).append(v["daily"])
        folds[str(y)] = fold
        log(f"{tag}{y}: tau model {fold['tau']['model']} mech {fold['tau']['mech']} "
            f"({time.time() - t0:.0f}s)")  # fmt: skip
    return folds, {k: pd.concat(v) for k, v in pooled.items()}


def sharpe_tests(r: np.ndarray, sr0: float) -> float:
    """Probability that the true per-period Sharpe exceeds sr0 (Bailey and Lopez de Prado
    2012/2014): PSR(sr0); the DSR is PSR at the expected maximum of N trials."""
    from scipy import stats

    r = np.asarray(r, float)
    sr = sharpe(r, annualise=False)
    g3, g4 = stats.skew(r), stats.kurtosis(r, fisher=False)
    denom = np.sqrt(max(1e-12, 1 - g3 * sr + (g4 - 1) / 4 * sr**2))
    return float(stats.norm.cdf((sr - sr0) * np.sqrt(len(r) - 1) / denom))


def dsr_for_n(r: np.ndarray, trial_sr: np.ndarray, n: int) -> dict:
    """DSR with N trials; the dispersion of trial Sharpe ratios comes from the trials run."""
    from scipy import stats

    v = np.var(trial_sr, ddof=1)
    g = 0.5772156649015329
    sr0 = np.sqrt(v) * (
        (1 - g) * stats.norm.ppf(1 - 1 / n) + g * stats.norm.ppf(1 - 1 / (n * np.e))
    )
    return {"n": n, "sr0_period": float(sr0), "dsr": sharpe_tests(r, sr0)}


def pooled_results(P: dict, n_boot: int) -> dict:
    out = {k: summary({"daily": P[k], "trades": None, "assumed_fills": None})
           for k in P if not k.startswith("trial:")}  # fmt: skip
    for v in out.values():
        v.pop("trades"), v.pop("assumed_fills")
    trial_sr = [sharpe(P[k].to_numpy(), annualise=False) for k in P if k.startswith("trial:")]
    dsr = {k: deflated_sharpe(P[k].to_numpy(), trial_sr) for k in HAZARD}
    diffs = {f"{a}-{b}": sharpe_diff_ci(P[a].to_numpy(), P[b].to_numpy(), n=n_boot)
             for a, b in PAIRS}  # fmt: skip
    diffs_blocks = {str(blk): {f"{a}-{b}": sharpe_diff_ci(P[a].to_numpy(), P[b].to_numpy(),
                                                         block=blk, n=n_boot)
                               for a, b in PAIRS[:3]} for blk in (40, 60)}  # fmt: skip
    sub = {}
    for name, (a, b) in SUBPERIODS.items():
        sub[name] = {k: sharpe(P[k][(P[k].index.year >= a) & (P[k].index.year <= b)].to_numpy())
                     for k in (*HAZARD, "dc", "bh")}  # fmt: skip
    # D-027 item 3: H5 needs the model exit to beat the DC exit, buy-and-hold AND the M exit
    h5 = bool(all(diffs[f"model-{b}"]["lo"] > 0 for b in ("dc", "bh", "mech")))
    psr = {k: sharpe_tests(P[k].to_numpy(), 0.0) for k in HAZARD}
    return {"pooled": out, "dsr": dsr, "sharpe_diffs": diffs,
            "sharpe_diffs_block_sensitivity": diffs_blocks, "subperiod_sharpe": sub,
            "n_trials": len(trial_sr), "psr": psr, "trial_sharpes": trial_sr,
            "h5_supported": h5}  # fmt: skip


def main(argv: list[str] | None = None) -> int:  # pragma: no cover - CLI wiring
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--cache", required=True, type=Path)
    ap.add_argument("--snapshot", required=True)
    ap.add_argument("--k", type=float, default=CFG["labels"]["k_main"])
    ap.add_argument("--bootstrap", type=int, default=CFG["evaluation"]["bootstrap"]["resamples"])
    ap.add_argument(
        "--evaluate-run",
        required=True,
        type=Path,
        help="the passed final.evaluate run of the same cache (protocol section 6)",
    )
    ap.add_argument("--final", action="store_true")
    ap.add_argument("--i-confirm-final-run", action="store_true")
    a = ap.parse_args(argv)
    if not (a.final and a.i_confirm_final_run):
        raise SystemExit("the final trading test needs --final --i-confirm-final-run (D-026)")
    require_passed_evaluation(a.evaluate_run, cache=a.cache, snapshot=a.snapshot)
    commit = code_version()
    years = sorted(int(p.name) for p in a.cache.iterdir() if p.is_dir() and p.name.isdigit())
    if tuple(years) != TEST_YEARS:
        raise SystemExit(f"caches for {years}, expected every test year {TEST_YEARS}")
    snap = paths.SNAPSHOTS / a.snapshot
    sessions = np.sort(pd.to_datetime(
        pd.read_parquet(snap / "sessions_hose.parquet").trade_date).to_numpy())  # fmt: skip
    tag = f"k{a.k:g}".replace(".", "_")
    run = paths.runs_dir(1) / f"{datetime.now(UTC):%Y%m%dT%H%M%SZ}-final-backtest-{tag}"
    run.mkdir(parents=True)
    logf = open(run / "log.txt", "w")

    def log(msg):
        print(msg, flush=True)
        logf.write(msg + "\n")
        logf.flush()

    out, all_trials = {}, []
    for execution in ("open", "close"):
        stocks = build_stocks(snap, a.k, execution=execution)
        folds, P = run_years(stocks, sessions, a.cache, years, log=log, tag=f"[{execution}] ")
        out[execution] = {"folds": folds, **pooled_results(P, a.bootstrap)}
        all_trials += out[execution]["trial_sharpes"]
        out[execution]["_daily_model"] = P["model"].to_numpy()
        pd.DataFrame({k: v for k, v in P.items() if not k.startswith("trial:")}).to_parquet(
            run / f"daily_returns_{execution}.parquet")  # fmt: skip
    # D-027 item 8: DSR with N = 16 (pre-registered), with every trial of this run (both
    # executions) and with every trial of the final run (k = 2, 1.5, 3, both executions)
    for execution in ("open", "close"):
        r = out[execution].pop("_daily_model")
        out[execution]["dsr_n"] = [dsr_for_n(r, np.array(all_trials), n)
                                   for n in (16, len(all_trials), 3 * len(all_trials))]  # fmt: skip
    cfg = {"protocol": "D-021 / D-026 / D-027", "cache": str(a.cache), "snapshot_id": a.snapshot,
           "k": a.k, "git_commit": commit, "taus": TAUS, "bootstrap": a.bootstrap,
           "years": years, "evaluate_run": a.evaluate_run.name}  # fmt: skip
    (run / "config.json").write_text(json.dumps(cfg, indent=2))
    (run / "metrics.json").write_text(json.dumps(out, indent=1, default=float))
    log(f"done: {run}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
