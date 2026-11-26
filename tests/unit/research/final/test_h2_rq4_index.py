"""D-027 items 5 and 6 on synthetic data: H2 sign test and the RQ4 single-index test."""

import numpy as np
import pandas as pd

from vnbank.research.survival.features.assemble import (
    add_bank_interactions,
    add_direction_interactions,
)
from vnbank.research.survival.final import h2, rq4

from .synth import make

ANN = pd.Timestamp("2011-10-07")


def _quick(ds, sessions, mask):
    ds.loc[mask, "duration"] = 1
    ds.loc[mask, "event"] = 1
    pos = np.searchsorted(sessions, ds.loc[mask, "trade_date"].to_numpy()) + 1
    ds.loc[mask, "end_date"] = sessions[np.minimum(pos, len(sessions) - 1)]


def _data(seed=0):
    ds, sessions = make(n_tickers=16, seed=seed, base=0.08, slope=0.05)
    return add_bank_interactions(add_direction_interactions(ds)), sessions


def test_h2_finds_a_planted_negative_spx_direction_effect():
    ds, sessions = _data()
    rng = np.random.default_rng(5)
    _quick(ds, sessions, (ds.spx_ret_xdir < -0.5) & (rng.random(len(ds)) < 0.5))
    res = h2.run(ds, sessions, pd.Timestamp("2012-12-31"))
    assert res["signs"]["spx_ret_xdir"]["supported"]
    assert res["signs"]["spx_ret_xdir"]["coef"] < 0
    assert not res["signs"]["vix_chg_xdir"]["supported"]
    assert 0 <= res["bank_joint"]["p"] <= 1 and len(res["bank_terms"]) == 6


def test_rq4_single_index_detects_a_larger_post_effect():
    ds, sessions = _data(seed=1)
    rng = np.random.default_rng(6)
    pre = ds.trade_date < ANN
    hit = ds.spx_ret_xdir < -0.5
    _quick(ds, sessions, hit & pre & (rng.random(len(ds)) < 0.15))
    _quick(ds, sessions, hit & ~pre & (rng.random(len(ds)) < 0.7))
    res = rq4.run_index(
        ds, sessions, ANN, pd.Timestamp("2012-12-31"), placebo_years=[2010], log=lambda m: None
    )
    assert res["real"]["p"] < 0.01 and res["real"]["coef"] > 0
    assert res["h4_supported"] and res["rank_of_real"] == 1


def test_rq4_single_index_null():
    ds, sessions = _data(seed=2)
    res = rq4.run_index(
        ds, sessions, ANN, pd.Timestamp("2012-12-31"), placebo_years=[2010], log=lambda m: None
    )
    assert res["real"]["p"] > 0.01
