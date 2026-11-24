import numpy as np
import pytest

from vnbank.research.survival.backtest.metrics import (
    ann_return,
    deflated_sharpe,
    max_drawdown,
    sharpe,
    sharpe_diff_ci,
)


def test_basic_metrics_by_hand():
    r = np.array([0.1, -0.5, 0.2])
    assert max_drawdown(r) == pytest.approx(-0.5)
    assert ann_return(np.full(252, 0.001)) == pytest.approx(1.001**252 - 1)
    x = np.array([0.01, 0.03])
    assert sharpe(x, annualise=False) == pytest.approx(0.02 / np.std(x, ddof=1))


def test_deflated_sharpe_falls_with_more_trials_and_is_a_probability():
    rng = np.random.default_rng(0)
    r = rng.normal(0.001, 0.01, 750)
    few = deflated_sharpe(r, rng.normal(0, 0.02, 2))
    many = deflated_sharpe(r, rng.normal(0, 0.02, 100))
    assert 0 <= many["dsr"] <= few["dsr"] <= 1


def test_sharpe_diff_ci_contains_zero_for_identical_series():
    r = np.random.default_rng(1).normal(0, 0.01, 300)
    ci = sharpe_diff_ci(r, r, n=20)
    assert ci["lo"] == ci["hi"] == ci["point"] == 0.0
