"""Loan-quality table ("Phân tích chất lượng nợ cho vay") from OCR text of bank statements.

The five State Bank loan groups (1 standard, 2 special mention, 3 substandard, 4 doubtful,
5 loss) with the current and the comparison column, the printed total, and
NPL ratio = (groups 3 + 4 + 5) / (groups 1..5), the SBV-classified loans. A table is accepted
only if the five groups (plus at most MAX_EXTRA unclassified rows such as SHB's Vinashin loans)
sum to the printed total: the sum check is the OCR test (block E, D-023 and its clarifications).
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

# group label keys after accent stripping, lower-casing and removing spaces (OCR glues
# words: "Nợcân chúý", "Nợ nghingd"). Checked in this order (group 3 before group 1).
# The leading "Nợ" is often misread ("Ng", "Ny"), so keys use the distinctive words only.
GROUPS = [
    ("duoitieu", 3),
    ("canchu", 2),
    ("nchuy", 2),  # "Nợ cén chú ÿ"
    ("nghing", 4),
    ("khanang", 5),
    ("dutieu", 1),
    ("tieuchu", 1),  # "Nợ 40 tiêu chuan" (MBB): any other "tiêu chuẩn" row, checked last
]
MAX_EXTRA = 2  # rows printed between group 5 and the total (D-023 clarification)
MAX_ROWS = 30  # look-ahead in lines (OCR often inserts blank lines between table rows)
_NUM = re.compile(r"\d[\d.,]*\d|\d")


def fold(s: str) -> str:
    """Lower case, Vietnamese accents removed (đ -> d), whitespace collapsed."""
    s = s.replace("đ", "d").replace("Đ", "D")
    s = "".join(c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn")
    return re.sub(r"\s+", " ", s.lower()).strip()


def numbers(line: str) -> list[int]:
    """Integers written with . or , thousands separators, in order. Tolerant of OCR that
    drops a separator ("5371348.825.425"): separators are removed, not validated. A misread
    cannot pass silently because every table must sum to its printed total."""
    return [int(re.sub(r"[.,]", "", m)) for m in _NUM.findall(line)]


def sums_to(parts: list[int], total: int) -> bool:
    """Equal up to presentation rounding: banks round each line (e.g. to millions), so the
    printed total can differ from the sum by a few units (D-023 clarification)."""
    return abs(sum(parts) - total) <= max(5, 1e-7 * abs(total))


@dataclass(frozen=True)
class LoanQuality:
    page: int  # 1-based
    groups: tuple[tuple[int, int], ...]  # (current, comparison) for groups 1..5
    total: tuple[int, int | None]  # comparison total None when not legible
    extra: tuple[int, int] = (0, 0)  # unclassified rows inside the total (SHB Vinashin, MBS)

    @property
    def npl_ratio(self) -> float:
        return sum(self.groups[i][0] for i in (2, 3, 4)) / sum(g[0] for g in self.groups)

    @property
    def npl_ratio_prior(self) -> float | None:
        if self.total[1] is None:
            return None
        return sum(self.groups[i][1] for i in (2, 3, 4)) / sum(g[1] for g in self.groups)


def _two_large(nums: list[int]) -> tuple[int, int] | None:  # used by the start-row test
    big = [n for n in nums if n >= 1000]
    return (big[-2], big[-1]) if len(big) >= 2 else None


def _group(folded_line: str) -> int | None:
    compact = re.sub(r"[^a-z0-9]", "", folded_line)
    return next((k for p, k in GROUPS if p in compact), None)


def parse_page(text: str, page: int) -> LoanQuality | None:
    """Find a run of the five group lines (each with two amounts) followed by a total line.
    Headings vary by bank and year ("Phân tích chất lượng nợ cho vay", "Phân tích theo nhóm"),
    so the table is located by its rows, not its heading. Every later line with an amount is
    tried as the total (OCR may garble the first "Tổng" line); the current column must sum
    to it, and the comparison column too whenever its total is legible."""
    lines = text.splitlines()
    folded = [fold(x) for x in lines]
    for start, f in enumerate(folded):
        if _group(f) != 1 or not _two_large(numbers(lines[start])):
            continue
        found: dict[int, tuple[int, int]] = {}
        extras: list[tuple[int, int]] = []
        for j in range(start, min(start + MAX_ROWS, len(lines))):
            if not re.search(r"\w", folded[j]):
                continue  # blank or punctuation-only line
            big = [n for n in numbers(lines[j]) if n >= 1000]
            g = _group(folded[j])
            if len(found) < 5:
                if g and g not in found and len(big) >= 2:
                    found[g] = (big[-2], big[-1])
                continue
            if not big:
                continue
            groups = tuple(found[k] for k in range(1, 6))
            cur = [gr[0] for gr in groups]
            prev = [gr[1] for gr in groups]
            total = (big[-2], big[-1]) if len(big) >= 2 else (big[0], None)
            if sums_to(cur, total[0]) and (total[1] is None or sums_to(prev, total[1])):
                return LoanQuality(page, groups, total)
            if len(big) >= 2 and sums_to(cur, big[-1]):  # only the current total legible
                return LoanQuality(page, groups, (big[-1], None))
            if extras and len(big) >= 2:  # groups + extra rows = total, both columns legible
                ex = (sum(e[0] for e in extras), sum(e[1] for e in extras))
                if sums_to(cur + [ex[0]], big[-2]) and sums_to(prev + [ex[1]], big[-1]):
                    return LoanQuality(page, groups, (big[-2], big[-1]), ex)
            if len(big) >= 2 and len(extras) < MAX_EXTRA:
                extras.append((big[-2], big[-1]))
    return None


def find_loan_quality(pages: list[str]) -> LoanQuality | None:
    """First table in the document whose groups add up to its printed total."""
    for i, text in enumerate(pages, start=1):
        lq = parse_page(text, i)
        if lq:
            return lq
    return None
