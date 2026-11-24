import numpy as np
import pandas as pd
import pytest

from research.eval.metrics import calibration, surv, uno_c
from research.models.hazard import LogisticHazard, one_day_target
from research.models.km import KaplanMeier


def test_km_matches_hand_calculation():
    # times 1,2,2,3 (events at 1,2,3; one censored at 2)
    km = KaplanMeier().fit([1, 2, 2, 3], [1, 1, 0, 1])
    # S(1) = 3/4; S(2) = 3/4 * (1 - 1/3) = 1/2; S(3) = 1/2 * (1 - 1/1) = 0
    assert km.survival([0, 1, 2, 3, 9]).tolist() == pytest.approx([1, 0.75, 0.5, 0, 0])


def test_km_delayed_entry_excludes_not_yet_entered():
    # subject B enters at 2: not at risk at time 1 or 2
    km = KaplanMeier().fit(exit_time=[1, 4], event=[1, 1], entry=[0, 2])
    assert km.at_risk_.tolist() == [1, 0, 1, 1]
    assert km.survival(1) == 0.0  # the only subject at risk at 1 had the event


def test_km_rejects_exit_not_after_entry():
    with pytest.raises(ValueError):
        KaplanMeier().fit([2], [1], entry=[2])


def test_uno_c_perfect_reverse_and_tied():
    rng = np.random.default_rng(0)
    t = rng.integers(1, 30, 400)
    e = rng.random(400) < 0.8
    ytr, yte = surv(e, t), surv(e, t)
    assert uno_c(ytr, yte, -t.astype(float), tau=25) > 0.99  # shorter time = higher risk
    assert uno_c(ytr, yte, t.astype(float), tau=25) < 0.01
    assert uno_c(ytr, yte, np.zeros(400), tau=25) == pytest.approx(0.5)  # KM-like: all ties


def test_calibration_of_a_perfect_constant():
    rng = np.random.default_rng(1)
    d = rng.geometric(0.2, 5000)  # P(event within 5) = 1 - 0.8**5
    cal = calibration(np.full(5000, 1 - 0.8**5), np.ones(5000), d, horizon=5, bins=5)
    assert np.allclose(cal.observed, 1 - 0.8**5, atol=0.03)


def test_landmark_expansion():
    from research.models.hazard import expand

    rows, steps, target = expand([3, 2, 25], [1, 0, 1], max_step=20)
    assert rows.tolist() == [0, 0, 0, 1, 1] + [2] * 20
    assert steps[:5].tolist() == [1, 2, 3, 1, 2]
    assert target[:5].tolist() == [0, 0, 1, 0, 0]  # event at step 3; row 1 censored at 2
    assert target[5:].sum() == 0  # event at 25 lies beyond the 20 expanded steps


def test_landmark_hazard_is_calibrated_on_a_known_process():
    # geometric durations with a covariate-dependent constant hazard p(x)
    rng = np.random.default_rng(3)
    n = 4000
    x = rng.normal(size=n)
    p = 1 / (1 + np.exp(-(-2.0 + 1.0 * x)))
    d = rng.geometric(p)
    cens = rng.integers(5, 40, n)
    e = (d <= cens).astype(int)
    dur = np.minimum(d, cens)
    X = pd.DataFrame({"x": x})
    m = LogisticHazard(["x"]).fit(X, dur, e)
    s5 = m.survival(X, np.array([1, 5]))[:, 1]
    truth = (1 - p) ** 5
    assert np.corrcoef(s5, truth)[0, 1] > 0.98
    assert abs(s5.mean() - truth.mean()) < 0.03  # calibrated on average
    assert one_day_target([1, 1, 0], [1, 2, 1]).tolist() == [1, 0, 0]
