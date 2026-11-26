"""Stratified Uno C (D-027): one stratum equals sksurv exactly; strata only count within."""

import numpy as np

from vnbank.research.survival.evaluation.metrics import surv, uno_c
from vnbank.research.survival.evaluation.strat import c_parts, strat_c


def _data(n, seed):
    rng = np.random.default_rng(seed)
    risk = rng.normal(size=n)
    t = np.ceil(rng.exponential(8 / np.exp(0.5 * risk))).clip(1, 40)
    e = rng.random(n) < 0.8
    return surv(e, t), risk


def test_single_stratum_equals_sksurv():
    ytr, _ = _data(500, 0)
    yte, r = _data(300, 1)
    a, b = c_parts(ytr, yte, r, 20)
    assert abs(a / b - uno_c(ytr, yte, r, 20)) < 1e-12


def test_strata_ignore_cross_stratum_pairs():
    ytr, _ = _data(800, 2)
    y1, r1 = _data(200, 3)
    y2, r2 = _data(200, 4)
    y = np.concatenate([y1, y2])
    r = np.concatenate([r1, r2 + 100])  # a level shift in stratum 2 only
    s = np.repeat([1, 2], 200)
    c = strat_c(s, {1: ytr, 2: ytr}, y, r, 20)
    a1, b1 = c_parts(ytr, y1, r1, 20)
    a2, b2 = c_parts(ytr, y2, r2, 20)
    assert abs(c - (a1 + a2) / (b1 + b2)) < 1e-12
    assert abs(c - uno_c(ytr, y, r, 20)) > 0.01  # pooled C is moved by the level shift
