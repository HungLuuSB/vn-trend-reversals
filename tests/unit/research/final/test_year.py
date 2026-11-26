"""Final-run year step (D-026) on synthetic data: guards, censoring split, caches."""

import json

import numpy as np
import pandas as pd
import pytest

from vnbank.research.survival.final import year as Y
from vnbank.research.survival.walkforward import split

from .synth import make


def test_test_years_need_confirmation(tmp_path):
    ds, sessions = make(n_tickers=2)
    with pytest.raises(SystemExit):
        Y.run_year(ds, sessions, 2017, tmp_path)


def test_censored_split_keeps_late_rows_censored_at_the_boundary():
    ds, sessions = make(n_tickers=3)
    train, test = Y.censored_split(ds, sessions, 2011)
    purged, test2 = split(ds, sessions, 2011, dev=False)
    assert test.equals(test2)
    start = pd.Timestamp("2011-01-01")
    late = train.end_date >= start
    assert late.any() and (train.loc[late, "event"] == 0).all()
    assert len(train) > len(purged)  # rows are kept, not dropped
    # duration never reaches past the last session before the boundary
    k = np.searchsorted(sessions, start.to_datetime64())
    pos = np.searchsorted(sessions, train.loc[late, "trade_date"].to_numpy())
    assert (train.loc[late, "duration"].to_numpy() <= k - 1 - pos).all()
    assert (train.loc[late, "duration"] >= 20).all()  # embargo: at least 20 sessions remain
    assert train.loc[~late].equals(ds.loc[train.index[~late.to_numpy()]])


def test_run_year_writes_caches_without_metrics(tmp_path):
    ds, sessions = make()
    ds = Y.prepare(ds, prices=None)
    only = {"M", "DIST", "ABCDx", "boundary:M", "loo-gold_ret"}
    meta = Y.run_year(ds, sessions, 2011, tmp_path, only=only, log=lambda m: None)
    out = tmp_path / "2011"
    keys = pd.read_parquet(out / "keys.parquet")
    preds = np.load(out / "preds.npz")
    assert set(preds.files) >= {
        "km",
        "M",
        "DIST",
        "ABCDx",
        "shuffled:M",
        "shuffled:ABCDx",
        "boundary:M",
        "boundary:ABCDx",
        "boundary:km",
        "loo-gold_ret",
    }
    for k in ("km", "M", "ABCDx", "boundary:M"):
        s = preds[k]
        assert s.shape == (len(keys), 20) and np.all(np.diff(s, axis=1) <= 1e-6)
    assert preds["shuffled:M"].shape == (len(keys), 10)
    assert (keys.trade_date.dt.year == 2011).all()
    inner = pd.read_parquet(out / "inner_p5.parquet")
    assert (inner.trade_date.dt.year == 2010).all() and {"p5:ABCDx", "p5:M"} <= set(inner)
    saved = json.loads((out / "meta.json").read_text())
    assert set(saved["chosen"]) >= {"M", "DIST", "ABCDx"} and "abcdx_coef_std" in saved
    assert not any("uno_c" in k or "ibs" in k for k in json.dumps(saved).split('"'))
    # the planted signal: higher 5-day risk where swing_dist is closer to the trigger
    r5 = 1 - preds["M"][:, 4]
    assert np.corrcoef(r5, -keys.swing_dist)[0, 1] > 0.5
    assert meta["n"]["test"] == len(keys)
