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


def test_logistic_hazard_learns_signal_and_chains_survival():
    rng = np.random.default_rng(2)
    n = 6000
    x = rng.normal(size=n)
    h = 1 / (1 + np.exp(-(-2.0 + 1.5 * x)))
    y = (rng.random(n) < h).astype(int)
    X = pd.DataFrame({"x": x, "swing_age": rng.integers(1, 50, n).astype(float)})
    X["log_age"] = np.log1p(X.swing_age)
    m = LogisticHazard(["x", "log_age"]).fit(X, y)
    coef = m.model[-1].coef_[0]
    assert coef[0] > 0.5  # recovers the positive effect of x (scaled)
    s = m.survival(X.head(3), np.array([1, 5]))
    assert np.all(s[:, 1] <= s[:, 0]) and np.all((s > 0) & (s < 1))
    assert one_day_target([1, 1, 0], [1, 2, 1]).tolist() == [1, 0, 0]
