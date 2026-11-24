"""Kaplan-Meier estimator with delayed entry, on integer (trading-day) times.

A subject with entry e and exit x is at risk at time u if e < u <= x. With entry = 0 this is the
ordinary estimator on time since prediction; with entry = swing age at the row and
exit = age + duration it estimates the survival of swings by age (H3) under left truncation.
"""

from __future__ import annotations

import numpy as np


class KaplanMeier:
    def fit(self, exit_time, event, entry=None) -> KaplanMeier:
        x = np.asarray(exit_time, dtype="int64")
        d = np.asarray(event, dtype=bool)
        e = np.zeros_like(x) if entry is None else np.asarray(entry, dtype="int64")
        if np.any(x <= e):
            raise ValueError("exit must be after entry")
        self.max_time_ = int(x.max())
        times = np.arange(1, self.max_time_ + 1)
        # at risk at u: entered before u and exited at or after u
        entered = np.searchsorted(np.sort(e), times, side="left")  # count of e < u
        exited_before = np.searchsorted(np.sort(x), times, side="left")  # count of x < u
        at_risk = entered - exited_before
        deaths = np.bincount(x[d], minlength=self.max_time_ + 1)[1:]
        with np.errstate(divide="ignore", invalid="ignore"):
            h = np.where(at_risk > 0, deaths / at_risk, 0.0)
        self.times_ = times
        self.at_risk_ = at_risk
        self.hazard_ = h
        self.survival_ = np.cumprod(1 - h)
        return self

    def survival(self, t) -> np.ndarray:
        """S(t) for integer t >= 0 (S(0) = 1; flat beyond the last time)."""
        t = np.clip(np.asarray(t, dtype="int64"), 0, self.max_time_)
        s = np.concatenate([[1.0], self.survival_])
        return s[t]
