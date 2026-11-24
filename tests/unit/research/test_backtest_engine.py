"""Hand-built series with known outcomes for the D-021 trading rules."""

import numpy as np
import pandas as pd
import pytest

from vnbank.research.survival.backtest.engine import Costs, StockDays, settlement_cycle, simulate


def days(start="2016-03-01", n=10, swing=None, open_raw=None, floor=None, ceiling=None,
         eligible=None, known=True):  # fmt: skip
    dates = pd.bdate_range(start, periods=n).to_numpy()
    o = np.full(n, 100.0) if open_raw is None else np.asarray(open_raw, float)
    return StockDays(
        dates=dates, session=np.arange(n), open_adj=o.copy(), open_raw=o,
        ceiling=np.full(n, 1e9) if ceiling is None else np.asarray(ceiling, float),
        floor=np.full(n, -1.0) if floor is None else np.asarray(floor, float),
        limit_known=np.full(n, known), close_at_floor=np.zeros(n, bool),
        eligible=np.ones(n, bool) if eligible is None else np.asarray(eligible, bool),
        swing_dir=np.asarray(swing if swing is not None else [1] * n),
    )  # fmt: skip


def first(df, col):
    hits = np.flatnonzero(df[col].to_numpy())
    return int(hits[0]) + 1 if len(hits) else None  # +1: output starts at stock row 1


def test_settlement_cycle_switches_on_2016_01_04():
    d = np.array(["2015-12-31", "2016-01-04"], dtype="datetime64[ns]")
    assert settlement_cycle(d).tolist() == [3, 2]


def test_t_plus_2_earliest_sell_is_the_open_after_settlement():
    # up-swing confirmed at row 0 -> buy at row 1; down-reversal confirmed at row 1 close
    sd = days(swing=[1, -1, -1, -1, -1, -1, -1, -1, -1, -1])
    out = simulate(sd, "dc")
    assert first(out, "buy") == 1
    assert first(out, "sell") == 1 + 2 + 1  # T+2: settled in the afternoon of row 3


def test_t_plus_3_before_2016():
    sd = days(start="2015-03-02", swing=[1, -1, -1, -1, -1, -1, -1, -1, -1, -1])
    out = simulate(sd, "dc")
    assert first(out, "sell") == 1 + 3 + 1


def test_no_sell_fill_at_limit_down_open():
    floor = np.full(10, -1.0)
    floor[4] = 100.0  # open at the floor on the first allowed sell day
    out = simulate(days(swing=[1] + [-1] * 9, floor=floor), "dc")
    assert first(out, "sell") == 5


def test_no_buy_fill_at_limit_up_open_and_retry():
    ceiling = np.full(10, 1e9)
    ceiling[1] = 100.0
    out = simulate(days(swing=[1] * 10, ceiling=ceiling), "dc")
    assert first(out, "buy") == 2


def test_costs_and_returns_are_attributed_to_the_right_days():
    o = [100, 100, 110, 121, 121, 121, 121, 121, 121, 121]
    sd = days(swing=[1, 1, 1, 1, -1, -1, -1, -1, -1, -1], open_raw=o)
    out = simulate(sd, "dc", costs=Costs(buy=0.001, sell=0.002))
    r = out.ret.to_numpy()
    assert r[0] == pytest.approx(-0.001)  # row 1: buy cost only
    assert r[1] == pytest.approx(0.10)  # row 2: 100 -> 110
    assert r[2] == pytest.approx(0.10)  # row 3: 110 -> 121
    assert first(out, "sell") == 5 and r[3] == pytest.approx(0.0)  # row 4: 121 -> 121
    assert r[5 - 1] == pytest.approx(-0.002)  # row 5: sell cost


def test_model_exit_and_no_entry_when_exit_already_signalled():
    p5 = np.array([0.1, 0.1, 0.1, 0.1, 0.9, 0.1, 0.1, 0.1, 0.1, 0.1])
    out = simulate(days(swing=[1] * 10), "model", p5=p5, tau=0.5)
    assert first(out, "buy") == 1 and first(out, "sell") == 5
    assert out.buy.sum() == 1  # no re-entry within the same up-swing
    out = simulate(days(swing=[1] * 10), "model", p5=np.full(10, 0.9), tau=0.5)
    assert out.buy.sum() == 0


def test_buy_and_hold_and_window_close():
    elig = [True] * 6 + [False] * 4
    out = simulate(days(eligible=elig), "bh", costs=Costs(0.001, 0.002))
    assert first(out, "buy") == 1 and first(out, "sell") == 6
    sd = days()
    out = simulate(sd, "bh", window=(sd.dates[0], sd.dates[5]), costs=Costs(0.001, 0.002))
    assert len(out) == 5 and out.sell.iloc[-1] and out.ret.iloc[-1] == pytest.approx(-0.002)


def test_entry_order_lapses_if_not_eligible_at_the_open():
    out = simulate(days(swing=[1] * 10, eligible=[True, False] + [True] * 8), "dc")
    assert out.buy.sum() == 0  # confirmed at row 0, not tradable at row 1: swing skipped


def test_round_trip_cost_split():
    assert Costs.round_trip(0.004) == Costs(0.0015, 0.0025)
    assert Costs.round_trip(0.002).buy == pytest.approx(0.0005)
    assert Costs.round_trip(0.008).sell == pytest.approx(0.0045)
