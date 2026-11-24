"""CafeF mirror of listed companies' financial-statement PDFs (Paper 1 block E; D-023).

Facts (observed 2026-11-25; docs/blockE-data-feasibility.md):

* ``GET https://cafef.vn/du-lieu/Ajax/PageNew/FileBCTC.ashx?Symbol=<SYM>&Type=1&Year=<yyyy>``
  returns ``{"Data": [...], "Success": true}``; ``Symbol`` must be upper case (lower case gives
  an empty list). Each item: Quarter (1-4; 5 = annual), Time ("Q3/2013", "CN/2013"), Name
  (e.g. "... hợp nhất quý 2 năm 2013 (đã soát xét)"), Link. There is NO publication date.
* Links point to ``cafefnew.mediacdn.vn`` (404); the same path on ``cafef1.mediacdn.vn``
  serves the PDF.

The list replies and every PDF are stored unchanged in the raw layer (CLAUDE.md rule 1).
"""

from __future__ import annotations

import json
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime

import httpx

LIST_URL = "https://cafef.vn/du-lieu/Ajax/PageNew/FileBCTC.ashx"
USER_AGENT = "Mozilla/5.0 (X11; Linux x86_64) vn-bank-data-platform/0.1 research"
PDF_HOST_FROM, PDF_HOST_TO = "cafefnew.mediacdn.vn", "cafef1.mediacdn.vn"
PAUSE_S = 1.0


class FilingsFormatError(ValueError):
    """A reply does not look like the payload this parser was written for."""


@dataclass(frozen=True)
class Filing:
    symbol: str
    year: int
    quarter: int  # 5 = annual
    period: str
    name: str
    link: str  # as listed

    @property
    def pdf_url(self) -> str:
        return self.link.replace(PDF_HOST_FROM, PDF_HOST_TO, 1)

    @property
    def filename(self) -> str:
        return self.link.rsplit("/", 1)[-1]


def parse_list(symbol: str, year: int, body: bytes) -> list[Filing]:
    try:
        doc = json.loads(body)
        rows = doc["Data"]
    except (ValueError, KeyError, TypeError) as e:
        raise FilingsFormatError("not a CafeF filings list") from e
    if doc.get("Success") is not True or not isinstance(rows, list):
        raise FilingsFormatError("CafeF filings request did not succeed")
    try:
        return [Filing(symbol, year, int(r["Quarter"]), str(r["Time"]), str(r["Name"]),
                       str(r["Link"])) for r in rows]  # fmt: skip
    except (KeyError, TypeError, ValueError) as e:
        raise FilingsFormatError("bad filings record") from e


class CafefFilingsClient:
    def __init__(self, http: httpx.Client | None = None, pause_s: float = PAUSE_S,
                 sleep: Callable[[float], None] = time.sleep):  # fmt: skip
        self.http = http or httpx.Client(headers={"User-Agent": USER_AGENT}, timeout=60.0)
        self.pause_s, self.sleep = pause_s, sleep

    def _get(self, url: str, params: dict | None = None) -> tuple[int, bytes, datetime]:
        fetched = datetime.now(UTC)
        r = self.http.get(url, params=params)
        self.sleep(self.pause_s)
        return r.status_code, r.content, fetched

    def list_filings(self, symbol: str, year: int) -> tuple[bytes, list[Filing], datetime]:
        status, body, fetched = self._get(LIST_URL, {"Symbol": symbol.upper(), "Type": "1",
                                                     "Year": str(year)})  # fmt: skip
        if status != 200:
            raise FilingsFormatError(f"list {symbol} {year}: HTTP {status}")
        return body, parse_list(symbol.upper(), year, body), fetched

    def pdf(self, f: Filing) -> tuple[int, bytes, datetime]:
        status, body, fetched = self._get(f.pdf_url)
        if status == 200 and not body.startswith(b"%PDF"):
            status = -2  # not a PDF
        return status, body, fetched
