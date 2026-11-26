"""The snapshot freeze refuses partial dbt runs and runs without the look-ahead tests."""

import pytest

from vnbank.research.shared.snapshot import check_dbt_clean

T = "test.vnbank.no_feature_after_decision_time_global_features_daily_.abc"
FULL = {"args": {"which": "build", "select": [], "exclude": [], "selector": None,
                 "resource_types": []},
        "results": [{"unique_id": "model.vnbank.x", "status": "success"},
                    {"unique_id": T, "status": "pass"}]}  # fmt: skip


def test_full_build_with_lookahead_tests_passes():
    check_dbt_clean(FULL)


@pytest.mark.parametrize("change", [
    {"args": {**FULL["args"], "select": ["market_classification_events"]}},
    {"args": {**FULL["args"], "which": "run"}},
    {"results": [FULL["results"][0]]},  # look-ahead tests not run
    {"results": [*FULL["results"][:1], {"unique_id": T, "status": "fail"}]},
])  # fmt: skip
def test_partial_or_failing_runs_are_refused(change):
    with pytest.raises(SystemExit):
        check_dbt_clean({**FULL, **change})


def test_derived_inputs_are_frozen_without_rows_after_the_study_end(tmp_path, monkeypatch):
    import datetime as dt

    import pandas as pd

    from vnbank.research.shared import snapshot as S

    src = tmp_path / "src"
    src.mkdir()
    pd.DataFrame({"day": pd.to_datetime(["2026-11-19", "2026-11-20", "2026-11-23"]),
                  "v": [1, 2, 3]}).to_parquet(src / "a.parquet")  # fmt: skip
    pd.DataFrame({"v": [1]}).to_parquet(src / "b.parquet")
    monkeypatch.setattr(S, "DERIVED", {"paper2/a.parquet": (src / "a.parquet", "day"),
                                       "b.parquet": (src / "b.parquet", None)})  # fmt: skip
    out = tmp_path / "snap"
    files, kept, dropped = S.freeze_derived(out, dt.date(2026, 11, 20))
    assert kept == {"paper2/a.parquet": 2, "b.parquet": 1} and dropped["paper2/a.parquet"] == 1
    assert pd.read_parquet(out / "paper2/a.parquet").v.tolist() == [1, 2]
    assert set(files) == {"paper2/a.parquet", "b.parquet"}


def test_frozen_input_prefers_the_snapshot(tmp_path, monkeypatch):
    from vnbank.common import paths

    monkeypatch.setattr(paths, "SNAPSHOTS", tmp_path / "snapshots")
    work = paths.REPO / "data" / "extracted"
    assert paths.frozen_input("abc", "x.parquet", work)[1].startswith("working:")
    (tmp_path / "snapshots" / "abc").mkdir(parents=True)
    (tmp_path / "snapshots" / "abc" / "x.parquet").write_bytes(b"")
    p, src = paths.frozen_input("abc", "x.parquet", work)
    assert src == "snapshot:abc" and p == tmp_path / "snapshots" / "abc" / "x.parquet"
