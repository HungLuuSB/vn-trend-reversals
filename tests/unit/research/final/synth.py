"""Synthetic survival rows for the final-run tests: every column the specs use, a planted
signal (the hazard rises with -swing_dist), years 2008-2012 (never a test year)."""

import numpy as np
import pandas as pd

from vnbank.research.survival.features.assemble import BLOCKS, FEATURES_C_ROBUST


def make(
    n_tickers: int = 12,
    seed: int = 0,
    start="2008-01-01",
    end="2012-12-31",
    base: float = 0.03,
    slope: float = 0.25,
):
    rng = np.random.default_rng(seed)
    sessions = pd.bdate_range(start, end).to_numpy()
    rows = []
    for i in range(n_tickers):
        tk = f"T{i:02d}"
        for j in range(0, len(sessions) - 1, 2):  # every other session: keeps tests fast
            dist = -rng.uniform(0, 1)
            h = base + slope * (-dist)  # planted: closer to the trigger -> earlier reversal
            dur = int(min(rng.geometric(h), 60))
            k = min(j + dur, len(sessions) - 1)
            rows.append(
                (
                    tk,
                    sessions[j],
                    dur,
                    1 if j + dur < len(sessions) else 0,
                    sessions[k],
                    dist,
                    i % 3 == 0,
                )
            )
    ds = pd.DataFrame(
        rows,
        columns=["ticker", "trade_date", "duration", "event", "end_date", "swing_dist", "is_bank"],
    )
    n = len(ds)
    for cols in BLOCKS.values():
        for c in cols:
            if c not in ds:
                ds[c] = rng.normal(size=n)
    ds["swing_dir"] = rng.choice([-1, 1], n)
    ds["swing_age"] = rng.integers(1, 80, n).astype(float)
    ds["log_age"] = np.log1p(ds.swing_age)
    for c in FEATURES_C_ROBUST:
        ds[c] = np.where(rng.random(n) < 0.1, np.nan, rng.normal(size=n))
    ds["in_vn30"] = ~ds.is_bank
    ds["close_at_limit"] = 0.0
    ds["limit_known_5"] = 1.0
    ds["bank_on_upcom"] = False
    ds["trade_date"] = pd.to_datetime(ds.trade_date)
    ds["end_date"] = pd.to_datetime(ds.end_date)
    return ds, sessions
