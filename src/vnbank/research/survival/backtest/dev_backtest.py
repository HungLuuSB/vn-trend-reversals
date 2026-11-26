"""Trading test (RQ5) on development data, 2014-2016 only (DECISIONS.md D-021).

    uv run python -m vnbank.research.survival.backtest.dev_backtest \\
        --features-run <dir> --d017-run <dir> --d016-run <dir>

Per outer fold: the main linear model (ABCDx, D-017 hyperparameters) and the mechanical
baseline M (D-016 hyperparameters) are refitted on the fold's training rows. The exit
threshold tau is chosen on the inner validation year by net Sharpe at 0.40% costs. The fold
year is then simulated for the model exit, the mechanical exit, the directional-change exit
and buy-and-hold, with cost and fill sensitivities.
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
from vnbank.research.survival.backtest.engine import Costs, StockDays, simulate
from vnbank.research.survival.backtest.metrics import (
    ann_return,
    deflated_sharpe,
    max_drawdown,
    sharpe,
    sharpe_diff_ci,
)
from vnbank.research.survival.dev_decompose import SPECS_D017
from vnbank.research.survival.features.assemble import FEATURES_MECH, add_direction_interactions
from vnbank.research.survival.models.zoo import make_model
from vnbank.research.survival.walkforward import DEV_END, DEV_FOLDS, split
from vnbank.research.swings.directional_change import label_series

CFG = load(1)
RUNS = paths.runs_dir(1)
H = CFG["evaluation"]["main_horizon"]
BT = CFG["backtest"]  # D-021
TAUS = list(BT["tau_grid"])
MAIN = Costs.round_trip(BT["round_trip_cost"], BT["sales_tax"])
COST_SENS = {f"{c:.1%}": Costs.round_trip(c, BT["sales_tax"]) for c in BT["cost_sensitivity"]}


def build_stocks(snap: Path, k: float) -> dict[str, StockDays]:
    adj = pd.read_parquet(snap / "prices_adjusted.parquet",
                          columns=["ticker", "trade_date", "open_adj", "high_adj", "low_adj",
                                   "close_adj"])  # fmt: skip
    lim = pd.read_parquet(snap / "price_limits.parquet",
                          columns=["ticker", "trade_date", "open_vnd", "ceiling_price",
                                   "floor_price", "limit_status", "close_at_floor"])  # fmt: skip
    raw = pd.read_parquet(snap / "prices_raw.parquet",
                          columns=["ticker", "trade_date", "open_vnd", "n_prior_days"])  # fmt: skip
    uni = pd.read_parquet(snap / "universe_daily.parquet", columns=["ticker", "trade_date"])
    ses = pd.read_parquet(snap / "sessions_hose.parquet", columns=["trade_date", "session_no"])
    for d in (adj, lim, raw, uni, ses):
        d["trade_date"] = pd.to_datetime(d.trade_date)
    px = (adj.merge(raw, on=["ticker", "trade_date"], how="left")
             .merge(lim.drop(columns="open_vnd"), on=["ticker", "trade_date"], how="left")
             .merge(ses, on="trade_date", how="left"))  # fmt: skip
    uni["in_uni"] = True
    px = px.merge(uni, on=["ticker", "trade_date"], how="left")
    min_hist = CFG["risk_set"]["min_history_days"]
    out = {}
    for t, g in px.groupby("ticker", sort=True):
        g = g.sort_values("trade_date").reset_index(drop=True)
        if g.session_no.isna().any():
            g = g[g.session_no.notna()].reset_index(drop=True)
        lab = label_series(g.high_adj, g.low_adj, g.close_adj, k=k)
        known = (g.limit_status == "computed").to_numpy()
        out[t] = StockDays(
            dates=g.trade_date.to_numpy(), session=g.session_no.to_numpy(dtype="int64"),
            open_adj=g.open_adj.to_numpy(float), open_raw=g.open_vnd.to_numpy(float),
            ceiling=np.where(known, g.ceiling_price, np.nan),
            floor=np.where(known, g.floor_price, np.nan), limit_known=known,
            close_at_floor=g.close_at_floor.fillna(False).to_numpy(bool),
            eligible=(g.in_uni.fillna(False) & (g.n_prior_days >= min_hist)).to_numpy(bool),
            swing_dir=np.asarray(lab.direction),
        )  # fmt: skip
    return out


def p5_by_stock(stocks, rows: pd.DataFrame, p5: np.ndarray) -> dict[str, np.ndarray]:
    s = pd.Series(p5, index=pd.MultiIndex.from_arrays([rows.ticker, rows.trade_date]))
    out = {}
    for t, sd in stocks.items():
        if t in s.index.get_level_values(0):
            st = s.loc[t]
            out[t] = st.reindex(pd.DatetimeIndex(sd.dates)).to_numpy(float)
    return out


def portfolio(stocks, rule, window, sessions, p5=None, tau=1.0, costs=MAIN, **kw) -> dict:
    """Equal-weighted mean of slot returns over the stocks counted each day (D-021)."""
    frames, buys, assumed = [], 0, 0
    for t, sd in stocks.items():
        if not sd.eligible[(sd.dates >= np.datetime64(window[0]))
                           & (sd.dates <= np.datetime64(window[1]))].any():  # fmt: skip
            continue
        pp = None if p5 is None else p5.get(t)
        if rule == "model" and pp is None:
            pp = np.full(len(sd.dates), np.nan)
        df = simulate(sd, rule, p5=pp, tau=tau, costs=costs, window=window, **kw)
        buys += int(df.buy.sum())
        assumed += int(df.assumed_fill.sum())
        frames.append(df[df.counted][["date", "ret"]])
    allr = pd.concat(frames)
    daily = allr.groupby("date").ret.mean()
    days = sessions[(sessions >= np.datetime64(window[0])) & (sessions <= np.datetime64(window[1]))]
    daily = daily.reindex(pd.DatetimeIndex(days)[1:], fill_value=0.0)
    return {"daily": daily, "trades": buys, "assumed_fills": assumed}


def summary(p: dict) -> dict:
    r = p["daily"].to_numpy()
    return {"ann_return": ann_return(r), "sharpe": sharpe(r), "max_drawdown": max_drawdown(r),
            "trades": p["trades"], "assumed_fills": p["assumed_fills"], "days": len(r)}  # fmt: skip


def predict(features, params, train, rows) -> np.ndarray:
    m = make_model("logit", features, **params).fit(train)
    return 1 - m.survival(rows, np.array([H]))[:, 0]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--features-run", required=True)
    ap.add_argument("--d017-run", required=True, help="hyperparameters of ABCDx per fold")
    ap.add_argument("--d016-run", required=True, help="hyperparameters of M per fold")
    ap.add_argument("--bootstrap", type=int, default=CFG["evaluation"]["bootstrap"]["resamples"])
    args = ap.parse_args(argv)
    commit = code_version()
    fr = Path(args.features_run)
    fcfg = json.loads((fr / "config.json").read_text())
    snap = paths.SNAPSHOTS / fcfg["snapshot_id"]
    ds = add_direction_interactions(pd.read_parquet(fr / "dataset.parquet"))
    ds = ds[ds.trade_date <= DEV_END]
    sessions = np.sort(pd.to_datetime(
        pd.read_parquet(snap / "sessions_hose.parquet").trade_date).to_numpy())  # fmt: skip
    p_main = {y: json.loads((Path(args.d017_run) / "metrics.json").read_text())["results"][str(y)]
              ["chosen"]["ABCDx"] for y in DEV_FOLDS}  # fmt: skip
    p_mech = {y: json.loads((Path(args.d016_run) / "metrics.json").read_text())["results"][str(y)]
              ["chosen"]["M"] for y in DEV_FOLDS}  # fmt: skip
    feats = {"model": SPECS_D017["ABCDx"], "mech": list(FEATURES_MECH)}

    t0 = time.time()
    stocks = build_stocks(snap, CFG["labels"]["k_main"])
    # sanity: the backtest's swing state must equal the dataset's on every survival row
    chk = ds[["ticker", "trade_date", "swing_dir"]]
    sd_map = {(t, d): v for t, sd in stocks.items() for d, v in zip(sd.dates, sd.swing_dir,
                                                                     strict=True)}  # fmt: skip
    mism = sum(sd_map.get((t, d.to_datetime64())) != v for t, d, v in chk.itertuples(index=False))
    if mism:
        raise SystemExit(f"swing_dir mismatch between backtest and dataset on {mism} rows")
    run = RUNS / f"{datetime.now(UTC):%Y%m%dT%H%M%SZ}-devbacktest-D-021"
    run.mkdir(parents=True)
    logf = open(run / "log.txt", "w")

    def log(msg):
        print(msg, flush=True)
        logf.write(msg + "\n")
        logf.flush()

    log(f"{len(stocks)} stocks built, swing state checked on {len(chk):,} rows "
        f"({time.time() - t0:.0f}s)")  # fmt: skip

    folds, pooled = {}, {}
    for year in DEV_FOLDS:
        t0 = time.time()
        win = (pd.Timestamp(f"{year}-01-01"), pd.Timestamp(f"{year}-12-31"))
        iwin = (pd.Timestamp(f"{year - 1}-01-01"), pd.Timestamp(f"{year - 1}-12-31"))
        train, _ = split(ds, sessions, year, dev=True)
        inner_train, _ = split(train, sessions, year - 1, dev=False)
        rows_y = ds[ds.trade_date.dt.year == year]
        rows_iy = ds[ds.trade_date.dt.year == year - 1]
        fold = {"tau": {}, "inner_sharpe": {}, "strategies": {}, "sensitivity": {}, "trials": {}}
        preds = {}
        for name, params in (("model", p_main[year]), ("mech", p_mech[year])):
            ip = p5_by_stock(stocks, rows_iy, predict(feats[name], params, inner_train, rows_iy))
            sh = [sharpe(portfolio(stocks, "model", iwin, sessions, ip, tau)["daily"].to_numpy())
                  for tau in TAUS]  # fmt: skip
            best = max(range(len(TAUS)), key=lambda j: (np.nan_to_num(sh[j], nan=-9), TAUS[j]))
            fold["tau"][name], fold["inner_sharpe"][name] = TAUS[best], sh
            preds[name] = p5_by_stock(stocks, rows_y, predict(feats[name], params, train, rows_y))
        res = {
            "model": portfolio(
                stocks, "model", win, sessions, preds["model"], fold["tau"]["model"]
            ),
            "mech": portfolio(stocks, "model", win, sessions, preds["mech"], fold["tau"]["mech"]),
            "dc": portfolio(stocks, "dc", win, sessions),
            "bh": portfolio(stocks, "bh", win, sessions),
        }
        for k, v in res.items():
            fold["strategies"][k] = summary(v)
            pooled.setdefault(k, []).append(v["daily"])
        for name in ("model", "mech"):  # all 16 configurations on the fold year (DSR trials)
            for tau in TAUS:
                d = portfolio(stocks, "model", win, sessions, preds[name], tau)["daily"]
                pooled.setdefault(f"trial:{name}:{tau}", []).append(d)
        for label, c in COST_SENS.items():
            for k in ("model", "mech", "dc", "bh"):
                hazard = k in ("model", "mech")
                kw = dict(p5=preds[k], tau=fold["tau"][k]) if hazard else {}
                rule = "model" if hazard else k
                v = portfolio(stocks, rule, win, sessions, costs=c, **kw)
                fold["sensitivity"][f"{k}@{label}"] = summary(v)
                pooled.setdefault(f"{k}@{label}", []).append(v["daily"])
        for label, kw in (("skip_unknown_limits", {"unknown_limit": "skip"}),
                          ("fail_on_floor_close", {"fail_on_floor_close": True})):  # fmt: skip
            for k in ("model", "dc", "bh"):
                extra = dict(p5=preds["model"], tau=fold["tau"]["model"]) if k == "model" else {}
                rule = "model" if k == "model" else k
                v = portfolio(stocks, rule, win, sessions, **extra, **kw)
                fold["sensitivity"][f"{k}@{label}"] = summary(v)
                pooled.setdefault(f"{k}@{label}", []).append(v["daily"])
        folds[str(year)] = fold
        s = fold["strategies"]
        log(
            f"{year}: tau model {fold['tau']['model']} mech {fold['tau']['mech']} | Sharpe "
            + ", ".join(f"{k} {s[k]['sharpe']:.2f}" for k in s)
            + f" ({time.time() - t0:.0f}s)"
        )

    P = {k: pd.concat(v) for k, v in pooled.items()}
    pooled_out = {k: summary({"daily": P[k], "trades": None, "assumed_fills": None})
                  for k in P if not k.startswith("trial:")}  # fmt: skip
    for k in pooled_out:
        pooled_out[k].pop("trades"), pooled_out[k].pop("assumed_fills")
    trial_sr = [sharpe(P[k].to_numpy(), annualise=False) for k in P if k.startswith("trial:")]
    dsr = {k: deflated_sharpe(P[k].to_numpy(), trial_sr) for k in ("model", "mech")}
    diffs = {f"{a}-{b}": sharpe_diff_ci(P[a].to_numpy(), P[b].to_numpy(), n=args.bootstrap)
             for a, b in (("model", "dc"), ("model", "bh"), ("model", "mech"),
                          ("mech", "dc"), ("dc", "bh"))}  # fmt: skip
    h5 = bool(diffs["model-dc"]["lo"] > 0 and diffs["model-bh"]["lo"] > 0)
    log(json.dumps({"pooled_sharpe": {k: round(pooled_out[k]["sharpe"], 3)
                                      for k in ("model", "mech", "dc", "bh")},
                    "diffs": {k: [round(v["lo"], 3), round(v["hi"], 3)] for k, v in diffs.items()},
                    "dsr": {k: round(v["dsr"], 3) for k, v in dsr.items()},
                    "h5_supported_dev": h5}))  # fmt: skip
    cfg = {"protocol": "D-021", "features_run": fr.name, "d017_run": Path(args.d017_run).name,
           "d016_run": Path(args.d016_run).name, "snapshot_id": fcfg["snapshot_id"],
           "git_commit": commit, "taus": TAUS, "costs_main": MAIN.__dict__,
           "costs_sens": {k: v.__dict__ for k, v in COST_SENS.items()}, "folds": DEV_FOLDS,
           "bootstrap": args.bootstrap, "block": 20, "n_trials": len(trial_sr)}  # fmt: skip
    (run / "config.json").write_text(json.dumps(cfg, indent=2))
    (run / "metrics.json").write_text(json.dumps(
        {"folds": folds, "pooled": pooled_out, "sharpe_diffs": diffs, "dsr": dsr,
         "h5_supported_dev": h5}, indent=2, default=float))  # fmt: skip
    pd.DataFrame({k: v for k, v in P.items() if not k.startswith("trial:")}).to_parquet(
        run / "daily_returns.parquet")  # fmt: skip
    log(json.dumps({"run_dir": str(run)}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
