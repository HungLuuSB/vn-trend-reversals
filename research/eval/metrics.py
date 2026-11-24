"""Survival metrics named in CLAUDE.md: Uno's C-index, IPCW integrated Brier score,
time-dependent AUC and calibration at 5/10/20 days (scikit-survival implementations)."""

from __future__ import annotations

import numpy as np
import pandas as pd
from sksurv.metrics import (
    concordance_index_ipcw,
    cumulative_dynamic_auc,
    integrated_brier_score,
)
from sksurv.util import Surv

from research.models.km import KaplanMeier


def surv(event, duration) -> np.ndarray:
    return Surv.from_arrays(np.asarray(event, dtype=bool), np.asarray(duration, dtype="float64"))


def clip_to_train(y_test: np.ndarray, y_train: np.ndarray) -> np.ndarray:
    """IPCW needs test follow-up inside the training follow-up: longer test times are
    censored at the last training time (administrative censoring)."""
    cap = y_train["time"].max() - 1
    t = np.minimum(y_test["time"], cap)
    e = y_test["event"] & (y_test["time"] <= cap)
    return Surv.from_arrays(e, t)


def uno_c(y_train, y_test, risk, tau: float) -> float:
    return float(concordance_index_ipcw(y_train, clip_to_train(y_test, y_train), risk, tau=tau)[0])


def ibs(y_train, y_test, surv_matrix: np.ndarray, times: np.ndarray) -> float:
    return float(integrated_brier_score(y_train, clip_to_train(y_test, y_train), surv_matrix,
                                        times))  # fmt: skip


def td_auc(y_train, y_test, risk_matrix: np.ndarray, times: np.ndarray) -> np.ndarray:
    auc, _ = cumulative_dynamic_auc(y_train, clip_to_train(y_test, y_train), risk_matrix, times)
    return auc


def calibration(pred_event_prob, event, duration, horizon: int, bins: int = 10) -> pd.DataFrame:
    """Predicted P(event within horizon) vs Kaplan-Meier observed, by predicted-risk decile."""
    df = pd.DataFrame({"p": pred_event_prob, "e": event, "d": duration})
    df["bin"] = pd.qcut(df["p"].rank(method="first"), bins, labels=False)
    out = []
    for b, g in df.groupby("bin"):
        km = KaplanMeier().fit(g["d"], g["e"])
        out.append((int(b), len(g), g["p"].mean(), 1 - float(km.survival(horizon))))
    return pd.DataFrame(out, columns=["bin", "n", "predicted", "observed"])
