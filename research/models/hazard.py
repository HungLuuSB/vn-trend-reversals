"""Discrete-time logistic hazard (docs/proposal.md, model 3: "the main interpretable model").

Each survival row (stock, t) is one at-risk day; the target is whether the swing's reversal is
confirmed on the next trading day (event and duration == 1). Survival over h days is the
product of one-day survival probabilities with the swing age advanced day by day and the other
features held at their value on t. Imputation and scaling are fitted on the training rows
only (CLAUDE.md research rules).
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

AGE_COLUMNS = ("swing_age", "log_age")


def one_day_target(event, duration) -> np.ndarray:
    return ((np.asarray(event) == 1) & (np.asarray(duration) == 1)).astype("int8")


class LogisticHazard:
    def __init__(self, features: list[str], C: float = 1.0, l1_ratio: float = 0.5, seed: int = 0):
        self.features = list(features)
        self.model = make_pipeline(
            SimpleImputer(strategy="median"),
            StandardScaler(),
            LogisticRegression(
                l1_ratio=l1_ratio, C=C, solver="saga", max_iter=2000, random_state=seed
            ),  # fmt: skip
        )

    def fit(self, X: pd.DataFrame, y1: np.ndarray) -> LogisticHazard:
        self.model.fit(X[self.features], y1)
        return self

    def hazard(self, X: pd.DataFrame) -> np.ndarray:
        return self.model.predict_proba(X[self.features])[:, 1]

    def survival(self, X: pd.DataFrame, horizons: np.ndarray) -> np.ndarray:
        """S(h | x_t) for each h in horizons (increasing), shape (n_rows, len(horizons))."""
        horizons = np.asarray(horizons, dtype="int64")
        surv = np.ones(len(X))
        out = np.empty((len(X), len(horizons)))
        Xs = X.copy()
        j = 0
        for step in range(1, horizons.max() + 1):
            surv = surv * (1 - self.hazard(Xs))
            if step == horizons[j]:
                out[:, j] = surv
                j += 1
            # advance the swing age by one day for the next step
            if "swing_age" in Xs:
                Xs["swing_age"] = Xs["swing_age"] + 1
            if "log_age" in Xs:
                Xs["log_age"] = np.log1p(Xs["swing_age"])
        return out
