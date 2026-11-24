"""Client for Yahoo Finance's chart endpoint, used to cross-check corporate actions (step 2).

We call the JSON endpoint directly with httpx instead of using yfinance, so the exact response
bytes can be stored in the raw layer before parsing (CLAUDE.md rule 1). Only events (dividends,
splits) and the series' first/last dates are parsed; Yahoo prices are not used as model input.

Yahoo conventions seen in practice for Vietnamese (``.VN``) symbols:

* Stock dividends and bonus shares appear as *splits* (``1181:1000`` for an 18.1% stock
  dividend).
* Cash dividend amounts are in VND and are rescaled by splits on or after their ex-date; the
  as-paid amount is ``amount * product(split ratios with ex_date >= this ex_date)``.
* Timestamps are 09:00 in the exchange time zone on the ex-date.
"""

from __future__ import annotations

import json
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, date, datetime
from datetime import time as dtime
from zoneinfo import ZoneInfo

import httpx
import pandas as pd

CHART_URL = "https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
USER_AGENT = "Mozilla/5.0 (X11; Linux x86_64) vn-bank-data-platform/0.1 research"

EVENT_COLUMNS = [
    "symbol",
    "event_type",
    "ex_date",
    "event_ts_utc",
    "numerator",
    "denominator",
    "amount",
    "currency",
    "exchange_tz",
    "data_first_date",
    "data_last_date",
]


class YahooFormatError(ValueError):
    """The response is not a chart payload this parser understands."""


@dataclass(frozen=True)
class YahooChart:
    symbol: str
    url: str
    content: bytes
    fetched_at_utc: datetime


def _epoch(d: date) -> int:
    return int(datetime.combine(d, dtime(0, 0), tzinfo=UTC).timestamp())


class YahooChartClient:
    def __init__(
        self,
        http: httpx.Client | None = None,
        *,
        retries: int = 3,
        backoff_seconds: float = 5.0,
        min_interval_seconds: float = 1.5,
        sleep: Callable[[float], None] = time.sleep,
        now: Callable[[], datetime] = lambda: datetime.now(UTC),
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        self._http = http or httpx.Client(
            timeout=httpx.Timeout(30.0), headers={"User-Agent": USER_AGENT}
        )
        self._retries = retries
        self._backoff = backoff_seconds
        self._interval = min_interval_seconds
        self._sleep = sleep
        self._now = now
        self._monotonic = monotonic
        self._last_call: float | None = None

    def _pace(self) -> None:
        if self._last_call is not None:
            wait = self._interval - (self._monotonic() - self._last_call)
            if wait > 0:
                self._sleep(wait)
        self._last_call = self._monotonic()

    def fetch_chart(self, symbol: str, start: date, end: date) -> YahooChart | None:
        """Daily chart with dividend and split events; ``None`` if Yahoo has no such symbol."""
        url = CHART_URL.format(symbol=symbol)
        params = {
            "period1": _epoch(start),
            "period2": _epoch(end),
            "interval": "1d",
            "events": "div|split",
            "includeAdjustedClose": "true",
        }
        for attempt in range(self._retries + 1):
            self._pace()
            try:
                resp = self._http.get(url, params=params)
            except httpx.TransportError:
                if attempt == self._retries:
                    raise
            else:
                if resp.status_code == 404:
                    return None
                if resp.status_code < 500 and resp.status_code != 429:
                    resp.raise_for_status()
                    _check_payload(resp.content, symbol)
                    return YahooChart(symbol, str(resp.url), resp.content, self._now())
                if attempt == self._retries:
                    resp.raise_for_status()
            self._sleep(self._backoff * 2**attempt)
        raise AssertionError("unreachable")


def _check_payload(content: bytes, symbol: str) -> None:
    try:
        chart = json.loads(content)["chart"]
    except (ValueError, KeyError, TypeError) as e:
        raise YahooFormatError(f"{symbol}: response is not a chart payload") from e
    if chart.get("error") is None and not chart.get("result"):
        raise YahooFormatError(f"{symbol}: chart payload has neither result nor error")


def parse_events(content: bytes) -> pd.DataFrame:
    """Events of one chart payload, one row per dividend or split.

    A symbol with price data but no events yields one row with ``event_type = 'none'``, so its
    coverage (``data_first_date``..``data_last_date``) is still recorded. A payload whose chart
    reports an error (e.g. delisted symbol) yields no rows.
    """
    chart = json.loads(content)["chart"]
    if chart.get("error") is not None or not chart.get("result"):
        return pd.DataFrame(columns=EVENT_COLUMNS)
    result = chart["result"][0]
    meta = result["meta"]
    symbol = meta["symbol"]
    tz = ZoneInfo(meta.get("exchangeTimezoneName") or "Asia/Ho_Chi_Minh")
    stamps = result.get("timestamp") or []

    def local_date(ts: int) -> date:
        return datetime.fromtimestamp(int(ts), tz).date()

    first = local_date(stamps[0]) if stamps else None
    last = local_date(stamps[-1]) if stamps else None
    common = {
        "symbol": symbol,
        "currency": meta.get("currency") or "",
        "exchange_tz": str(tz),
        "data_first_date": first,
        "data_last_date": last,
    }
    rows = []
    events = result.get("events") or {}
    for ts, ev in (events.get("splits") or {}).items():
        rows.append(
            {
                **common,
                "event_type": "split",
                "ex_date": local_date(ts),
                "event_ts_utc": datetime.fromtimestamp(int(ts), UTC),
                "numerator": float(ev["numerator"]),
                "denominator": float(ev["denominator"]),
                "amount": 0.0,
            }
        )
    for ts, ev in (events.get("dividends") or {}).items():
        rows.append(
            {
                **common,
                "event_type": "dividend",
                "ex_date": local_date(ts),
                "event_ts_utc": datetime.fromtimestamp(int(ts), UTC),
                "numerator": 0.0,
                "denominator": 0.0,
                "amount": float(ev["amount"]),
            }
        )
    if not rows and stamps:
        rows.append(
            {
                **common,
                "event_type": "none",
                "ex_date": first,
                "event_ts_utc": datetime.fromtimestamp(int(stamps[0]), UTC),
                "numerator": 0.0,
                "denominator": 0.0,
                "amount": 0.0,
            }
        )
    out = pd.DataFrame(rows, columns=EVENT_COLUMNS)
    return out.sort_values(["ex_date", "event_type"], ignore_index=True)


def parse_quotes(content: bytes) -> pd.DataFrame:
    """Daily OHLCV bars of one chart payload; obs_date is the bar's date in the exchange time
    zone. Raw (unadjusted) values only: adjclose is ignored (CLAUDE.md rule 7). Bars with no
    close (holidays Yahoo fills with nulls) are dropped."""
    chart = json.loads(content)["chart"]
    cols = ["symbol", "obs_date", "open", "high", "low", "close", "volume"]
    if chart.get("error") is not None or not chart.get("result"):
        return pd.DataFrame(columns=cols)
    result = chart["result"][0]
    tz = ZoneInfo(result["meta"].get("exchangeTimezoneName") or "UTC")
    stamps = result.get("timestamp") or []
    quote = (result.get("indicators", {}).get("quote") or [{}])[0]
    df = pd.DataFrame(
        {
            "symbol": result["meta"]["symbol"],
            "obs_date": [datetime.fromtimestamp(int(t), tz).date() for t in stamps],
            "open": quote.get("open", [None] * len(stamps)),
            "high": quote.get("high", [None] * len(stamps)),
            "low": quote.get("low", [None] * len(stamps)),
            "close": quote.get("close", [None] * len(stamps)),
            "volume": quote.get("volume", [None] * len(stamps)),
        },
        columns=cols,
    )
    df = df[df["close"].notna()].copy()
    for c in ("open", "high", "low", "close"):
        df[c] = df[c].astype("float64")
    df["volume"] = df["volume"].fillna(0).astype("int64")
    # Yahoo occasionally repeats the last bar (intraday snapshot); keep one row per date.
    return df.drop_duplicates(["symbol", "obs_date"], keep="last").reset_index(drop=True)
