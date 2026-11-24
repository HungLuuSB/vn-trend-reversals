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


def test_grids_keep_the_d014_order():
    assert GRIDS["logit"] == [{"C": c, "l1_ratio": r} for c in (0.01, 0.1, 1.0) for r in (0.0, 0.5)]
    assert GRIDS["gbm"] == [{"learning_rate": lr, "max_leaf_nodes": m}
                            for lr in (0.03, 0.1) for m in (15, 31)]  # fmt: skip
    assert GRIDS["cox"] == [{"alpha": a} for a in (1.0, 10.0, 100.0)]
    assert GRIDS["rsf"] == [{"min_samples_leaf": m} for m in (50, 200)]
    assert grid({"a": [1, 2], "b": [3]}) == [{"a": 1, "b": 3}, {"a": 2, "b": 3}]
