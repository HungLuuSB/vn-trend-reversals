"""Discrete-time logistic hazard fitted by landmarking (docs/proposals/paper1-trend-reversals.md,
model 3;
research/DECISIONS.md D-013).

Each survival row (stock, t) is a landmark: a prediction made after the close of t. For
steps s = 1 .. min(duration, H) the row contributes one at-risk period with target 1 if the
reversal is confirmed exactly s trading days after t (event and s == duration). Features stay at
their day-t values; the step s enters as indicator columns, so the model learns h(s | x_t), the
hazard s days after the prediction. Then S(h | x_t) = prod_{s <= h} (1 - h(s | x_t)).
Imputation and scaling are fitted on training rows only (CLAUDE.md research rules).
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

MAX_STEP = 20


def expand(duration, event, max_step: int = MAX_STEP) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Landmark expansion: (row index, step s, target) for every at-risk step."""
    d = np.asarray(duration, dtype="int64")
    e = np.asarray(event, dtype="int64")
    n_steps = np.minimum(d, max_step)
    rows = np.repeat(np.arange(len(d)), n_steps)
    steps = np.concatenate([np.arange(1, k + 1) for k in n_steps]) if len(d) else np.array([])
    target = ((steps == d[rows]) & (e[rows] == 1)).astype("int8")
    return rows, steps.astype("int64"), target


def one_day_target(event, duration) -> np.ndarray:
    return ((np.asarray(event) == 1) & (np.asarray(duration) == 1)).astype("int8")


class LogisticHazard:
    def __init__(self, features: list[str], C: float = 1.0, l1_ratio: float = 0.5,
                 max_step: int = MAX_STEP, seed: int = 0):  # fmt: skip
        self.features = list(features)
        self.max_step = max_step
        self.model = make_pipeline(
            SimpleImputer(strategy="median"),
            StandardScaler(),
            LogisticRegression(
                l1_ratio=l1_ratio, C=C, solver="saga", max_iter=3000, random_state=seed
            ),  # fmt: skip
        )

    def _design(self, X: pd.DataFrame, rows: np.ndarray, steps: np.ndarray) -> np.ndarray:
        base = X[self.features].to_numpy(dtype="float64")[rows]
        step_dummies = (steps[:, None] == np.arange(1, self.max_step + 1)[None, :]).astype(float)
        return np.hstack([base, step_dummies])

    def fit(self, X: pd.DataFrame, duration, event) -> LogisticHazard:
        rows, steps, target = expand(duration, event, self.max_step)
        self.model.fit(self._design(X, rows, steps), target)
        return self

    def hazard(self, X: pd.DataFrame, step: int) -> np.ndarray:
        rows = np.arange(len(X))
        steps = np.full(len(X), step, dtype="int64")
        return self.model.predict_proba(self._design(X, rows, steps))[:, 1]

    def survival(self, X: pd.DataFrame, horizons: np.ndarray) -> np.ndarray:
        """S(h | x_t) for each h in horizons (increasing, <= max_step): (n_rows, len)."""
        horizons = np.asarray(horizons, dtype="int64")
        if horizons.max() > self.max_step:
            raise ValueError("horizon beyond the fitted steps")
        surv = np.ones(len(X))
        out = np.empty((len(X), len(horizons)))
        j = 0
        for step in range(1, horizons.max() + 1):
            surv = surv * (1 - self.hazard(X, step))
            while j < len(horizons) and horizons[j] == step:
                out[:, j] = surv
                j += 1
        return out
