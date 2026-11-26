"""Stratified survival metrics (D-027 item 2).

Uno's C pooled over strata: the IPCW-weighted concordant and comparable pair sums of each
stratum (a test year, or a date) are added, and only within-stratum pairs count. Each stratum
has its own censoring distribution (its year's training outcomes). With one stratum this equals
``sksurv.metrics.concordance_index_ipcw`` exactly (tested). The stratified IBS is the
row-weighted mean of the per-stratum IBS.
"""

from __future__ import annotations

import numpy as np
from sksurv.metrics import _iter_comparable  # private; scikit-survival is pinned (0.28.0)
from sksurv.nonparametric import CensoringDistributionEstimator

from vnbank.research.survival.evaluation.metrics import clip_to_train, ibs


def c_parts(y_train, y_test, risk, tau: float, tied_tol: float = 1e-8) -> tuple[float, float]:
    """(numerator, denominator) of Uno's C, as in sksurv.concordance_index_ipcw."""
    y_test = clip_to_train(y_test, y_train)
    event, time = y_test["event"], y_test["time"]
    mask = time < tau
    cens = CensoringDistributionEstimator().fit(y_train)
    w = np.zeros(len(time))
    if mask.any():
        w[mask] = cens.predict_ipcw(y_test[mask])
    w = np.square(w)
    order = np.argsort(time)
    num = den = 0.0
    try:
        for ind, comp, _ in _iter_comparable(event, time, order):
            est_i, w_i = risk[order[ind]], w[order[ind]]
            est = risk[order[comp]]
            ties = np.absolute(est - est_i) <= tied_tol
            num += w_i * (est < est_i)[~ties].sum() + 0.5 * w_i * ties.sum()
            den += w_i * comp.sum()
    except Exception:  # no comparable pair in this stratum
        return 0.0, 0.0
    return float(num), float(den)


def strat_c(strata: np.ndarray, y_trains: dict, y_test, risk, tau: float,
            train_of=None) -> float:  # fmt: skip
    """Uno C over within-stratum pairs. y_trains: training outcomes per censoring group;
    train_of: censoring group of each stratum (defaults to the stratum itself)."""
    num = den = 0.0
    for s in np.unique(strata):
        m = strata == s
        g = s if train_of is None else train_of[s]
        a, b = c_parts(y_trains[g], y_test[m], risk[m], tau)
        num, den = num + a, den + b
    return num / den if den > 0 else float("nan")


def strat_ibs(strata: np.ndarray, y_trains: dict, y_test, surv_matrix, times) -> float:
    tot = n = 0.0
    for s in np.unique(strata):
        m = strata == s
        tot += m.sum() * ibs(y_trains[s], y_test[m], surv_matrix[m], times)
        n += m.sum()
    return tot / n
