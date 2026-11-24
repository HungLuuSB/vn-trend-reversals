import numpy as np

from vnbank.research.survival.dev_attribution import FULL, boot_p, drop, holm, variants
from vnbank.research.survival.features.assemble import FEATURES_D


def test_holm_matches_hand_computation():
    # p sorted: 0.01*3=0.03, 0.02*2=0.04, 0.04*1=0.04 (monotone)
    assert np.allclose(holm(np.array([0.04, 0.01, 0.02])), [0.04, 0.03, 0.04])
    assert holm(np.array([0.5, 0.9])).max() <= 1.0


def test_variants_drop_feature_and_its_interaction_only():
    v = variants()
    assert len(v) == 1 + len(FEATURES_D) + 1
    full = set(v[FULL])
    gone = full - set(v["-gold_ret"])
    assert gone == {"gold_ret", "gold_ret_xdir"}
    assert full - set(v["-gold-gpr"]) == {"gold_ret", "gold_ret_xdir", "gpr_level",
                                         "gpr_level_xdir", "gpr_chg", "gpr_chg_xdir"}  # fmt: skip
    assert drop(["a", "a_xdir", "b"], ["a"]) == ["b"]


def test_bootstrap_p_value():
    assert boot_p(np.array([1.0, 2.0, 3.0, 4.0])) == 0.0
    assert boot_p(np.array([-1.0, 1.0])) == 1.0


def test_attribution_runs_end_to_end(tmp_path, monkeypatch):
    import json

    import pandas as pd

    import vnbank.research.survival.dev_attribution as da
    from vnbank.research.survival.features.assemble import BLOCKS

    sessions = pd.bdate_range("2012-01-02", "2016-12-30")
    rng = np.random.default_rng(1)
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
    prev = tmp_path / "d017"
    prev.mkdir()
    chosen = {str(y): {"chosen": {FULL: {"C": 0.1, "l1_ratio": 0.0}}} for y in (2014, 2015, 2016)}
    (prev / "metrics.json").write_text(json.dumps({"results": chosen}))
    monkeypatch.setattr(da, "REPO", tmp_path)
    monkeypatch.setattr(da, "RUNS", tmp_path / "research" / "paper1" / "runs")
    monkeypatch.setattr(da, "code_version", lambda: "test")
    monkeypatch.setattr(da, "C_RESAMPLES", 3)
    assert da.main(["--features-run", str(fr), "--from-run", str(prev), "--bootstrap", "5"]) == 0
    out = json.loads(
        next((tmp_path / "research" / "paper1" / "runs").glob("*/metrics.json")).read_text()
    )
    assert len(out["leave_one_out"]) == len(FEATURES_D)
    assert set(out["gold_vs_gpr"]) == {"gold_given_gpr_ibs", "gpr_given_no_gold_ibs",
                                      "gold_given_gpr_c", "gpr_given_no_gold_c"}  # fmt: skip
