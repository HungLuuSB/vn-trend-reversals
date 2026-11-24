"""Models behind one interface (research/paper1/DECISIONS.md D-014).

    model = make_model(name, features, **params).fit(train)        # train: DataFrame
    S = model.survival(val, times)                                  # (n_val, len(times))

Every model sees only its training rows: imputation and scaling are fitted there. Durations
beyond FIT_CAP days are censored at FIT_CAP for fitting (horizons of interest are <= 20).
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.impute import SimpleImputer
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from sksurv.ensemble import RandomSurvivalForest
from sksurv.linear_model import CoxPHSurvivalAnalysis
from sksurv.util import Surv

from vnbank.research.shared.config import grid, load
from vnbank.research.survival.models.hazard import LogisticHazard, expand
from vnbank.research.survival.models.km import KaplanMeier

CFG = load(1)  # research/paper1/configs/main.yaml

FIT_CAP = CFG["evaluation"]["fit_cap"]


def capped(train: pd.DataFrame) -> tuple[np.ndarray, np.ndarray]:
    d = train["duration"].to_numpy()
    e = train["event"].to_numpy()
    over = d > FIT_CAP
    return np.where(over, FIT_CAP, d), np.where(over, 0, e)


class KMModel:
    def __init__(self, features=None):
        self.km = KaplanMeier()

    def fit(self, train):
        d, e = capped(train)
        self.km.fit(d, e)
        return self

    def survival(self, X, times):
        return np.tile(self.km.survival(np.asarray(times)), (len(X), 1))


class LogitHazard:
    def __init__(self, features, C=1.0, l1_ratio=0.5, seed=0):
        self.m = LogisticHazard(features, C=C, l1_ratio=l1_ratio, seed=seed)

    def fit(self, train):
        d, e = capped(train)
        self.m.fit(train, d, e)
        return self

    def survival(self, X, times):
        return self.m.survival(X, np.asarray(times))


class GBMHazard:
    """Gradient-boosted discrete-time hazard on the landmark expansion (D-013, D-014)."""

    def __init__(self, features, learning_rate=0.1, max_leaf_nodes=31, max_step=20, seed=0):
        self.features = list(features)
        self.max_step = max_step
        self.clf = HistGradientBoostingClassifier(
            learning_rate=learning_rate, max_leaf_nodes=max_leaf_nodes, max_iter=300,
            l2_regularization=1.0, early_stopping=False, random_state=seed,
        )  # fmt: skip

    def _design(self, X, rows, steps):
        base = X[self.features].to_numpy(dtype="float64")[rows]
        return np.hstack([base, steps[:, None].astype("float64")])

    def fit(self, train):
        d, e = capped(train)
        rows, steps, target = expand(d, e, self.max_step)
        self.clf.fit(self._design(train, rows, steps), target)
        return self

    def survival(self, X, times):
        times = np.asarray(times)
        rows = np.arange(len(X))
        surv, out, j = np.ones(len(X)), np.empty((len(X), len(times))), 0
        for step in range(1, times.max() + 1):
            h = self.clf.predict_proba(self._design(X, rows, np.full(len(X), step)))[:, 1]
            surv = surv * (1 - h)
            while j < len(times) and times[j] == step:
                out[:, j] = surv
                j += 1
        return out


class _SksurvModel:
    """Shared wrapper for scikit-survival estimators on time since the prediction day."""

    def __init__(self, features, estimator):
        self.features = list(features)
        self.prep = make_pipeline(SimpleImputer(strategy="median"), StandardScaler())
        self.est = estimator

    def fit(self, train):
        d, e = capped(train)
        Xt = self.prep.fit_transform(train[self.features].to_numpy(dtype="float64"))
        self.est.fit(Xt, Surv.from_arrays(e.astype(bool), d.astype("float64")))
        return self

    def survival(self, X, times):
        Xv = self.prep.transform(X[self.features].to_numpy(dtype="float64"))
        fns = self.est.predict_survival_function(Xv)
        times = np.asarray(times, dtype="float64")
        return np.vstack([fn(np.clip(times, fn.x[0], fn.x[-1])) for fn in fns])


class CoxModel(_SksurvModel):
    def __init__(self, features, alpha=10.0, seed=0):
        super().__init__(features, CoxPHSurvivalAnalysis(alpha=alpha, ties="efron"))


class RSFModel(_SksurvModel):
    def __init__(self, features, min_samples_leaf=50, seed=0):
        super().__init__(features, RandomSurvivalForest(
            n_estimators=100, min_samples_leaf=min_samples_leaf, max_features="sqrt",
            n_jobs=2, random_state=seed, low_memory=False,
        ))  # fmt: skip


MODELS = {"km": KMModel, "logit": LogitHazard, "gbm": GBMHazard, "cox": CoxModel,
          "rsf": RSFModel}  # fmt: skip

GRIDS = {"km": [{}], **{m: grid(g) for m, g in CFG["tuning_grids"].items()}}  # D-014


def make_model(name: str, features, **params):
    if name == "km":
        return KMModel()
    return MODELS[name](features, **params)
