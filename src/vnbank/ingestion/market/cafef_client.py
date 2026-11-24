"""Client for CafeF's end-of-day bulk archives (ADR 0002).

CafeF (VCCorp) publishes, after each trading day, two zip archives holding the full daily history
of every ticker on HOSE (``HSX``), HNX and UPCoM:

* ``CafeF.SolieuGD.Raw.UptoDDMMYYYY.zip``: raw (unadjusted) prices. The research uses this one
  and computes adjustments itself (CLAUDE.md rule 7).
* ``CafeF.SolieuGD.UptoDDMMYYYY.zip``: prices adjusted by CafeF. Kept for cross-checks and to
  infer adjustment dates; never used directly as model input.

Each archive holds three CSVs (one per exchange) with the header
``<Ticker>,<DTYYYYMMDD>,<Open>,<High>,<Low>,<Close>,<Volume>``. Prices are in thousands of VND.
Covered warrants, ETFs and some index-like rows appear alongside ordinary shares.

Downloading and parsing are separate on purpose: callers store the downloaded bytes in the raw
layer first (``vnbank.ingestion.market.cafef_ingest``), then parse what was stored.
"""

from __future__ import annotations

import io
import re
import time
import zipfile
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from enum import StrEnum
from zoneinfo import ZoneInfo

import httpx
import pandas as pd

BASE_URL = "https://cafef1.mediacdn.vn/data/ami_data"
VN_TZ = ZoneInfo("Asia/Ho_Chi_Minh")
USER_AGENT = "vn-bank-data-platform/0.1 (research data pipeline)"

EXPECTED_HEADER = ["<Ticker>", "<DTYYYYMMDD>", "<Open>", "<High>", "<Low>", "<Close>", "<Volume>"]
EXCHANGES = ("HSX", "HNX", "UPCOM")
_MEMBER_RE = re.compile(
    r"^CafeF\.(?P<raw>RAW_)?(?P<exchange>HSX|HNX|UPCOM)\.Upto(?P<d>\d{2}\.\d{2}\.\d{4})\.csv$"
)


class Variant(StrEnum):
    RAW = "raw"
    ADJUSTED = "adjusted"


class CafefFormatError(ValueError):
    """The archive does not look like the format this parser was written for."""


@dataclass(frozen=True)
class CafefArchive:
    as_of: date  # last trading date covered ("Upto" date in the file name)
    variant: Variant
    url: str
    filename: str
    content: bytes
    fetched_at_utc: datetime
    last_modified: str | None  # HTTP Last-Modified header, as sent


def archive_filename(as_of: date, variant: Variant) -> str:
    stamp = as_of.strftime("%d%m%Y")
    prefix = "CafeF.SolieuGD.Raw" if variant is Variant.RAW else "CafeF.SolieuGD"
    return f"{prefix}.Upto{stamp}.zip"


def archive_url(as_of: date, variant: Variant) -> str:
    return f"{BASE_URL}/{as_of.strftime('%Y%m%d')}/{archive_filename(as_of, variant)}"


class CafefClient:
    """Downloads CafeF archives with timeouts and retries; holds only the HTTP client."""

    def __init__(
        self,
        http: httpx.Client | None = None,
        *,
        retries: int = 3,
        backoff_seconds: float = 2.0,
        sleep: Callable[[float], None] = time.sleep,
        now: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self._http = http or httpx.Client(
            timeout=httpx.Timeout(30.0, read=300.0),
            headers={"User-Agent": USER_AGENT},
            follow_redirects=True,
        )
        self._retries = retries
        self._backoff = backoff_seconds
        self._sleep = sleep
        self._now = now

    def fetch(self, as_of: date, variant: Variant) -> CafefArchive | None:
        """Download the archive for ``as_of``; ``None`` if CafeF has none for that date (404)."""
        url = archive_url(as_of, variant)
        for attempt in range(self._retries + 1):
            try:
                resp = self._http.get(url)
            except httpx.TransportError:
                if attempt == self._retries:
                    raise
            else:
                if resp.status_code == 404:
                    return None
                if resp.status_code < 500 and resp.status_code != 429:
                    resp.raise_for_status()
                    _check_zip(resp.content, url)
                    return CafefArchive(
                        as_of=as_of,
                        variant=variant,
                        url=url,
                        filename=archive_filename(as_of, variant),
                        content=resp.content,
                        fetched_at_utc=self._now(),
                        last_modified=resp.headers.get("last-modified"),
                    )
                if attempt == self._retries:
                    resp.raise_for_status()
            self._sleep(self._backoff * 2**attempt)
        raise AssertionError("unreachable")

    def fetch_latest(
        self, variant: Variant, *, on_or_before: date | None = None, max_lookback_days: int = 10
    ) -> CafefArchive:
        """Newest archive dated on or before ``on_or_before`` (default: today in Vietnam)."""
        start = on_or_before or self._now().astimezone(VN_TZ).date()
        for back in range(max_lookback_days + 1):
            archive = self.fetch(start - timedelta(days=back), variant)
            if archive is not None:
                return archive
        raise LookupError(
            f"no CafeF {variant} archive in the {max_lookback_days} days up to {start}"
        )


def _check_zip(content: bytes, url: str) -> None:
    if not zipfile.is_zipfile(io.BytesIO(content)):
        raise CafefFormatError(f"response from {url} is not a zip archive")


def parse_archive(content: bytes) -> pd.DataFrame:
    """Parse a CafeF archive into one row per (exchange, ticker, trade_date).

    Columns: ``exchange`` (HSX/HNX/UPCOM), ``ticker``, ``trade_date`` (datetime64, no time zone:
    a Vietnamese trading date), ``open``/``high``/``low``/``close`` (float, thousand VND),
    ``volume`` (int64), ``variant`` (raw/adjusted), ``upto`` (the archive's "Upto" date),
    ``source_file`` and ``row_num`` (1-based data line within ``source_file``, for lineage).
    Values are passed through as published; cleaning happens downstream.
    """
    frames = []
    with zipfile.ZipFile(io.BytesIO(content)) as zf:
        members = [m for m in zf.infolist() if not m.is_dir()]
        variants = set()
        for member in members:
            m = _MEMBER_RE.match(member.filename)
            if m is None:
                raise CafefFormatError(f"unexpected file in archive: {member.filename!r}")
            variant = Variant.RAW if m["raw"] else Variant.ADJUSTED
            variants.add(variant)
            with zf.open(member) as fh:
                df = pd.read_csv(
                    fh,
                    encoding="utf-8-sig",
                    dtype=str,
                    keep_default_na=False,  # a ticker could be spelled "NAN" or "NA"
                )
            if list(df.columns) != EXPECTED_HEADER:
                raise CafefFormatError(
                    f"{member.filename}: header {list(df.columns)} != {EXPECTED_HEADER}"
                )
            df.columns = ["ticker", "trade_date", "open", "high", "low", "close", "volume"]
            df.insert(0, "exchange", m["exchange"])
            df["variant"] = str(variant)
            df["upto"] = datetime.strptime(m["d"], "%d.%m.%Y").date()  # noqa: DTZ007 (a date)
            df["source_file"] = member.filename
            df["row_num"] = pd.RangeIndex(1, len(df) + 1, dtype="int64")
            frames.append(df)
    if not frames:
        raise CafefFormatError("archive contains no CSV files")
    if len(variants) != 1:
        raise CafefFormatError(f"archive mixes raw and adjusted files: {sorted(variants)}")

    out = pd.concat(frames, ignore_index=True)
    out["ticker"] = out["ticker"].str.strip()
    out["trade_date"] = pd.to_datetime(out["trade_date"], format="%Y%m%d")
    for col in ("open", "high", "low", "close"):
        out[col] = pd.to_numeric(out[col], errors="raise").astype("float64")
    out["volume"] = pd.to_numeric(out["volume"], errors="raise").astype("int64")
    out["upto"] = pd.to_datetime(out["upto"])
    return out
