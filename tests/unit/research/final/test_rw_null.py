"""Random-walk null (D-027 item 1): exact labeller replay, determinism, calibration."""

import numpy as np
import pandas as pd

from vnbank.research.survival.final import rw_null as R
from vnbank.research.swings.directional_change import ATR_WINDOW, label_series, true_range


def _prices(n=1500, seed=0, ticker="AAA"):
    rng = np.random.default_rng(seed)
    r = rng.normal(0, 0.02, n)
    c = 20 * np.exp(np.cumsum(r))
    h = c * np.exp(np.abs(rng.normal(0, 0.01, n)))
    lo = c * np.exp(-np.abs(rng.normal(0, 0.01, n)))
    return pd.DataFrame(
        {
            "ticker": ticker,
            "trade_date": pd.bdate_range("2010-01-01", periods=n),
            "high_adj": h,
            "low_adj": lo,
            "close_adj": c,
        }
    )


def test_replaying_the_real_path_reproduces_the_labeller():
    px = _prices()
    h, lo, c = px.high_adj.to_numpy(), px.low_adj.to_numpy(), px.close_adj.to_numpy()
    lab = label_series(h, lo, c, k=2.0)
    tr = true_range(h, lo, c)
    _, _, _, tuples = R.stock_state(px, 2.0)
    ts = [t for t in range(ATR_WINDOW, len(c) - R.STEPS) if lab.direction[t] != 0]
    paths = np.stack([tuples[t + 1 : t + 1 + R.STEPS] for t in ts])[:, None]  # one path each
    hist = np.stack([tr[t - ATR_WINDOW + 1 : t + 1] for t in ts])
    done = R.roll(lab.direction[ts], lab.running_extreme[ts], c[ts], hist, 2.0, paths)[:, 0]
    nxt = lab.next_confirm_index[ts]
    want = np.where((nxt > 0) & (nxt - np.array(ts) <= R.STEPS), nxt - np.array(ts), R.STEPS + 1)
    assert len(ts) > 1000 and np.array_equal(done, want)


def test_rw_survival_is_deterministic_monotone_and_causal():
    px = pd.concat([_prices(seed=1), _prices(seed=2, ticker="BBB")])
    rows = px[px.trade_date.dt.year == 2014][["ticker", "trade_date"]].reset_index(drop=True)
    a = R.rw_survival(px, rows, 2.0, n_paths=50)
    b = R.rw_survival(px, rows.iloc[::-1].reset_index(drop=True), 2.0, n_paths=50)[::-1]
    ok = ~np.isnan(a[:, 0])
    assert ok.mean() > 0.9 and np.allclose(a[ok], b[ok])
    assert np.all(np.diff(a[ok], axis=1) <= 0)
    later = px.copy()  # prices after every row are scrambled: predictions must not move
    m = later.trade_date > rows.trade_date.max()
    later.loc[m, ["high_adj", "low_adj", "close_adj"]] *= 3.0
    c = R.rw_survival(later, rows, 2.0, n_paths=50)
    assert np.allclose(a[ok], c[ok])


def test_rw_is_calibrated_when_prices_really_are_a_random_walk():
    px = _prices(n=3000, seed=3)
    lab = label_series(px.high_adj, px.low_adj, px.close_adj, k=2.0)
    t = np.arange(400, 2900, 3)
    t = t[lab.direction[t] != 0]
    rows = px.iloc[t][["ticker", "trade_date"]].reset_index(drop=True)
    s = R.rw_survival(px, rows, 2.0, n_paths=200)
    p5 = 1 - s[:, 4]
    nxt = lab.next_confirm_index[t]
    hit = ((nxt > 0) & (nxt - t <= 5)).astype(float)
    assert abs(p5.mean() - hit.mean()) < 0.03  # calibrated on average
    assert np.corrcoef(p5, hit)[0, 1] > 0.2  # and it ranks
