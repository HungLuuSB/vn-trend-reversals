"""D-022: sequence inputs are point-in-time; hazard targets; the neural hazard learns a planted
signal and is deterministic for a fixed seed."""

import numpy as np
import pandas as pd

from vnbank.research.survival.features.sequence import SEQ, add_sequences, seq_columns
from vnbank.research.survival.models.neural import NNHazard, targets


def _prices(n=120, seed=0, ticker="AAA"):
    rng = np.random.default_rng(seed)
    close = 10 * np.exp(np.cumsum(rng.normal(0, 0.02, n)))
    open_ = close * np.exp(rng.normal(0, 0.005, n))
    return pd.DataFrame({
        "ticker": ticker,
        "trade_date": pd.bdate_range("2014-01-01", periods=n),
        "open_adj": open_, "close_adj": close,
        "high_adj": np.maximum(open_, close) * 1.01, "low_adj": np.minimum(open_, close) * 0.99,
        "volume": rng.integers(1_000, 5_000, n).astype(float),
    })  # fmt: skip


def test_sequence_uses_only_days_up_to_t():
    px = _prices()
    t = px.trade_date.iloc[80]
    ds = pd.DataFrame({"ticker": ["AAA"], "trade_date": [t]})
    a = add_sequences(ds, px)[seq_columns()]
    later = px.trade_date > t
    px2 = px.copy()
    px2.loc[later, ["open_adj", "close_adj", "high_adj", "low_adj"]] *= 3.0
    px2.loc[later, "volume"] *= 7.0
    b = add_sequences(ds, px2)[seq_columns()]
    pd.testing.assert_frame_equal(a, b)
    c = px.close_adj.to_numpy()
    assert np.isclose(a["seq_r_0"].iloc[0], np.log(c[80] / c[79]), rtol=1e-5)  # lag 0 = day t
    assert np.isclose(a["seq_r_59"].iloc[0], np.log(c[21] / c[20]), rtol=1e-5)  # oldest day
    v = px.volume.to_numpy()
    assert np.isclose(a["seq_vr_0"].iloc[0], np.log(v[80] / v[60:80].mean()), rtol=1e-5)


def test_sequence_short_history_is_left_padded_with_nan():
    px = _prices()
    ds = pd.DataFrame({"ticker": ["AAA"], "trade_date": [px.trade_date.iloc[10]]})
    s = add_sequences(ds, px)
    assert np.isnan(s["seq_hl_59"].iloc[0]) and not np.isnan(s["seq_hl_0"].iloc[0])
    assert np.isnan(s["seq_r_10"].iloc[0])  # day 0 has no previous close


def test_targets_mark_at_risk_steps_and_event_step():
    y, m = targets([2, 3, 25], [1, 0, 1], max_step=4)
    assert m.tolist() == [[1, 1, 0, 0], [1, 1, 1, 0], [1, 1, 1, 1]]
    assert y.tolist() == [[0, 1, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0]]


def _synthetic(n=3000, seed=1):
    rng = np.random.default_rng(seed)
    x = rng.normal(size=n)
    hazard = 1 / (1 + np.exp(-(-2.0 + 1.2 * x)))  # constant daily hazard driven by x
    dur = np.minimum(rng.geometric(hazard), 30)
    event = (dur < 30).astype(int)
    df = pd.DataFrame({"x": x, "noise": rng.normal(size=n), "duration": dur, "event": event})
    seq = pd.DataFrame(np.zeros((n, len(seq_columns())), dtype="float32"), columns=seq_columns())
    return pd.concat([df, seq], axis=1)


def test_nn_learns_a_planted_signal_and_is_deterministic():
    df = _synthetic()
    tr, va = df.iloc[:2000], df.iloc[2000:]
    m1 = NNHazard(["x", "noise", SEQ], hidden=8, weight_decay=1e-4, epochs=30).fit(tr)
    s1 = m1.survival(va, np.array([1, 5, 20]))
    assert (np.diff(s1, axis=1) <= 1e-12).all()  # survival non-increasing in time
    risk = 1 - s1[:, 1]
    assert np.corrcoef(risk, va.x)[0, 1] > 0.8  # higher x -> higher reversal risk
    s2 = NNHazard(["x", "noise", SEQ], hidden=8, weight_decay=1e-4, epochs=30).fit(tr).survival(
        va, np.array([1, 5, 20]))  # fmt: skip
    np.testing.assert_array_equal(s1, s2)


def test_nn_seed_average_equals_mean_of_single_seeds():
    df = _synthetic(n=800)
    times = np.array([5, 20])
    both = NNHazard(["x"], hidden=4, epochs=1, seeds=(0, 1)).fit(df).survival(df, times)
    one = [NNHazard(["x"], hidden=4, epochs=1, seed=k).fit(df).survival(df, times) for k in (0, 1)]
    np.testing.assert_allclose(both, (one[0] + one[1]) / 2, rtol=1e-6)


def test_nn_starts_at_the_empirical_hazard_level():
    """Output bias initialised at the training hazard (D-022): after one epoch the mean
    predicted 5-day reversal probability is close to the observed share."""
    df = _synthetic()
    s = NNHazard(["x"], hidden=8, epochs=1).fit(df).survival(df, np.array([5]))
    observed = ((df.event == 1) & (df.duration <= 5)).mean()
    assert abs((1 - s[:, 0]).mean() - observed) < 0.05
