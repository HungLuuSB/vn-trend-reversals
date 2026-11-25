"""Visual-transcription tier (D-023): every seed row must pass the exact two-column check."""

import csv

import pytest

from vnbank.common import paths
from vnbank.documents.tables.visual import SEED_COLUMNS, candidate_pages, check_row

SEED = paths.SEEDS / "loan_quality_transcribed.csv"

ROW = {"g1": "95663399", "g1_prior": "101564431", "g2": "4567430", "g2_prior": "326758",
       "g3": "747218", "g3_prior": "274973", "g4": "673361", "g4_prior": "345655",
       "g5": "1150391", "g5_prior": "297339", "extra": "", "extra_prior": "",
       "total": "102801799", "total_prior": "102809156"}  # fmt: skip


def test_check_row_is_exact_in_both_columns():
    assert check_row(ROW)
    assert not check_row({**ROW, "total": "102801800"})  # off by one unit: rejected
    assert not check_row({**ROW, "g2_prior": "326759"})
    assert check_row({**ROW, "extra": "10", "extra_prior": "0", "total": "102801809"})


def test_candidate_pages_rank_table_pages_first():
    table = "Nợ đủ tiêu chuẩn 95.663.399 101.564.431\nNợ cần chú ý 4.567.430 326.758\n"
    policy = "Nhóm 1: Nợ đủ tiêu chuẩn\n"  # cue words but no amounts
    assert candidate_pages(["cover", policy, table]) == [3]


@pytest.mark.skipif(not SEED.exists(), reason="no transcriptions yet")
def test_every_seed_row_sums_exactly_and_is_sourced():
    rows = list(csv.DictReader(open(SEED, encoding="utf-8")))
    assert rows and list(rows[0].keys()) == SEED_COLUMNS
    for r in rows:
        assert r["raw_key"].startswith("cafef_filings/") and int(r["page"]) >= 1, r
        assert r["method"] == "visual", r
        assert check_row(r), f"{r['raw_key']} does not sum exactly"
