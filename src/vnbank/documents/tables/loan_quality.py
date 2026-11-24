"""Loan-quality table ("Phân tích chất lượng nợ cho vay") from OCR text of bank statements.

The five State Bank loan groups (1 standard, 2 special mention, 3 substandard, 4 doubtful,
5 loss) with the current and the comparison column, the printed total, and
NPL ratio = (groups 3 + 4 + 5) / total loans. A table is accepted only if the five groups sum
to the printed total (both columns): the sum check is the OCR test (block E, D-023).
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

# group label prefixes after accent stripping and lower-casing (OCR may garble the tail)
GROUPS = [
    ("no du tieu chu", 1),
    ("no can chu y", 2),
    ("no duoi tieu chu", 3),
    ("no nghi ngo", 4),
    ("no co kha nang m", 5),
]
_NUM = re.compile(r"(?<![\d.,])\d{1,3}(?:[.,]\d{3})+(?![\d.,])|(?<![\d.,])\d{1,6}(?![\d.,])")


def fold(s: str) -> str:
    """Lower case, Vietnamese accents removed (đ -> d), whitespace collapsed."""
    s = s.replace("đ", "d").replace("Đ", "D")
    s = "".join(c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn")
    return re.sub(r"\s+", " ", s.lower()).strip()


def numbers(line: str) -> list[int]:
    """Integers written with . or , thousands separators (or plain), in order."""
    return [int(re.sub(r"[.,]", "", m)) for m in _NUM.findall(line)]


@dataclass(frozen=True)
class LoanQuality:
    page: int  # 1-based
    groups: tuple[tuple[int, int], ...]  # (current, comparison) for groups 1..5
    total: tuple[int, int]

    @property
    def npl_ratio(self) -> float:
        return sum(self.groups[i][0] for i in (2, 3, 4)) / self.total[0]

    @property
    def npl_ratio_prior(self) -> float:
        return sum(self.groups[i][1] for i in (2, 3, 4)) / self.total[1]


def _two_large(nums: list[int]) -> tuple[int, int] | None:
    big = [n for n in nums if n >= 1000]
    return (big[-2], big[-1]) if len(big) >= 2 else None


def _group(folded_line: str) -> int | None:
    return next((k for p, k in GROUPS if folded_line.startswith(p) or f" {p}" in folded_line),
                None)  # fmt: skip


def parse_page(text: str, page: int) -> LoanQuality | None:
    """Find a run of the five group lines (each with two amounts) followed by a total line.
    Headings vary by bank and year ("Phân tích chất lượng nợ cho vay", "Phân tích theo nhóm"),
    so the table is located by its rows, not its heading."""
    lines = text.splitlines()
    folded = [fold(x) for x in lines]
    for start, f in enumerate(folded):
        if _group(f) != 1 or not _two_large(numbers(lines[start])):
            continue
        found: dict[int, tuple[int, int]] = {}
        total = None
        for j in range(start, min(start + 12, len(lines))):
            g, pair = _group(folded[j]), _two_large(numbers(lines[j]))
            if g and pair and g not in found:
                found[g] = pair
            elif len(found) == 5 and pair:
                total = pair
                break
        if len(found) == 5 and total:
            groups = tuple(found[k] for k in range(1, 6))
            if all(sum(gr[c] for gr in groups) == total[c] for c in (0, 1)):
                return LoanQuality(page, groups, total)
    return None


def find_loan_quality(pages: list[str]) -> LoanQuality | None:
    """First table in the document whose groups add up to its printed total."""
    for i, text in enumerate(pages, start=1):
        lq = parse_page(text, i)
        if lq:
            return lq
    return None
