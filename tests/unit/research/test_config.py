"""The Paper 1 config must keep the pre-registered design (DECISIONS.md D-001, D-011-D-014).
Changing a value here is a design change: log it in research/paper1/DECISIONS.md first."""

import datetime as dt

from vnbank.research.shared.config import grid, load
from vnbank.research.survival.models.zoo import GRIDS


def test_main_design_is_the_pre_registered_one():
    c = load(1)
    assert c["study"]["start"] == dt.date(2012, 1, 3)
    assert c["study"]["end"] == dt.date(2026, 11, 20)
    assert c["labels"]["k_main"] == 2.0 and c["labels"]["k_robustness"] == [1.5, 3.0]
    assert c["labels"]["atr_window"] == 20
    assert c["evaluation"]["main_horizon"] == 5
    assert c["walkforward"]["embargo_sessions"] == 20
    assert c["walkforward"]["dev_folds"] == [2014, 2015, 2016]
    assert c["walkforward"]["test_years"] == list(range(2017, 2027))
    assert c["risk_set"] == {"min_history_days": 250, "halt_gap_sessions": 5}
    assert c["neural"]["seq_len"] == 60 and c["neural"]["outer_seeds"] == [0, 1, 2]  # D-022
    assert c["decision"] == {"hour_local": 9, "tz": "Asia/Ho_Chi_Minh"}
    assert c["block_e"] == {"margin_sessions": 5, "margin_robustness": [0, 20]}  # D-023
    assert c["evaluation"]["bootstrap"] == {"block": 20, "resamples": 200}  # D-014
    assert c["backtest"] == {  # D-021
        "round_trip_cost": 0.004, "sales_tax": 0.001, "cost_sensitivity": [0.002, 0.008],
        "tau_grid": [0.25, 0.30, 0.35, 0.40, 0.45, 0.50, 0.55, 0.60]}  # fmt: skip


def test_values_outside_python_match_the_config():
    """The study window is also written in dbt SQL; it must equal the config (D-001)."""
    import re

    from vnbank.common import paths
    from vnbank.research.survival.backtest.engine import Costs

    c = load(1)
    sql = (paths.REPO / "dbt/models/universe/research_universe_daily.sql").read_text()
    start = re.search(r"study_start = '([\d-]+)'", sql)[1]
    end = re.search(r"study_end = '([\d-]+)'", sql)[1]
    assert (start, end) == (str(c["study"]["start"]), str(c["study"]["end"]))
    main = Costs.round_trip(c["backtest"]["round_trip_cost"], c["backtest"]["sales_tax"])
    assert abs(main.buy + main.sell - 0.004) < 1e-12 and main == Costs()  # engine default = main


def test_grids_keep_the_d014_order():
    assert GRIDS["logit"] == [{"C": c, "l1_ratio": r} for c in (0.01, 0.1, 1.0) for r in (0.0, 0.5)]
    assert GRIDS["gbm"] == [{"learning_rate": lr, "max_leaf_nodes": m}
                            for lr in (0.03, 0.1) for m in (15, 31)]  # fmt: skip
    assert GRIDS["cox"] == [{"alpha": a} for a in (1.0, 10.0, 100.0)]
    assert GRIDS["rsf"] == [{"min_samples_leaf": m} for m in (50, 200)]
    assert GRIDS["nn"] == [
        {"hidden": h, "weight_decay": w, "epochs": e}
        for h in (16, 32)
        for w in (0.0001, 0.001)
        for e in (5, 15)
    ]  # D-022
    assert grid({"a": [1, 2], "b": [3]}) == [{"a": 1, "b": 3}, {"a": 2, "b": 3}]
