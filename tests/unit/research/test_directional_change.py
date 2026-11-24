import numpy as np
import pytest

from vnbank.research.swings.directional_change import DOWN, UP, atr20, label_series, thresholds


def unit_steps(path):
    """Close path with high/low = close +/- 1. With moves of at most 1, every true range is 2,
    so ATR20 = 2 and theta_t = k * 2 / close_{t-1} once 21 closes exist."""
    c = np.asarray(path, dtype="float64")
    return c + 1, c - 1, c


def test_atr_and_threshold_use_only_the_past():
    h, low, c = unit_steps([100.0] * 25)
    a = atr20(h, low, c)
    assert np.isnan(a[:20]).all() and np.allclose(a[20:], 2.0)
    th = thresholds(h, low, c, k=2.0)
    assert np.isnan(th[:21]).all()  # needs ATR20 of the previous day
    assert np.allclose(th[21:], 2.0 * 2.0 / 100.0)


def test_known_up_then_reversal():
    # 25 flat days at 100, a +1/day rise to 120, then a one-day drop to 100.
    path = [100.0] * 25 + [100.0 + i for i in range(1, 21)] + [100.0]
    h, low, c = unit_steps(path)
    lab = label_series(h, low, c, k=2.0)
    peak = path.index(120.0)
    drop = len(path) - 1

    # first swing: up, confirmed at the first close >= 100 * (1 + 0.04) = 104
    first = lab.reversals[0]
    assert first.ended_direction == DOWN and first.extreme_price == 100.0
    assert first.extreme_index == 21  # tracking starts when theta first exists
    assert first.confirm_index == path.index(104.0)
    # the up-swing ends at the drop: 100 <= 120 * (1 - 4/119) holds on that very day
    second = lab.reversals[1]
    assert (second.confirm_index, second.extreme_index, second.extreme_price) == (drop, peak, 120.0)
    assert second.ended_direction == UP
    # state during the up-swing
    t = peak
    assert lab.direction[t] == UP and lab.swing_start_index[t] == 21
    assert lab.swing_confirm_index[t] == first.confirm_index and lab.running_extreme[t] == 120.0
    assert lab.next_confirm_index[t] == drop  # future, for targets only
    # after the drop: a down-swing that started at the peak
    assert lab.direction[drop] == DOWN and lab.swing_start_index[drop] == peak


def test_small_pullbacks_do_not_reverse():
    # rise, a 2-point dip (below the ~4% threshold), rise again: one up-swing throughout
    path = (
        [100.0] * 25 + [100 + i for i in range(1, 11)] + [109, 108] + [109 + i for i in range(10)]
    )
    lab = label_series(*unit_steps(path), k=2.0)
    assert [r.ended_direction for r in lab.reversals] == [DOWN]  # only the initial confirmation
    assert lab.direction[-1] == UP and lab.next_confirm_index[-1] == -1  # still open


def test_down_swing_mirrors():
    path = [100.0] * 25 + [100.0 - i for i in range(1, 16)] + [100.0]
    lab = label_series(*unit_steps(path), k=2.0)
    assert lab.reversals[0].ended_direction == UP  # a down-swing is confirmed first
    trough = path.index(85.0)
    last = lab.reversals[-1]
    assert (last.extreme_index, last.extreme_price, last.ended_direction) == (trough, 85.0, DOWN)
    assert lab.direction[-1] == UP


def test_larger_k_gives_fewer_reversals():
    rng = np.random.default_rng(7)
    c = 100 * np.exp(np.cumsum(rng.normal(0, 0.02, 1500)))
    h, low = c * 1.01, c * 0.99
    n = [len(label_series(h, low, c, k=k).reversals) for k in (1.5, 2.0, 3.0)]
    assert n[0] > n[1] > n[2] > 0


@pytest.mark.parametrize("seed", [1, 2, 3])
def test_truncation_invariance_no_look_ahead(seed):
    """Labelling the first n days must reproduce the full run on those days exactly."""
    rng = np.random.default_rng(seed)
    c = 50 * np.exp(np.cumsum(rng.normal(0, 0.025, 800)))
    h = c * (1 + rng.uniform(0, 0.02, 800))
    low = c * (1 - rng.uniform(0, 0.02, 800))
    full = label_series(h, low, c, k=2.0)
    for n in (60, 150, 333, 501, 799):
        part = label_series(h[:n], low[:n], c[:n], k=2.0)
        for name in ("theta", "running_extreme"):
            np.testing.assert_array_equal(getattr(part, name), getattr(full, name)[:n])
        for name in ("direction", "swing_start_index", "swing_confirm_index"):
            np.testing.assert_array_equal(getattr(part, name), getattr(full, name)[:n])
        assert part.reversals == [r for r in full.reversals if r.confirm_index < n]


def test_rejects_bad_input():
    with pytest.raises(ValueError):
        label_series([1, 2], [1, 2], [1, 2, 3])
    with pytest.raises(ValueError):
        label_series([1, 1], [1, 1], [1, 0])
