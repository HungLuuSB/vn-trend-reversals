"""Clients and parsers for FRED CSV downloads and the Caldara-Iacoviello daily GPR file.

Yahoo series use vnbank.ingestion.market.yahoo_client (same chart endpoint as the corporate-action
cross-check). Every response is stored unchanged in the raw layer before parsing (rule 1).
"""

from __future__ import annotations

import io
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime

import httpx
import pandas as pd

FRED_CSV_URL = "https://fred.stlouisfed.org/graph/fredgraph.csv"
GPR_DTA_URL = "https://www.matteoiacoviello.com/gpr_files/data_gpr_daily_recent.dta"
USER_AGENT = "Mozilla/5.0 (X11; Linux x86_64) vn-bank-data-platform/0.1 research"
# GPR columns used as series. The file's "event" column holds event labels added by the
# authors with hindsight and must never become a feature; moving averages are not used either.
GPR_SERIES = ("GPRD", "GPRD_ACT", "GPRD_THREAT")


class SourceFormatError(ValueError):
    """A download does not look like what the parser expects."""


@dataclass(frozen=True)
class Download:
    source: str
    symbol: str
    url: str
    filename: str
    content: bytes
    fetched_at_utc: datetime


class HttpSource:
    def __init__(
        self,
        http: httpx.Client | None = None,
        *,
        retries: int = 3,
        backoff_seconds: float = 5.0,
        sleep: Callable[[float], None] = time.sleep,
        now: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self._http = http or httpx.Client(
            timeout=httpx.Timeout(60.0), headers={"User-Agent": USER_AGENT}, follow_redirects=True
        )
        self._retries = retries
        self._backoff = backoff_seconds
        self._sleep = sleep
        self._now = now

    def _get(self, url: str, params: dict | None = None) -> httpx.Response:
        for attempt in range(self._retries + 1):
            try:
                resp = self._http.get(url, params=params)
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

    def fetch_fred(self, series_id: str) -> Download:
        resp = self._get(FRED_CSV_URL, {"id": series_id})
        parse_fred_csv(resp.content, series_id)  # validate before storing
        return Download("fred", series_id, str(resp.url), f"{series_id}.csv", resp.content,
                        self._now())  # fmt: skip

    def fetch_gpr(self) -> Download:
        resp = self._get(GPR_DTA_URL)
        parse_gpr_dta(resp.content)
        return Download("gpr", "GPRD", str(resp.url), "data_gpr_daily_recent.dta", resp.content,
                        self._now())  # fmt: skip


def parse_fred_csv(content: bytes, series_id: str) -> pd.DataFrame:
    """FRED graph CSV -> (symbol, obs_date, value). Missing values ('.') are dropped."""
    df = pd.read_csv(io.BytesIO(content), dtype=str, keep_default_na=False)
    if list(df.columns) != ["observation_date", series_id]:
        raise SourceFormatError(f"FRED {series_id}: unexpected columns {list(df.columns)}")
    df = df[df[series_id].str.strip().ne(".") & df[series_id].str.strip().ne("")]
    return pd.DataFrame(
        {
            "symbol": series_id,
            "obs_date": pd.to_datetime(df["observation_date"], format="%Y-%m-%d").dt.date,
            "value": pd.to_numeric(df[series_id], errors="raise").astype("float64"),
        }
    ).reset_index(drop=True)


def parse_gpr_dta(content: bytes) -> pd.DataFrame:
    """Daily GPR Stata file -> long (symbol, obs_date, value) for GPR_SERIES only."""
    df = pd.read_stata(io.BytesIO(content))
    missing = {"DAY", *GPR_SERIES} - set(df.columns)
    if missing:
        raise SourceFormatError(f"GPR file: missing columns {sorted(missing)}")
    dates = pd.to_datetime(df["DAY"].astype(str), format="%Y%m%d").dt.date
    frames = [
        pd.DataFrame({"symbol": s, "obs_date": dates, "value": df[s].astype("float64")})
        for s in GPR_SERIES
    ]
    out = pd.concat(frames, ignore_index=True)
    return out[out["value"].notna()].reset_index(drop=True)
