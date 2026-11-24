"""Paired moving-block bootstrap over validation trading dates (research/paper1/DECISIONS.md D-014).

Validation rows from the same days (and the same swings) are strongly dependent, so rows are
resampled in blocks of consecutive trading dates. The same resamples are used for every model,
so paired differences (e.g. with vs without the global block) get valid intervals.
"""

from __future__ import annotations

from collections.abc import Callable

import numpy as np


def block_resamples(dates: np.ndarray, block: int = 20, n: int = 200, seed: int = 0):
    """Yield arrays of row indices; each resample draws whole blocks of consecutive dates
    (with replacement) until it covers as many dates as the original."""
    uniq = np.unique(dates)
    rows_by_date = {d: np.flatnonzero(dates == d) for d in uniq}
    n_dates = len(uniq)
    rng = np.random.default_rng(seed)
    starts = np.arange(max(1, n_dates - block + 1))
    for _ in range(n):
        picked: list[np.ndarray] = []
        count = 0
        while count < n_dates:
            s = rng.choice(starts)
            for d in uniq[s : s + block]:
                picked.append(rows_by_date[d])
            count += min(block, n_dates - s)
        yield np.concatenate(picked)


def paired_ci(
    dates: np.ndarray,
    stats: dict[str, Callable[[np.ndarray], float]],
    block: int = 20,
    n: int = 200,
    seed: int = 0,
    level: float = 0.95,
) -> dict[str, dict[str, float]]:
    """Percentile intervals for named statistics computed on the same resamples.
    Each stat maps resampled row indices -> value."""
    draws = {k: [] for k in stats}
    for idx in block_resamples(dates, block, n, seed):
        for k, f in stats.items():
            draws[k].append(f(idx))
    lo, hi = (1 - level) / 2, 1 - (1 - level) / 2
    out = {}
    for k, v in draws.items():
        a = np.asarray(v, dtype="float64")
        a = a[np.isfinite(a)]
        out[k] = {"lo": float(np.quantile(a, lo)), "hi": float(np.quantile(a, hi)),
                  "n": int(len(a))}  # fmt: skip
    return out
