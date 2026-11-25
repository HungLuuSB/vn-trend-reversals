"""Loan-quality parser on hand-typed OCR text (values as printed in the statements)."""

import pytest

from vnbank.documents.tables.loan_quality import find_loan_quality, fold, numbers, sums_to

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
    assert numbers("mét vốn _ 5371348.825.425 4.209.282.272.418") == [5371348825425,
                                                                     4209282272418]  # fmt: skip


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


# BID consolidated Q3/2014 (amounts in VND): glued label, a dropped separator, ODA line after
BID14Q3 = """- Phân tích chất lượng nợ cho vay:
30/09/2014 31/12/2013
Nợ đủ tiêu chuẩn 375.496.067.210.512 339.091.600.001.015
Nợ cần chú ý 20.240.652.118.633 25.338.340.895.149
Nợ dưới tiéu chuẩn 1.827.571.385.861 3.946.369.850.190
Nợ nghingd 763.489.954.847 683.714.986.250
Nợ có khả năng mét vốn _ 5371348.825.425 4.209.282.272.418
Tổng _403.699.129.495.278 373.269.308.005.022
Cho vay bằng vốn ODA _ 8734450.894909 _ 17.765.742.774835_
"""

# CTG consolidated Q3/2012: blank lines between rows, "Nợcân chúý"
CTG12Q3 = """3.1.  Phdn tích chất lượng nợ cho vay

Nợ du tiêu chudn 289.166.683 285.213.117

Nợcân chúý -. 3.937.823 6.017.024

Nợ dưới tiêu chuân 1.734.152 1.071.421

Nợ nghi ngờ 3.528.678 220.213

Nợ có kha năng mất vốn 2.603.163 912.537

300.970.499 293.434.312
"""


@pytest.mark.parametrize("text,total", [(BID14Q3, 403699129495278), (CTG12Q3, 300970499)])
def test_ocr_damage_is_tolerated_but_still_sum_checked(text, total):
    lq = find_loan_quality([text])
    assert lq is not None and lq.total[0] == total
    # one misread significant digit in each table (beyond the 1e-7 rounding tolerance)
    broken = text.replace("1.827.571.385.861", "1.828.571.385.861")
    broken = broken.replace("1.734.152", "1.784.152")
    assert find_loan_quality([broken]) is None


# BID Q1/2016: "Ng"/"Ny" for "Nợ", a split prior total on the first Tổng line, a clean second one
BID16Q1 = """- Phân tich chất lượng nợ cho vay
: — 31/03/2016.-Á _ 31/12/2015
Ng đủ tiêu chuẩn 593,740,320 570,845,421
s Nợ cẳn chú ý 18,747,770 17,535,374
Ny dưới tiêu chuẩn 3,830,457 3,975,637
Nợ nghỉ ngờ 1,765,997 887,764
Nợ có khả năng mắt vén 5,655.972 5,190279
Tổng 623,740,516 598,434 475
Cho vay bằng vén ODA - -
Tổng 623,740,516 598,434,475
"""

# CTG Q1/2012: only the current total legible; CTG Q3/2013: printed total off by rounding (1)
CTG12Q1 = """| No đủ tiêu chuẩn 272.701.173 285.213.117
‘ _ Nợ cần chú ý 7.901.072 6.017.024
| Nợ đưới tiêu chuẩn 3.358.458 1.071.421
Nợ nghi ngờ 914.644 220.213
" Nợ có khả năng mét vốn 1.004.956 912.537
285.880.303 EM
"""
CTG13Q3 = """Nợ đủ tiêu chuẩn 335.351.656 327.054.358 !
| Nợcầnchúý - 1.685.321 1.411.738
Nợ dưới tiêu chuân 1.535.747 994.983 j
Nợ nghi ngờ 1.551.689 1.789.074 j
Nợ có khả năng mất vén 5.431.258 2.105.939
I 345.555.670 333.356.092
"""


@pytest.mark.parametrize("text,total", [(BID16Q1, (623740516, 598434475)),
                                        (CTG12Q1, (285880303, None)),
                                        (CTG13Q3, (345555670, 333356092))])  # fmt: skip
def test_misread_labels_partial_totals_and_rounding(text, total):
    lq = find_loan_quality([text])
    assert lq is not None and lq.total == total


def test_rounding_tolerance_is_tight():
    assert sums_to([100, 200], 302) and not sums_to([100, 200], 310)
    big = 400_000_000  # million-VND table: tolerance 40 units
    assert sums_to([big], big + 40) and not sums_to([big], big + 41)
