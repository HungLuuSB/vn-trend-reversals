"""Final-run evaluation (D-026) end to end on synthetic years: stop rules first, then the
pre-registered outputs."""

import numpy as np
import pytest

from vnbank.research.survival.final import evaluate as E
from vnbank.research.survival.final import year as Y

from .synth import make

YEARS = [2010, 2011, 2012]
ONLY = {"M", "DIST", "AGE", "ABCx", "ABCDx", "loo-gold_ret", "loo-gpr_level", "boundary:M"}


def _caches(tmp, **kw):
    ds, sessions = make(**kw)
    ds = Y.prepare(ds, prices=None)
    for y in YEARS:
        Y.run_year(ds, sessions, y, tmp, only=ONLY, log=lambda m: None)
    return E.load_caches(tmp, YEARS)


@pytest.fixture(scope="module")
def weak(tmp_path_factory):
    return _caches(tmp_path_factory.mktemp("weak"), base=0.08, slope=0.05)


def test_too_good_signal_stops_before_any_other_output(tmp_path):
    c = _caches(tmp_path, base=0.01, slope=0.6)
    res = E.evaluate(c, YEARS, n_boot=10, log=lambda m: None)
    assert set(res) == {"STOP"} and res["STOP"]["stop"]
    assert "M" in res["STOP"]["too_good_c"]


def test_weak_signal_runs_every_section(weak):
    res = E.evaluate(weak, YEARS, n_boot=10, log=lambda m: None)
    assert "STOP" not in res and not res["stop_checks"]["stop"]
    sh = res["stop_checks"]["shuffled"]
    assert {"shuffled:M", "shuffled:ABCDx"} <= set(sh)
    assert set(sh["shuffled:M"]["per_year_mean"]) == {"2010", "2011", "2012"}
    pooled = res["pooled"]
    assert {"ABCDx-km", "ABCx-M", "ABCDx-M", "ABCDx-ABCx", "M-DIST", "AGE-km"} <= set(
        pooled["paired"]["improves"]
    )
    assert set(pooled["paired_block_sensitivity"]) == {"40", "60"}
    assert "boundary:M-boundary:DIST" not in pooled.get("paired_boundary_censoring", {}).get(
        "improves", {}
    )  # only specs cached under boundary: are compared
    att = pooled["attribution_d018"]["leave_one_out"]
    assert {"loo-gold_ret", "loo-gpr_level"} <= set(att)
    assert all(0 <= v["p_ibs_holm"] <= 1 for v in att.values())
    dm = pooled["diebold_mariano"]["ABCDx-km"]
    assert np.isfinite(dm["dm"]) and 0 <= dm["p"] <= 1
    assert {"banks", "2017-2019"} & set(pooled["slices"]) == {"banks"}  # synthetic years only
    assert set(res["per_year"]) == {"2010", "2011", "2012"}
    m = pooled["metrics"]["M"]
    assert m["uno_c"] > pooled["metrics"]["km"]["uno_c"]  # the planted signal is found
    assert set(res["h2_coefficients"]["2012"]) == set(E.H2_TERMS)


def test_dm_is_zero_for_identical_forecasts(weak):
    dm = E.diebold_mariano(weak["keys"], weak["preds"], "M", "M")
    assert dm["mean_loss_diff"] == 0


def test_strict_mode_refuses_missing_preregistered_specs(weak):
    import pytest as _pt

    with _pt.raises(SystemExit, match="missing"):
        E.evaluate(weak, YEARS, n_boot=5, log=lambda m: None, strict=True)


def test_caches_from_different_runs_are_refused(tmp_path):
    import json

    ds, sessions = make(n_tickers=4)
    ds = Y.prepare(ds, prices=None)
    for y in (2011, 2012):
        Y.run_year(ds, sessions, y, tmp_path, only={"M"}, log=lambda m: None)
        meta = json.loads((tmp_path / str(y) / "meta.json").read_text())
        meta["git_commit"] = f"commit-{y}"
        (tmp_path / str(y) / "meta.json").write_text(json.dumps(meta))
    with pytest.raises(SystemExit, match="git_commit"):
        E.load_caches(tmp_path, [2011, 2012])


def test_later_steps_need_a_passed_evaluation(tmp_path):
    import json

    run = tmp_path / "run"
    run.mkdir()
    with pytest.raises(SystemExit, match="no completed"):
        E.require_passed_evaluation(run)
    (run / "config.json").write_text(
        json.dumps({"cache": str(tmp_path / "c"), "snapshot_id": {"2017": "abc"}})
    )
    (run / "metrics.json").write_text("{}")
    E.require_passed_evaluation(run, cache=tmp_path / "c", snapshot="abc")
    with pytest.raises(SystemExit):
        E.require_passed_evaluation(run, cache=tmp_path / "other")
    (run / "STOP.json").write_text("{}")
    with pytest.raises(SystemExit, match="stop rule"):
        E.require_passed_evaluation(run)
