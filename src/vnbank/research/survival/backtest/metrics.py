"""Performance metrics for the trading test (DECISIONS.md D-021)."""

from __future__ import annotations

import numpy as np
from scipy import stats

from vnbank.research.survival.evaluation.bootstrap import block_resamples

DAYS = 252
EULER_GAMMA = 0.5772156649015329


def ann_return(r: np.ndarray) -> float:
    r = np.asarray(r, float)
    return float(np.prod(1 + r) ** (DAYS / len(r)) - 1) if len(r) else float("nan")


def sharpe(r: np.ndarray, annualise: bool = True) -> float:
    r = np.asarray(r, float)
    sd = r.std(ddof=1)
    if len(r) < 2 or sd == 0:
        return float("nan")
    s = r.mean() / sd
    return float(s * np.sqrt(DAYS)) if annualise else float(s)


def max_drawdown(r: np.ndarray) -> float:
    cum = np.cumprod(1 + np.asarray(r, float))
    return float((cum / np.maximum.accumulate(cum) - 1).min())


def deflated_sharpe(r: np.ndarray, trial_sharpes: np.ndarray) -> dict:
    """Bailey and Lopez de Prado (2014), with per-period (not annualised) Sharpe ratios.
    trial_sharpes: per-period Sharpe ratios of all N configurations tried."""
    r = np.asarray(r, float)
    t = len(r)
    sr = sharpe(r, annualise=False)
    trials = np.asarray(trial_sharpes, float)
    n = len(trials)
    v = trials.var(ddof=1) if n > 1 else 0.0
    sr0 = np.sqrt(v) * ((1 - EULER_GAMMA) * stats.norm.ppf(1 - 1 / n)
                        + EULER_GAMMA * stats.norm.ppf(1 - 1 / (n * np.e)))  # fmt: skip
    g3 = stats.skew(r)
    g4 = stats.kurtosis(r, fisher=False)
    denom = np.sqrt(max(1e-12, 1 - g3 * sr + (g4 - 1) / 4 * sr**2))
    dsr = stats.norm.cdf((sr - sr0) * np.sqrt(t - 1) / denom)
    return {"dsr": float(dsr), "sr_period": sr, "sr0_period": float(sr0), "n_trials": n,
            "skew": float(g3), "kurtosis": float(g4), "t": t}  # fmt: skip


def sharpe_diff_ci(a: np.ndarray, b: np.ndarray, block: int = 20, n: int = 200,
                   seed: int = 0) -> dict:  # fmt: skip
    """Paired moving-block bootstrap over days of Sharpe(a) - Sharpe(b) (annualised)."""
    a, b = np.asarray(a, float), np.asarray(b, float)
    days = np.arange(len(a))
    d = [sharpe(a[i]) - sharpe(b[i]) for i in block_resamples(days, block=block, n=n, seed=seed)]
    d = np.asarray(d)
    d = d[np.isfinite(d)]
    return {"point": sharpe(a) - sharpe(b), "lo": float(np.quantile(d, 0.025)),
            "hi": float(np.quantile(d, 0.975)), "n": int(len(d))}  # fmt: skip
