"""VNDirect finfo foreign-flow history (foreign-flow robustness of Paper 1; research use only).

    GET https://api-finfo.vndirect.com.vn/v4/foreigns
        ?q=code:<CODE>~tradingDate:gte:<YYYY-MM-DD>~tradingDate:lte:<YYYY-MM-DD>
        &size=<n>&page=<p>&sort=tradingDate:asc

Facts (observed 2026-11-25): public, no key; JSON ``{"data": [...], "currentPage", "size",
"totalElements", "totalPages"}``; one row per code and trading date with ``buyVal``, ``sellVal``,
``netVal`` (VND), ``buyVol``, ``sellVol``, ``netVol`` (shares), ``floor`` and ``type`` (STOCK or
INDEX; ``VNINDEX`` gives HOSE market-level flows). History starts on 2018-08-30.

Every response is stored unchanged in the raw layer by the ingest module before it is parsed.
"""

from __future__ import annotations

import json
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, date, datetime

import httpx
import pandas as pd

URL = "https://api-finfo.vndirect.com.vn/v4/foreigns"
USER_AGENT = "Mozilla/5.0 (X11; Linux x86_64) vn-bank-data-platform/0.1 research"
PAUSE_S = 1.0
PAGE_SIZE = 500
FIELDS = ("buyVal", "sellVal", "netVal", "buyVol", "sellVol", "netVol")
FIRST_DATE = date(2018, 8, 30)


class ForeignFormatError(ValueError):
    """A reply does not look like the payload this parser was written for."""


@dataclass(frozen=True)
class Page:
    code: str
    start: date
    end: date
    page: int
    body: bytes
    fetched_at_utc: datetime
    total_pages: int


def parse(body: bytes) -> tuple[pd.DataFrame, int]:
    """Rows of one reply and the reply's totalPages."""
    try:
        doc = json.loads(body)
        rows, total = doc["data"], int(doc["totalPages"])
    except (ValueError, KeyError, TypeError) as e:
        raise ForeignFormatError("not a VNDirect foreigns reply") from e
    if not isinstance(rows, list):
        raise ForeignFormatError("data is not a list")
    df = pd.DataFrame(rows)
    if len(df):
        missing = {"code", "tradingDate", *FIELDS} - set(df.columns)
        if missing:
            raise ForeignFormatError(f"missing fields {sorted(missing)}")
        df["tradingDate"] = pd.to_datetime(df.tradingDate).dt.date
    return df, total


class VndirectForeignClient:
    def __init__(self, http: httpx.Client | None = None, pause_s: float = PAUSE_S,
                 sleep: Callable[[float], None] = time.sleep):  # fmt: skip
        self.http = http or httpx.Client(headers={"User-Agent": USER_AGENT}, timeout=60.0)
        self.pause_s, self.sleep = pause_s, sleep

    def fetch(self, code: str, start: date, end: date) -> list[Page]:
        """All pages for one code and date range (inclusive), oldest first."""
        pages, p, total = [], 1, 1
        while p <= total:
            fetched = datetime.now(UTC)
            q = f"code:{code}~tradingDate:gte:{start:%Y-%m-%d}~tradingDate:lte:{end:%Y-%m-%d}"
            r = self.http.get(URL, params={"q": q, "size": str(PAGE_SIZE), "page": str(p),
                                           "sort": "tradingDate:asc"})  # fmt: skip
            self.sleep(self.pause_s)
            if r.status_code != 200:
                raise ForeignFormatError(f"{code} {start}..{end} page {p}: HTTP {r.status_code}")
            _, total = parse(r.content)
            pages.append(Page(code, start, end, p, r.content, fetched, total))
            p += 1
        return pages
