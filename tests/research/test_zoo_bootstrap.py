import numpy as np
import pandas as pd
import pytest

from research.eval.bootstrap import block_resamples, paired_ci
from research.models.zoo import FIT_CAP, GRIDS, capped, make_model


def toy(n=1500, seed=0):
    rng = np.random.default_rng(seed)
    x = rng.normal(size=n)
    p = 1 / (1 + np.exp(-(-2.2 + 0.9 * x)))
    d = rng.geometric(p)
    c = rng.integers(3, 60, n)
    return pd.DataFrame({"x": x, "z": rng.normal(size=n), "duration": np.minimum(d, c),
                         "event": (d <= c).astype(int)})  # fmt: skip


@pytest.mark.parametrize("name", ["km", "logit", "gbm", "cox", "rsf"])
def test_every_model_gives_valid_survival_curves(name):
    df = toy()
    params = GRIDS[name][0]
    m = make_model(name, ["x", "z"], **params).fit(df)
    s = m.survival(df.head(50), np.arange(1, 21))
    assert s.shape == (50, 20)
    assert np.all((s >= 0) & (s <= 1))
    assert np.all(np.diff(s, axis=1) <= 1e-9)  # non-increasing in time
    if name != "km":  # higher x -> higher hazard -> lower 10-day survival
        lo, hi = df.x.nsmallest(50).index, df.x.nlargest(50).index
        s10 = lambda idx: m.survival(df.loc[idx], np.array([10]))[:, 0].mean()  # noqa: E731
        assert s10(hi) < s10(lo)


def test_fit_cap_censors_long_durations():
    d, e = capped(pd.DataFrame({"duration": [5, 30], "event": [1, 1]}))
    assert d.tolist() == [5, FIT_CAP] and e.tolist() == [1, 0]


def test_block_resamples_keep_size_and_whole_dates():
    dates = np.repeat(np.arange(100), 3)
    for idx in block_resamples(dates, block=10, n=5):
        assert len(np.unique(dates[idx])) <= 100
        # every drawn date comes with all its rows
        drawn, counts = np.unique(dates[idx], return_counts=True)
        assert np.all(counts % 3 == 0)
        assert len(idx) >= 300


def test_paired_ci_brackets_a_known_mean():
    rng = np.random.default_rng(1)
    dates = np.repeat(np.arange(200), 5)
    v = rng.normal(1.0, 1.0, len(dates))
    ci = paired_ci(dates, {"mean": lambda i: v[i].mean()}, block=10, n=300)["mean"]
    assert ci["lo"] < 1.0 < ci["hi"]
