from vnbank.research.survival.dev_decompose import DIFFS, SPECS
from vnbank.research.survival.features.assemble import FEATURES_D


def test_specs_are_nested_and_exclude_global_block():
    names = list(SPECS)
    for small, big in zip(names, names[1:], strict=False):
        assert set(SPECS[small]) < set(SPECS[big])
    assert not set(SPECS["ABC"]) & set(FEATURES_D)
    assert all(a in SPECS and b in SPECS for a, b in DIFFS)


def test_d016_specs_build_on_the_mechanical_baseline():
    from vnbank.research.survival.dev_decompose import DIFFS_D016, SPECS_D016
    from vnbank.research.survival.features.assemble import FEATURES_A, FEATURES_MECH

    assert set(FEATURES_MECH) <= set(FEATURES_A)
    for name in ("MB", "MBC", "MD"):
        assert set(SPECS_D016["M"]) < set(SPECS_D016[name])
    assert set(SPECS_D016["MB"]) < set(SPECS_D016["MBC"])
    assert not set(SPECS_D016["MBC"]) & set(FEATURES_D)
    assert set(FEATURES_D) <= set(SPECS_D016["ABCD"])
    assert all(a in SPECS_D016 and b in SPECS_D016 for a, b in DIFFS_D016)


def test_direction_interactions_flip_with_the_swing():
    import numpy as np
    import pandas as pd

    from vnbank.research.survival.features.assemble import BLOCKS, add_direction_interactions

    cols = [c for b in "BCD" for c in BLOCKS[b]]
    ds = pd.DataFrame({c: [0.02, 0.02, np.nan] for c in cols})
    ds["swing_dir"] = np.array([1, -1, 1], dtype="int8")
    out = add_direction_interactions(ds)
    assert out["spx_ret_xdir"].tolist()[:2] == [0.02, -0.02]
    assert np.isnan(out["spx_ret_xdir"].iloc[2])


def test_d017_specs():
    from vnbank.research.survival.dev_decompose import DIFFS_D017, SPECS_D017, model_and_features

    assert not any(c.startswith(tuple(FEATURES_D)) for c in SPECS_D017["MBCx"])
    assert set(SPECS_D017["MBCx"]) < set(SPECS_D017["MBCDx"])
    assert set(SPECS_D017["ABCx"]) < set(SPECS_D017["ABCDx"])
    assert "spx_ret_xdir" in SPECS_D017["ABCDx"]
    assert all(a in SPECS_D017 and b in SPECS_D017 for a, b in DIFFS_D017)
    assert model_and_features(("gbm", ["x"])) == ("gbm", ["x"])


def test_runner_end_to_end_on_a_tiny_dataset(tmp_path, monkeypatch):
    """Every protocol must run to its final summary line (the D-016 run crashed there)."""
    import json

    import numpy as np
    import pandas as pd

    import vnbank.research.survival.dev_decompose as dd
    from vnbank.research.survival.features.assemble import BLOCKS

    sessions = pd.bdate_range("2012-01-02", "2016-12-30")
    rng = np.random.default_rng(0)
    rows = []
    for i in range(0, len(sessions) - 25, 3):
        dur = int(rng.integers(1, 25))
        rows.append({"trade_date": sessions[i], "end_date": sessions[i + dur], "duration": dur,
                     "event": int(rng.random() < 0.7),
                     "days_to_dev_end": len(sessions) - 1 - i})  # fmt: skip
    ds = pd.DataFrame(rows)
    for c in [c for b in "ABCD" for c in BLOCKS[b]]:
        ds[c] = rng.normal(size=len(ds))
    ds["swing_dir"] = rng.choice([-1, 1], size=len(ds)).astype("int8")
    fr = tmp_path / "features"
    fr.mkdir()
    ds.to_parquet(fr / "dataset.parquet")
    (fr / "config.json").write_text(json.dumps({"snapshot_id": "snap"}))
    snap = tmp_path / "data" / "snapshots" / "snap"
    snap.mkdir(parents=True)
    pd.DataFrame({"trade_date": sessions}).to_parquet(snap / "sessions_hose.parquet")
    monkeypatch.setattr(dd, "REPO", tmp_path)
    monkeypatch.setattr(dd, "RUNS", tmp_path / "research" / "paper1" / "runs")
    monkeypatch.setattr(dd, "code_version", lambda: "test")
    for protocol in ("D-016", "D-017"):
        assert dd.main(["--features-run", str(fr), "--bootstrap", "2",
                        "--protocol", protocol]) == 0  # fmt: skip


def test_d019_specs_and_aging_helpers():
    import numpy as np
    import pandas as pd

    from vnbank.research.survival.aging import H, empirical
    from vnbank.research.survival.dev_decompose import DIFFS_D019, SPECS_D019

    assert set(SPECS_D019["DIST"]) < set(SPECS_D019["M"])
    assert ("M", "DIST") in DIFFS_D019
    # hand-built rows: 2 reversals within H among 3 known rows in one bucket; 1 unknown row
    ds = pd.DataFrame({"swing_age": [3, 3, 3, 3], "swing_dist": [-0.1, -0.2, -0.3, -0.4],
                       "event": [1, 1, 0, 0], "duration": [2, H, H + 3, 1]})  # fmt: skip
    out = empirical(ds)
    assert out.n.sum() == 3 and np.isclose((out.share * out.n).sum(), 2)


def test_d020_bank_interactions():
    import numpy as np
    import pandas as pd

    from vnbank.research.survival.dev_decompose import SPECS_D020
    from vnbank.research.survival.features.assemble import BANK_CHANNELS, add_bank_interactions

    ds = pd.DataFrame({"is_bank": [True, False, True], "swing_dir": [1, 1, -1],
                       **{c: [0.01, 0.01, 0.02] for c in BANK_CHANNELS}})  # fmt: skip
    out = add_bank_interactions(ds)
    assert out["bank_x_dxy_ret"].tolist() == [0.01, 0.0, 0.02]
    assert np.allclose(out["bank_x_dxy_ret_xdir"], [0.01, 0.0, -0.02])
    assert set(SPECS_D020["ABCDx"]) < set(SPECS_D020["ABCDx_bank"])
    assert "bank_x_ust10_chg_xdir" in SPECS_D020["ABCDx_bank"]
