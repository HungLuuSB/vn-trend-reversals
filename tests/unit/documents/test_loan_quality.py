"""Loan-quality parser on hand-typed OCR text (values as printed in the statements)."""

import pytest

from vnbank.documents.tables.loan_quality import find_loan_quality, fold, numbers

# ACB consolidated Q3/2015, note on loan quality (million VND), as OCRed (accents garbled)
ACB = """Phân tích chất lượng nợ cho vay
30/9/2015 31/12/2014
Triệu đồng Triệu đồng
Nợ đủ tiêu chuẳn 126.547.560 110.796.873
Nợ cần chú ý 2.499.209 2.993.934
Nợ dưới tiêu chuẳn 300.840 293.035
Nợ nghi ngờ 524.495 444.308
Nợ có khả năng mét vén 1.149.154 1.795.905
131.021.258 116.324.055
"""

# VCB consolidated Q3/2013 (scanned), same note
VCB = """Nợ cho vay được khoanh 113.675 128.096
Phân tích chất lượng nợ cho vay:
30/9/2013 31/12/2012
Triệu VNĐ Triệu VNĐ
(đã kiếm toán)
Nợ đủ tiêu chuẩn 225.073.173 201.798.721
Nợ cần chú ý 18.142.895 33.572.647
Nợ dưới tiêu chuẩn 3.151.974 3.126.126
Nợ nghi ngờ 1.635.665 1.213.720
Nợ có khả năng mét vén 2.683.423 1.451.461
250.687.130 241.162.675
"""


def test_fold_and_numbers():
    assert fold("Nợ có khả năng mất vốn") == "no co kha nang mat von"
    assert numbers("Nợ đủ tiêu chuẩn 126.547.560 110.796.873") == [126547560, 110796873]
    assert numbers("30/9/2015 31/12/2014") == [30, 9, 2015, 31, 12, 2014]


@pytest.mark.parametrize("text,npl,total", [(ACB, (300840 + 524495 + 1149154) / 131021258,
                                              131021258),
                                             (VCB, (3151974 + 1635665 + 2683423) / 250687130,
                                              250687130)])  # fmt: skip
def test_parses_both_statements_and_sum_checks(text, npl, total):
    lq = find_loan_quality(["cover page", text])
    assert lq is not None and lq.page == 2
    assert lq.total[0] == total
    assert lq.npl_ratio == pytest.approx(npl)
    assert round(lq.npl_ratio, 4) in (0.0151, 0.0298)


def test_rejects_a_table_whose_groups_do_not_sum():
    bad = ACB.replace("2.499.209", "2.499.299")  # one misread digit
    assert find_loan_quality([bad]) is None


# ACB consolidated Q1/2013: heading "Phân tích theo nhóm"; provision-rate table earlier
ACB13 = """Nhóm 1 - Nợ đủ tiêu chuẩn 0%
Nhóm 2 — Nợ cần chú ý 5%
Nhóm 5 — Nợ có khả năng mét vén 100%
Phân tích theo nhóm
31/3/2013 31/12/2012
Nợ đủ tiêu chuan 99.773.159 94.822.750
Nợ cần chú ý 4.276.308 5.421.128
Nợ dưới tiêu chuẩn 716.592 747.218
Nợ nghi ngờ 886.502 673.361
Nợ có khả năng mát vén 1.487.109 1.150.391
107.139.670 102.814.848
Phân tích theo kỳ hạn cho vay
"""


def test_table_found_by_its_rows_whatever_the_heading():
    lq = find_loan_quality([ACB13])
    assert lq is not None and lq.total == (107139670, 102814848)
    assert lq.npl_ratio == pytest.approx((716592 + 886502 + 1487109) / 107139670)
