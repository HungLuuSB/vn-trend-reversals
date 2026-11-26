"""Final trading test (D-021 / D-026) on synthetic stocks and caches."""

import numpy as np
import pandas as pd

from vnbank.research.survival.backtest.engine import StockDays
from vnbank.research.survival.final import backtest as B


def _stocks(sessions, n=4, seed=0):
    rng = np.random.default_rng(seed)
    out = {}
    for i in range(n):
        m = len(sessions)
        px = 10 * np.exp(np.cumsum(rng.normal(0, 0.02, m)))
        sd = np.where(np.sin(np.arange(m) / 15 + i) > 0, 1, -1)
        out[f"T{i}"] = StockDays(dates=sessions, session=np.arange(m), open_adj=px,
                                 open_raw=px * 1000, ceiling=px * 1070, floor=px * 930,
                                 limit_known=np.ones(m, bool), close_at_floor=np.zeros(m, bool),
                                 eligible=np.ones(m, bool), swing_dir=sd)  # fmt: skip
    return out


def test_run_years_from_caches(tmp_path):
    sessions = pd.bdate_range("2016-01-01", "2018-12-31").to_numpy()
    stocks = _stocks(sessions)
    rng = np.random.default_rng(1)
    for y in (2017, 2018):
        d = tmp_path / str(y)
        d.mkdir()
        rows = [(t, s, stocks[t].swing_dir[i]) for t in stocks
                for i, s in enumerate(sessions) if pd.Timestamp(s).year == y]  # fmt: skip
        keys = pd.DataFrame(rows, columns=["ticker", "trade_date", "swing_dir"])
        keys.to_parquet(d / "keys.parquet")
        n = len(keys)
        s = np.sort(rng.uniform(0.3, 1, (n, 20)), axis=1)[:, ::-1]
        (d / "preds").mkdir()
        np.save(d / "preds" / "ABCDx.npy", s)
        np.save(d / "preds" / "M.npy", s**0.9)
        irows = [(t, s) for t in stocks for s in sessions if pd.Timestamp(s).year == y - 1]
        inner = pd.DataFrame(irows, columns=["ticker", "trade_date"])
        inner["p5:ABCDx"] = rng.uniform(0, 1, len(inner))
        inner["p5:M"] = rng.uniform(0, 1, len(inner))
        inner.to_parquet(d / "inner_p5.parquet")
    folds, P = B.run_years(stocks, sessions, tmp_path, [2017, 2018], log=lambda m: None)
    assert set(folds) == {"2017", "2018"}
    assert all(f["tau"]["model"] in B.TAUS for f in folds.values())
    assert sum(k.startswith("trial:") for k in P) == 16
    res = B.pooled_results(P, n_boot=20)
    assert res["n_trials"] == 16 and set(res["sharpe_diffs"]) == {f"{a}-{b}" for a, b in B.PAIRS}
    assert 0 <= res["dsr"]["model"]["dsr"] <= 1
