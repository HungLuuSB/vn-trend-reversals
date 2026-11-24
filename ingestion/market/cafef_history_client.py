"""Client for CafeF's per-ticker price history (fills gaps in the bulk archive; ADR 0002).

CafeF's bulk end-of-day archive keeps only a stock's history on its current exchange: history
from before an exchange move (e.g. ACB on HNX 2006-2020) is missing. The per-ticker history
endpoint behind cafef.vn/du-lieu/lich-su-giao-dich-<ticker>-1.chn still has it, and also gives
matched trade value, from which a daily VWAP can be computed.

Endpoint facts (observed 2026-11-24):

* ``StartDate`` / ``EndDate`` are US-style ``MM/DD/YYYY``; at most 30 rows per page.
* Prices are in thousand VND; ``GiaTriKhopLenh`` (matched value) is in billion VND, rounded to
  2 decimals, so a VWAP from it is uncertain by up to 0.005e9 / volume VND per share.
* Each response also carries the current VN-Index snapshot, so identical requests on different
  days return different bytes.

All pages of one (ticker, date range) request are stored together, byte for byte, as one zip in
the raw layer before anything is parsed (CLAUDE.md rule 1).
"""

from __future__ import annotations

import io
import json
import time
import zipfile
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, date, datetime

import httpx
import pandas as pd

URL = "https://cafef.vn/du-lieu/Ajax/PageNew/DataHistory/PriceHistory.ashx"
USER_AGENT = "Mozilla/5.0 (X11; Linux x86_64) vn-bank-data-platform/0.1 research"
PAGE_SIZE = 30  # the endpoint never returns more
ZIP_TIME = (2000, 1, 1, 0, 0, 0)  # fixed member timestamps: same pages -> same zip bytes

COLUMNS = [
    "ticker",
    "trade_date",
    "open",
    "high",
    "low",
    "close",
    "adj_close",
    "volume",
    "value_bn",
    "pt_volume",
    "pt_value_bn",
    "page",
    "row_in_page",
]


class CafefHistoryFormatError(ValueError):
    """A page does not look like the payload this parser was written for."""


@dataclass(frozen=True)
class HistoryBundle:
    ticker: str
    start: date
    end: date
    pages: list[bytes] = field(repr=False)
    urls: list[str]
    total_count: int
    fetched_at_utc: datetime
    exchange_type: str = ""  # "" = endpoint default; else HOSE, HNX or UPCOM

    @property
    def filename(self) -> str:
        return bundle_stem(self.ticker, self.exchange_type, self.start, self.end) + "zip"

    def to_zip(self) -> bytes:
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            for i, body in enumerate(self.pages, start=1):
                info = zipfile.ZipInfo(f"p{i:04d}.json", date_time=ZIP_TIME)
                info.compress_type = zipfile.ZIP_DEFLATED
                zf.writestr(info, body)
        return buf.getvalue()


def bundle_stem(ticker: str, exchange_type: str, start: date, end: date) -> str:
    """File-name stem (ends with '.'); the default exchange keeps the original naming."""
    ex = f"{exchange_type}_" if exchange_type else ""
    return f"{ticker}_{ex}{start:%Y%m%d}_{end:%Y%m%d}."


def _us(d: date) -> str:
    return d.strftime("%m/%d/%Y")


def _payload(body: bytes) -> dict:
    try:
        doc = json.loads(body)
        data = doc["Data"]
        int(data["TotalCount"])
        rows = data["Data"]
    except (ValueError, KeyError, TypeError) as e:
        raise CafefHistoryFormatError("not a CafeF price-history payload") from e
    if doc.get("Success") is not True or not isinstance(rows, list | type(None)):
        raise CafefHistoryFormatError("CafeF price-history request did not succeed")
    return data


class CafefHistoryClient:
    def __init__(
        self,
        http: httpx.Client | None = None,
        *,
        retries: int = 3,
        backoff_seconds: float = 5.0,
        min_interval_seconds: float = 1.0,
        max_pages: int = 200,
        sleep: Callable[[float], None] = time.sleep,
        now: Callable[[], datetime] = lambda: datetime.now(UTC),
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        self._http = http or httpx.Client(
            timeout=httpx.Timeout(30.0), headers={"User-Agent": USER_AGENT}, follow_redirects=True
        )
        self._retries = retries
        self._backoff = backoff_seconds
        self._interval = min_interval_seconds
        self._max_pages = max_pages
        self._sleep = sleep
        self._now = now
        self._monotonic = monotonic
        self._last: float | None = None

    def _get(self, params: dict) -> httpx.Response:
        for attempt in range(self._retries + 1):
            if self._last is not None:
                wait = self._interval - (self._monotonic() - self._last)
                if wait > 0:
                    self._sleep(wait)
            self._last = self._monotonic()
            try:
                resp = self._http.get(URL, params=params)
            except httpx.TransportError:
                if attempt == self._retries:
                    raise
            else:
                if resp.status_code < 500 and resp.status_code != 429:
                    resp.raise_for_status()
                    return resp
                if attempt == self._retries:
                    resp.raise_for_status()
            self._sleep(self._backoff * 2**attempt)
        raise AssertionError("unreachable")

    def fetch_range(
        self, ticker: str, start: date, end: date, exchange_type: str = ""
    ) -> HistoryBundle:
        """All pages for ticker between start and end (inclusive).

        exchange_type selects CafeF's exchange filter (HOSE, HNX, UPCOM). Which one returns a
        stock's history varies: ACB's HNX years come back under the default (its current
        exchange), BVB's UPCoM years only with UPCOM.
        """
        pages, urls, total = [], [], None
        for page in range(1, self._max_pages + 1):
            params = {
                "Symbol": ticker,
                "StartDate": _us(start),
                "EndDate": _us(end),
                "PageIndex": page,
                "PageSize": PAGE_SIZE,
            }
            if exchange_type:
                params["ExchangeType"] = exchange_type
            resp = self._get(params)
            data = _payload(resp.content)
            count = int(data["TotalCount"])
            if total is None:
                total = count
            elif count != total:
                raise CafefHistoryFormatError(f"{ticker}: TotalCount changed while paging")
            pages.append(resp.content)
            urls.append(str(resp.url))
            if page * PAGE_SIZE >= total:
                break
        else:
            raise CafefHistoryFormatError(f"{ticker}: more than {self._max_pages} pages")
        return HistoryBundle(
            ticker, start, end, pages, urls, total or 0, self._now(), exchange_type
        )


def parse_bundle(content: bytes) -> pd.DataFrame:
    """Rows of a stored bundle zip; one row per (ticker, trade_date), as published."""
    frames = []
    with zipfile.ZipFile(io.BytesIO(content)) as zf:
        names = sorted(n for n in zf.namelist() if n.endswith(".json"))
        for name in names:
            data = _payload(zf.read(name))
            rows = data["Data"] or []
            if not rows:
                continue
            df = pd.DataFrame(rows)
            missing = {"Symbol", "Ngay", "GiaMoCua", "GiaCaoNhat", "GiaThapNhat", "GiaDongCua",
                       "GiaDieuChinh", "KhoiLuongKhopLenh", "GiaTriKhopLenh", "KLThoaThuan",
                       "GtThoaThuan"} - set(df.columns)  # fmt: skip
            if missing:
                raise CafefHistoryFormatError(f"{name}: missing fields {sorted(missing)}")
            frames.append(
                pd.DataFrame(
                    {
                        "ticker": df["Symbol"].astype(str).str.strip(),
                        "trade_date": pd.to_datetime(df["Ngay"], format="%d/%m/%Y"),
                        "open": df["GiaMoCua"].astype("float64"),
                        "high": df["GiaCaoNhat"].astype("float64"),
                        "low": df["GiaThapNhat"].astype("float64"),
                        "close": df["GiaDongCua"].astype("float64"),
                        "adj_close": df["GiaDieuChinh"].astype("float64"),
                        "volume": df["KhoiLuongKhopLenh"].astype("int64"),
                        "value_bn": df["GiaTriKhopLenh"].astype("float64"),
                        "pt_volume": df["KLThoaThuan"].astype("int64"),
                        "pt_value_bn": df["GtThoaThuan"].astype("float64"),
                        "page": name,
                        "row_in_page": range(1, len(df) + 1),
                    }
                )
            )
    if not frames:
        return pd.DataFrame(columns=COLUMNS)
    return pd.concat(frames, ignore_index=True)[COLUMNS]
