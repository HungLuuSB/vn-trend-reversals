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

# group label keys after accent stripping, lower-casing and removing spaces (OCR glues
# words: "Nợcân chúý", "Nợ nghingd"). Checked in this order (group 3 before group 1).
# The leading "Nợ" is often misread ("Ng", "Ny"), so keys use the distinctive words only.
GROUPS = [
    ("duoitieu", 3),
    ("canchu", 2),
    ("nghing", 4),
    ("khanang", 5),
    ("dutieu", 1),
]
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

    @property
    def npl_ratio(self) -> float:
        return sum(self.groups[i][0] for i in (2, 3, 4)) / self.total[0]

    @property
    def npl_ratio_prior(self) -> float | None:
        if self.total[1] is None:
            return None
        return sum(self.groups[i][1] for i in (2, 3, 4)) / self.total[1]


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

    def _next_group(i: int) -> int | None:
        for k in range(i + 1, min(i + 4, len(lines))):
            if re.search(r"\w", folded[k]):
                return _group(folded[k])
        return None

    for start, f in enumerate(folded):
        if not _two_large(numbers(lines[start])):
            continue
        g0 = _group(f)
        unreadable_first = g0 is None and re.search(r"[a-z]", f) and _next_group(start) == 2
        if g0 != 1 and not unreadable_first:
            continue
        found: dict[int, tuple[int, int]] = {}
        for j in range(start, min(start + MAX_ROWS, len(lines))):
            if not re.search(r"\w", folded[j]):
                continue  # blank or punctuation-only line
            big = [n for n in numbers(lines[j]) if n >= 1000]
            g = _group(folded[j])
            if len(found) < 5:
                if len(big) >= 2:
                    compact = re.sub(r"[^a-z]", "", folded[j])
                    nxt = len(found) + 1
                    if g is None and compact and not compact.startswith(("tong", "cong")):
                        g = nxt  # unreadable label: SBV tables always list groups 1-5 in order
                    if g == nxt:
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
    return None


def find_loan_quality(pages: list[str]) -> LoanQuality | None:
    """First table in the document whose groups add up to its printed total."""
    for i, text in enumerate(pages, start=1):
        lq = parse_page(text, i)
        if lq:
            return lq
    for i in range(1, len(pages)):  # then tables that run over a page break
        lq = parse_page(pages[i - 1] + "\n" + pages[i], i)
        if lq:
            return lq
    return None
