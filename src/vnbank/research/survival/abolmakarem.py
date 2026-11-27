"""Random versus chronological splits, and target alignment, for the design of Abolmakarem et al.
(2024) (FINAL_RUN_PROTOCOL.md 5d). Development years only (2012-2016): no test year is used.

    uv run python -m vnbank.research.survival.abolmakarem

Abolmakarem et al. predict next-day targets from 28 inputs with a one-hidden-layer perceptron
(40 nodes) and report test accuracy of 95.8-97.0% for the next day's direction and R^2 of about
0.9999 for the next day's return. We rebuild their inputs (their Table 2: 15 log-price ratios
over the last four days and 13 technical indicators) and three of their targets (Trend, peak
detection PK, daily return Ret, their Eqs. 1, 2 and 10) on our VN30 and bank stock-days, and
fit the same kind of network under:

* split: random 70/15/15 over rows (MATLAB's default `dividerand`, which their training setup
  suggests) versus chronological (first 70% of dates train, next 15% validation, last 15% test);
* alignment: the target of day t+1 on the inputs of day t (Eq. 11, correct), versus the target
  of day t on the inputs of day t, where r1 = ln(C_t / C_{t-1}) already contains the answer.
  The second factor is a diagnostic added to the pre-registered comparison.

Indicators that are price levels in the original (moving averages, SAR, TR, ATR, momentum) are
divided by the close so that stocks can be pooled (CLAUDE.md rule 9: adjusted prices only in
ratios). Writes research/paper1/runs/<UTC timestamp>-abolmakarem-dev/{config.json, metrics.json}.
"""

from __future__ import annotations

import json
import sys
from datetime import UTC, datetime

import numpy as np
import pandas as pd

from vnbank.common import paths
from vnbank.research.shared.run_meta import code_version

SNAPSHOT = "1f0c80b50427479e"
DEV_START, DEV_END = "2012-01-03", "2016-12-31"
SEED = 0
HIDDEN = 40


def _wilder(x: pd.Series, n: int) -> pd.Series:
    return x.ewm(alpha=1 / n, adjust=False).mean()


def _wma(x: pd.Series, n: int) -> pd.Series:
    w = np.arange(1, n + 1, dtype=float)
    return x.rolling(n).apply(lambda v: np.dot(v, w) / w.sum(), raw=True)


def _psar(h: np.ndarray, lo: np.ndarray, step: float = 0.02, cap: float = 0.2) -> np.ndarray:
    """Wilder's parabolic SAR."""
    n = len(h)
    sar = np.full(n, np.nan)
    if n < 2:
        return sar
    up, af, ep, s = True, step, h[0], lo[0]
    for i in range(1, n):
        s = s + af * (ep - s)
        if up:
            s = min(s, lo[i - 1], lo[i - 2] if i > 1 else lo[i - 1])
            if lo[i] < s:
                up, s, ep, af = False, ep, lo[i], step
            elif h[i] > ep:
                ep, af = h[i], min(af + step, cap)
        else:
            s = max(s, h[i - 1], h[i - 2] if i > 1 else h[i - 1])
            if h[i] > s:
                up, s, ep, af = True, ep, h[i], step
            elif lo[i] < ep:
                ep, af = lo[i], min(af + step, cap)
        sar[i] = s
    return sar


def features(px: pd.DataFrame) -> pd.DataFrame:
    """Their 28 inputs for one stock (rows ordered by date)."""
    o, h, lo, c = (px[k].astype(float) for k in ("open_adj", "high_adj", "low_adj", "close_adj"))
    f = pd.DataFrame(index=px.index)
    for k in range(1, 5):  # r1-r4: close-to-close log returns, lags 0-3
        f[f"r{k}"] = np.log(c.shift(k - 1) / c.shift(k))
    for k, lag in zip(range(5, 9), range(4), strict=True):  # r5-r8: ln(H_t / O_{t-lag})
        f[f"r{k}"] = np.log(h / o.shift(lag))
    for k, lag in zip(range(9, 12), range(1, 4), strict=True):  # r9-r11: ln(H_{t-lag}/O_{t-lag})
        f[f"r{k}"] = np.log(h.shift(lag) / o.shift(lag))
    for k, lag in zip(range(12, 16), range(4), strict=True):  # r12-r15: ln(L_{t-lag}/O_{t-lag})
        f[f"r{k}"] = np.log(lo.shift(lag) / o.shift(lag))
    d = c.diff()
    rs = _wilder(d.clip(lower=0), 14) / _wilder((-d).clip(lower=0), 14)
    f["rsi"] = 100 - 100 / (1 + rs)
    f["momentum"] = c / c.shift(10) - 1
    tr = pd.concat([h, c.shift()], axis=1).max(axis=1) - pd.concat([lo, c.shift()], axis=1).min(
        axis=1)  # fmt: skip
    f["tr"] = tr / c
    f["atr"] = tr.rolling(14).mean() / c
    f["psar"] = _psar(h.to_numpy(), lo.to_numpy()) / c
    m = (h + lo + c) / 3
    sm = m.rolling(20).mean()
    md = m.rolling(20).apply(lambda v: np.abs(v - v.mean()).mean(), raw=True)
    f["cci"] = (m - sm) / (0.015 * md)
    f["sma"] = c.rolling(20).mean() / c
    f["wma"] = _wma(c, 20) / c
    f["hma"] = _wma(2 * _wma(c, 10) - _wma(c, 20), 4) / c
    upm, dnm = h.diff(), -lo.diff()
    pdm = upm.where((upm > dnm) & (upm > 0), 0.0)
    ndm = dnm.where((dnm > upm) & (dnm > 0), 0.0)
    atr_w = _wilder(tr, 14)
    pdi, ndi = 100 * _wilder(pdm, 14) / atr_w, 100 * _wilder(ndm, 14) / atr_w
    f["adx"] = _wilder(100 * (pdi - ndi).abs() / (pdi + ndi), 14)
    hh, ll = h.rolling(14).max(), lo.rolling(14).min()
    f["williams_r"] = 100 * (hh - c) / (hh - ll)
    f["stoch_k"] = 100 * (c - ll) / (hh - ll)
    f["stoch_d_slow"] = f.stoch_k.rolling(3).mean().rolling(3).mean()
    return f


def targets(px: pd.DataFrame) -> pd.DataFrame:
    """Their Eqs. 1, 2 and 10, indexed by the day whose close completes them."""
    c = px.close_adj.astype(float)
    trend = (c > c.shift()).astype(float).where(c.shift().notna())
    pk = ((trend.shift() == 1) & (trend == 0)).astype(float).where(trend.shift().notna())
    ret = 100 * (c / c.shift() - 1)
    return pd.DataFrame({"trend": trend, "pk": pk, "ret": ret}, index=px.index)


def build() -> pd.DataFrame:
    snap = paths.SNAPSHOTS / SNAPSHOT
    cols = ["ticker", "trade_date", "open_adj", "high_adj", "low_adj", "close_adj"]
    px = pd.read_parquet(snap / "prices_adjusted.parquet", columns=cols)
    px["trade_date"] = pd.to_datetime(px.trade_date)
    px = px[px.trade_date <= DEV_END].sort_values(["ticker", "trade_date"])
    u = pd.read_parquet(snap / "universe_daily.parquet", columns=["ticker", "trade_date"])
    u["trade_date"] = pd.to_datetime(u.trade_date)
    frames = []
    for _, g in px.groupby("ticker", sort=False):
        g = g.reset_index(drop=True)
        f, t = features(g), targets(g)
        out = pd.concat([g[["ticker", "trade_date"]], f], axis=1)
        for k in t.columns:
            out[f"{k}_same"] = t[k]  # target of day t: as if aligned on the same row
            out[f"{k}_next"] = t[k].shift(-1)  # target of day t+1 (Eq. 11)
        frames.append(out)
    ds = pd.concat(frames, ignore_index=True)
    ds = ds.merge(u, on=["ticker", "trade_date"])  # universe stock-days only
    ds = ds[(ds.trade_date >= DEV_START) & (ds.trade_date <= DEV_END)]
    feats = [c for c in ds.columns if c not in ("ticker", "trade_date")
             and not c.endswith(("_same", "_next"))]  # fmt: skip
    return ds.replace([np.inf, -np.inf], np.nan).dropna(subset=feats).reset_index(drop=True)


def splits(ds: pd.DataFrame, how: str, rng) -> tuple[np.ndarray, np.ndarray]:
    """Train and test row indices (the middle 15% is the validation share, used for early
    stopping inside the training fit, as in their setup)."""
    n = len(ds)
    if how == "random":
        p = rng.permutation(n)
        return p[: int(0.85 * n)], p[int(0.85 * n) :]
    dates = np.sort(ds.trade_date.unique())
    cut = dates[int(0.85 * len(dates))]
    return np.flatnonzero(ds.trade_date < cut), np.flatnonzero(ds.trade_date >= cut)


def fit_score(ds, feats, target, kind, tr, te) -> dict:
    from sklearn.metrics import accuracy_score, r2_score
    from sklearn.neural_network import MLPClassifier, MLPRegressor
    from sklearn.preprocessing import StandardScaler

    y = ds[target].to_numpy()
    ok_tr, ok_te = tr[~np.isnan(y[tr])], te[~np.isnan(y[te])]
    sc = StandardScaler().fit(ds.loc[ok_tr, feats])
    Xtr, Xte = sc.transform(ds.loc[ok_tr, feats]), sc.transform(ds.loc[ok_te, feats])
    kw = {"hidden_layer_sizes": (HIDDEN,), "activation": "tanh", "early_stopping": True,
          "validation_fraction": 0.15 / 0.85, "max_iter": 500, "random_state": SEED}  # fmt: skip
    if kind == "class":
        m = MLPClassifier(**kw).fit(Xtr, y[ok_tr].astype(int))
        pred = m.predict(Xte)
        base = max(np.mean(y[ok_te]), 1 - np.mean(y[ok_te]))
        return {
            "accuracy": float(accuracy_score(y[ok_te].astype(int), pred)),
            "majority_class": float(base),
            "n_train": len(ok_tr),
            "n_test": len(ok_te),
        }
    m = MLPRegressor(**kw).fit(Xtr, y[ok_tr])
    return {"r2": float(r2_score(y[ok_te], m.predict(Xte))), "n_train": len(ok_tr),
            "n_test": len(ok_te)}  # fmt: skip


def main(argv: list[str] | None = None) -> int:
    commit = code_version()
    if commit.endswith("+dirty"):
        raise SystemExit("working tree is dirty: reported results come from committed code")
    ds = build()
    feats = [c for c in ds.columns if c not in ("ticker", "trade_date")
             and not c.endswith(("_same", "_next"))]  # fmt: skip
    if len(feats) != 28:
        raise SystemExit(f"expected their 28 inputs, built {len(feats)}")
    rng = np.random.default_rng(SEED)
    metrics: dict = {"rows": len(ds), "stocks": int(ds.ticker.nunique()),
                     "first": str(ds.trade_date.min().date()),
                     "last": str(ds.trade_date.max().date()), "results": {}}  # fmt: skip
    for how in ("random", "chronological"):
        tr, te = splits(ds, how, rng)
        for align in ("next", "same"):
            for tgt, kind in (("trend", "class"), ("pk", "class"), ("ret", "reg")):
                r = fit_score(ds, feats, f"{tgt}_{align}", kind, tr, te)
                metrics["results"][f"{how}:{align}:{tgt}"] = r
                print(how, align, tgt, {k: round(v, 4) for k, v in r.items()}, flush=True)
    out = paths.runs_dir(1) / f"{datetime.now(UTC):%Y%m%dT%H%M%SZ}-abolmakarem-dev"
    out.mkdir(parents=True)
    (out / "config.json").write_text(json.dumps(
        {"git_commit": commit, "created_at_utc": datetime.now(UTC).isoformat(),
         "protocol": "FINAL_RUN_PROTOCOL.md 5d", "snapshot_id": SNAPSHOT,
         "years": [DEV_START, DEV_END], "hidden": HIDDEN, "seed": SEED,
         "features": feats}, indent=1))  # fmt: skip
    (out / "metrics.json").write_text(json.dumps(metrics, indent=1))
    print(out.name)
    return 0


if __name__ == "__main__":
    sys.exit(main())
