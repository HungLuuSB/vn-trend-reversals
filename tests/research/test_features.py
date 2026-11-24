import numpy as np
import pandas as pd
import pytest

from research.features.stock import block_a, block_b, rsi
from research.labels.directional_change import label_series


def frame(n=400, seed=0):
    rng = np.random.default_rng(seed)
    c = 30 * np.exp(np.cumsum(rng.normal(0, 0.02, n)))
    return pd.DataFrame(
        {
            "close_adj": c,
            "high_adj": c * (1 + rng.uniform(0, 0.02, n)),
            "low_adj": c * (1 - rng.uniform(0, 0.02, n)),
            "volume": rng.integers(1_000, 100_000, n),
            "close_at_ceiling": rng.random(n) < 0.03,
            "close_at_floor": rng.random(n) < 0.03,
            "limit_status": np.where(rng.random(n) < 0.9, "computed", "ref_not_reconstructable"),
        }
    )


def features(px):
    lab = label_series(px.high_adj, px.low_adj, px.close_adj, k=2.0)
    return pd.concat([block_a(px.close_adj.to_numpy(), lab), block_b(px)], axis=1)


@pytest.mark.parametrize("seed", [0, 1])
def test_features_on_day_t_use_only_data_up_to_t(seed):
    px = frame(seed=seed)
    full = features(px)
    for t in (60, 199, 333, 399):
        cut = features(px.iloc[: t + 1].reset_index(drop=True))
        pd.testing.assert_series_equal(cut.iloc[t], full.iloc[t], check_names=False)


def test_swing_state_units():
    # flat 100 then +1/day: after the first confirmation the move is positive and the distance
    # from the running maximum is 0 on new highs
    c = np.array([100.0] * 25 + [100.0 + i for i in range(1, 21)])
    lab = label_series(c + 1, c - 1, c, k=2.0)
    a = block_a(c, lab)
    t = len(c) - 1
    assert a.swing_dir.iat[t] == 1 and a.swing_dist.iat[t] == 0
    assert a.swing_move.iat[t] == pytest.approx((120 / 100 - 1) / lab.theta[t])
    assert a.swing_age.iat[t] == t - 21
    assert np.isnan(a.swing_age.iat[10])  # no swing yet


def test_rsi_extremes():
    up = np.arange(1, 40, dtype="float64")
    assert rsi(up)[-1] == 100.0
    assert rsi(up[::-1].copy())[-1] == 0.0
    assert np.isnan(rsi(up)[5])


def test_block_b_values():
    px = frame(n=60)
    b = block_b(px)
    c = px.close_adj.to_numpy()
    assert b.ret_5.iat[30] == pytest.approx(np.log(c[30] / c[25]))
    assert b.vol_rel_20.iat[30] == pytest.approx(px.volume.iat[30] / px.volume.iloc[11:31].mean())
    assert b.limit_up_hits_5.iat[30] == px.close_at_ceiling.iloc[26:31].sum()
