"""RQ4 (D-026 5a): the Wald test finds a planted post-announcement effect and no effect where
none is planted; placebos and censoring behave."""

import numpy as np
import pandas as pd

from vnbank.research.survival.features.assemble import add_direction_interactions
from vnbank.research.survival.final import rq4

from .synth import make

ANN = pd.Timestamp("2011-10-07")
END = pd.Timestamp("2012-12-31")


def _data(effect: float, seed=0):
    ds, sessions = make(n_tickers=16, seed=seed, base=0.08, slope=0.05)
    ds = add_direction_interactions(ds)
    rng = np.random.default_rng(seed + 1)
    post = ds.trade_date >= ANN
    hit = post & (ds.spx_ret_xdir > 0.5)
    if effect:  # planted: after the announcement, an up-move in spx ends swings quickly
        quick = hit & (rng.random(len(ds)) < effect)
        ds.loc[quick, "duration"] = 1
        ds.loc[quick, "event"] = 1
        pos = np.searchsorted(sessions, ds.loc[quick, "trade_date"].to_numpy()) + 1
        ds.loc[quick, "end_date"] = sessions[np.minimum(pos, len(sessions) - 1)]
    return ds, sessions


def test_censor_at_cuts_labels_at_the_sample_end():
    ds, sessions = _data(0)
    end = pd.Timestamp("2010-06-30")
    d = rq4.censor_at(ds, sessions, end)
    assert d.trade_date.max() <= end
    late = ds.loc[d.index, "end_date"] > end
    assert (d.loc[late, "event"] == 0).all()
    k = np.searchsorted(sessions, end.to_datetime64(), side="right") - 1
    assert (d.duration + np.searchsorted(sessions, d.trade_date.to_numpy()) <= k).loc[late].all()


def test_planted_effect_is_found_and_beats_placebos():
    ds, sessions = _data(0.6)
    res = rq4.run(ds, sessions, ANN, END, placebo_years=[2009, 2010], log=lambda m: None)
    assert res["real"]["p"] < 0.01 and res["real"]["coef"]["spx_ret_xdir"] > 0
    assert res["real"]["p"] == max(res["real"]["two_way"]["p"], res["real"]["date"]["p"])
    assert res["beats_every_placebo"] and res["h4_supported"] and res["rank_of_real"] == 1


def test_no_effect_is_not_supported():
    ds, sessions = _data(0)
    res = rq4.run(ds, sessions, ANN, END, placebo_years=[2009, 2010], log=lambda m: None)
    assert res["real"]["p"] > 0.01
