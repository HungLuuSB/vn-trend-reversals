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


# SHB Q1/2014 (VND): Vinashin loans awaiting resolution printed between group 5 and the total
SHB14Q1 = """y 20.1. Phân tích chất lượng nợ cho vay
31/03/2014 31/12/2013
No đủ tiêu chuẩn 74,685,918,917,330 69,824,849,892,000
Nợ cần chú y 2,883,173,705,586 2,352,445,687,051
No dưới tiêu chuẩn 307,792,975,786 144,391,408,890
Nợ nghi ngờ 212,597,167,859 434,849,602,395
Nợ có khả năng mắt vốn 2,986,117,034,519 2,524,550,316,059
Các khoản nợ chờ xử ly - Vinashin 1,228,584,079,407 1,228,584,079,407
82,304,183,880,487 76,509,670,985,802
20.2. Phân tich dư nợ theo thời gian
"""

# MBB Q1/2015: "đủ" read as "40"; MBS repo row inside the total (as printed, then as OCRed)
MBB15Q1 = """- Phén tich chét lượng nợ cho vay:
Nợ 40 tiêu chuan 93.742.850 94.348.653
Nợ cén chú ÿ 2.634.129 2.367.403
Nợ dưới tiêu chuắn 729.534 594.447
Nợ nghi ngờ 492.176 902.868
Nợ có khả năng mắt vén 1.396.070 1.364.495
Các hợp đồng REPO, hỗ trợ tai chinh và ứng
trước cho khách hàng của MBS — 1.025.361 991.140
100.020.120 100.569.006
"""


def test_extra_rows_inside_the_total():
    lq = find_loan_quality([SHB14Q1])
    assert lq is not None and lq.extra == (1228584079407, 1228584079407)
    assert lq.total == (82304183880487, 76509670985802)
    npl = (307792975786 + 212597167859 + 2986117034519) / (82304183880487 - 1228584079407)
    assert lq.npl_ratio == pytest.approx(npl, rel=1e-12)  # denominator: classified loans
    mbb = find_loan_quality([MBB15Q1])
    assert mbb is not None and mbb.groups[0] == (93742850, 94348653)
    assert mbb.extra == (1025361, 991140)


def test_extra_rows_still_sum_checked():
    assert find_loan_quality([MBB15Q1.replace("1.025.361", "1026381")]) is None  # as OCRed
    # an extra row is accepted only when both columns of the total are legible
    assert find_loan_quality([SHB14Q1.replace(" 76,509,670,985,802", "")]) is None


def test_unreadable_label_takes_the_next_group_in_order_and_page_breaks_join():
    vcb = """Phân tích chất lượng nợ cho vay:
31/3/2015 31/12/2014
Nợ dg tiéu chuân 305.766.039 298.526.817
Nợcân chúý -. 16.184.890 17.346.539
No dưới tiéu chuan 2.612.538 2.135.698
Nợ nghi ngờ ; 1.448.719 1.770.773
Nợ có khả năng mất vốn 4.769.707 3.552.210
330.781.893 323.332.037
"""
    first = vcb.replace("Nợ dg tiéu chuân", "Nợ đủ tiêu chuẩn")
    assert find_loan_quality([first]) is not None  # baseline
    assert find_loan_quality([vcb]).total == (330781893, 323332037)
    split = first.split("Nợ nghi ngờ")
    lq = find_loan_quality([split[0] + "Trang 14", "Nợ nghi ngờ" + split[1]])
    assert lq is not None and lq.page == 1


def test_percentage_columns_are_not_amounts():
    """TCB prints a share next to each amount (D-023 clarification 6)."""
    from vnbank.documents.tables.loan_quality import numbers, parse_page

    assert numbers("Nợ đủ tiêu chuan 711.706.750 98,34 594.272.007 98,10") == [711706750, 594272007]
    assert numbers("Nợ cần chú ý 3.852.272 0,53 4.440.911 0,73") == [3852272, 4440911]
    text = """9.1 Phân tich chất lượng nợ cho vay
31/12/2025 31/12/2024
triệu dong % triệu dong %
Nợ đủ tiêu chuan 711.706.750 98,34 594.272.007 98,10
Nợ cần chú ý 3.852.272 0,53 4.440.911 0,73
Nợ dưới tiêu chuan 918.063 0,13 1.365.655 0,22
Nợ nghi ngờ 1.339.119 0,18 2.465.618 0,41
Nợ có khả năng mắt vén 5.941.193 0,82 3.269.527 0,54
723.757.397 100,00 605.813.718 100,00"""
    lq = parse_page(text, 45)
    assert lq is not None and lq.total == (723757397, 605813718)
    assert lq.groups[0] == (711706750, 594272007)
    assert abs(lq.npl_ratio - (918063 + 1339119 + 5941193) / 723757397) < 1e-12
