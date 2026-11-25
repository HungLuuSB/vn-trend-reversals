"""Paper-number generator (vnbank.research.shared.report): formatting, names, provenance."""

import json

import pandas as pd
import pytest

from vnbank.research.shared import report as R


def test_macro_names_are_letters_only():
    assert R.macro("p2", "h1", "beta5", "bar") == "PTwoHOneBetaFiveBar"
    assert R.macro("ptwo", "rows", "bmr") == "PtwoRowsBmr"
    with pytest.raises(R.ReportError):
        R.macro("p2", "_")


def test_number_formatting():
    assert R.num(-0.0098648) == r"\ensuremath{-0.010}"
    assert R.num(0.0537, 2) == r"\ensuremath{0.05}"
    assert R.num(-0.0004) == r"\ensuremath{0.000}"  # never -0.000
    assert R.num(0.12, signed=True) == r"\ensuremath{+0.120}"
    assert R.num(float("nan")) == r"\textemdash{}" and R.num(None) == r"\textemdash{}"
    assert R.interval(-0.0734, 0.0537) == r"\ensuremath{[-0.073, 0.054]}"
    assert R.integer(3569) == r"\ensuremath{3\,569}" and R.integer(44) == r"\ensuremath{44}"


def test_numbers_file_records_sources_and_rejects_duplicates(tmp_path, monkeypatch):
    run_dir = tmp_path / "runs" / "20260101T000000Z-x"
    run_dir.mkdir(parents=True)
    (run_dir / "config.json").write_text(json.dumps({"git_commit": "abc123def4567"}))
    monkeypatch.setattr(R.paths, "runs_dir", lambda paper: tmp_path / "runs")
    run = R.Run.load(2, "20260101T000000Z-x")
    n = R.Numbers(2)
    n.add("PtwoX", R.num(1.5), run, "metrics.x")
    with pytest.raises(R.ReportError):
        n.add("PtwoX", R.num(2.0), run, "metrics.y")
    text = n.write(tmp_path / "gen", "test", "fff").read_text()
    assert r"\newcommand{\PtwoX}{\ensuremath{1.500}} % 20260101T000000Z-x: metrics.x" in text
    assert "20260101T000000Z-x (commit abc123def456)" in text and "GENERATED FILE" in text


def test_dirty_or_missing_runs_are_refused(tmp_path, monkeypatch):
    monkeypatch.setattr(R.paths, "runs_dir", lambda paper: tmp_path)
    with pytest.raises(R.ReportError, match="not found"):
        R.Run.load(2, "nope")
    (tmp_path / "d").mkdir()
    (tmp_path / "d" / "config.json").write_text(json.dumps({"git_commit": "abc+dirty"}))
    with pytest.raises(R.ReportError, match="uncommitted"):
        R.Run.load(2, "d")
    assert R.Run.load(2, "d", allow_dirty=True).name == "d"


def test_tabular_escapes_text_but_keeps_latex_cells(tmp_path):
    df = pd.DataFrame([["Bar & ring_x", R.num(-0.01)], ["50%", R.integer(1200)]])
    body = R.tabular(df, "lr", header=["Name", "Value"])
    assert r"Bar \& ring\_x & \ensuremath{-0.010} \\" in body
    assert r"50\% & \ensuremath{1\,200} \\" in body
    assert body.startswith(r"\begin{tabular}{lr}") and r"\bottomrule" in body
    with pytest.raises(R.ReportError):
        R.tabular(df, "l")
    with pytest.raises(R.ReportError):
        R.write_table(tmp_path, "Bad-Name", body, "x")
