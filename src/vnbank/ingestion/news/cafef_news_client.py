"""CafeF article archive: sitemaps and article pages (Paper 1 block E news counts; D-023).

Facts (observed 2026-11-25; docs/blockE-data-feasibility.md):

* robots.txt: ``User-agent: * / Allow: /``. The sitemap index lists 5-day sitemaps from 2016;
  older ones (from 2012) exist at the same URL pattern but are not listed:
  ``https://cafef.vn/sitemaps/sitemaps-<yyyy>-<m>-<d1>-<d2>.xml`` with day ranges
  1-5, 6-10, 11-15, 16-20, 21-25, 26-<last day>.
* Article pages carry ``<span class="pdate" ... datetime="2014-06-10T23:11:12+07:00">`` (the
  publication time with its offset) and JSON-LD ``datePublished`` without an offset.

Pages are stored unchanged in the raw layer (CLAUDE.md rule 1), one zip per sitemap window.
Use: this research only; not redistributed or served (owner decision 2026-11-25).
"""

from __future__ import annotations

import calendar
import io
import json
import re
import threading
import time
import zipfile
from collections.abc import Callable, Iterator
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import UTC, date, datetime

import httpx

BASE = "https://cafef.vn"
USER_AGENT = "Mozilla/5.0 (X11; Linux x86_64) vn-bank-data-platform/0.1 research"
PAUSE_S = 1.0  # per connection: each worker waits this long after each request
START_CONCURRENCY = 3
MAX_CONCURRENCY = 8  # hard cap: stay well below the point where the site would block us
LATENCY_FACTOR = 2.0  # median latency above 2x the first window's counts as pushback
ZIP_TIME = (2000, 1, 1, 0, 0, 0)
_LOC = re.compile(rb"<loc>\s*([^<\s]+)\s*</loc>")
_PDATE = re.compile(rb'data-role="publishdate"[^>]*datetime="([^"]+)"')


@dataclass(frozen=True)
class Window:
    year: int
    month: int
    d1: int
    d2: int

    @property
    def sitemap_url(self) -> str:
        return f"{BASE}/sitemaps/sitemaps-{self.year}-{self.month}-{self.d1}-{self.d2}.xml"

    @property
    def stem(self) -> str:
        return f"cafef_news_{self.year}{self.month:02d}{self.d1:02d}_{self.d2:02d}"

    @property
    def first_day(self) -> date:
        return date(self.year, self.month, self.d1)


def windows(start: date, end: date) -> Iterator[Window]:
    """Sitemap windows overlapping [start, end], in order."""
    y, m = start.year, start.month
    while (y, m) <= (end.year, end.month):
        last = calendar.monthrange(y, m)[1]
        for d1, d2 in ((1, 5), (6, 10), (11, 15), (16, 20), (21, 25), (26, last)):
            if date(y, m, d2) >= start and date(y, m, d1) <= end:
                yield Window(y, m, d1, d2)
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)


def sitemap_urls(xml: bytes) -> list[str]:
    return [u.decode() for u in _LOC.findall(xml)]


def published_at(html: bytes) -> str | None:
    """The page's publication time as written (ISO 8601 with offset), or None."""
    m = _PDATE.search(html)
    return m[1].decode() if m else None


@dataclass
class Bundle:
    window: Window
    sitemap: bytes
    pages: list[tuple[str, int, bytes]] = field(default_factory=list)  # url, status, body
    fetched_at_utc: datetime = field(default_factory=lambda: datetime.now(UTC))
    stats: dict = field(default_factory=dict)

    @property
    def filename(self) -> str:
        return self.window.stem + ".zip"

    def to_zip(self) -> bytes:
        buf = io.BytesIO()
        index = []
        with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            zf.writestr(zipfile.ZipInfo("sitemap.xml", date_time=ZIP_TIME), self.sitemap,
                        compress_type=zipfile.ZIP_DEFLATED)  # fmt: skip
            for i, (url, status, body) in enumerate(self.pages):
                name = f"p{i:05d}.html"
                zf.writestr(zipfile.ZipInfo(name, date_time=ZIP_TIME), body,
                            compress_type=zipfile.ZIP_DEFLATED)  # fmt: skip
                index.append({"member": name, "url": url, "status": status})
            meta = {"sitemap_url": self.window.sitemap_url,
                    "fetched_at_utc": self.fetched_at_utc.isoformat(), "pages": index}  # fmt: skip
            zf.writestr(zipfile.ZipInfo("index.json", date_time=ZIP_TIME),
                        json.dumps(meta, ensure_ascii=False, indent=1).encode(),
                        compress_type=zipfile.ZIP_DEFLATED)  # fmt: skip
        return buf.getvalue()


class Concurrency:
    """Adaptive number of parallel connections (owner request 2026-11-25: start at 3, increase
    until the server pushes back). Additive increase after a clean window, halving on any
    throttling sign, hard cap MAX_CONCURRENCY."""

    def __init__(self, start: int = START_CONCURRENCY, cap: int = MAX_CONCURRENCY):
        self.n, self.cap = start, cap
        self.base_latency: float | None = None

    def update(self, stats: dict) -> str:
        """stats: pages, throttled (429/5xx/transport errors), median_latency (s)."""
        lat = stats["median_latency"]
        if self.base_latency is None and stats["pages"]:
            self.base_latency = lat
        slow = self.base_latency is not None and lat > LATENCY_FACTOR * self.base_latency
        if stats["throttled"] or slow:
            self.n = max(1, self.n // 2)
            return "down"
        if self.n < self.cap:
            self.n += 1
            return "up"
        return "hold"


class CafefNewsClient:
    def __init__(self, http: httpx.Client | None = None, pause_s: float = PAUSE_S,
                 sleep: Callable[[float], None] = time.sleep,
                 concurrency: Concurrency | None = None):  # fmt: skip
        limits = httpx.Limits(max_connections=MAX_CONCURRENCY + 1)
        self.http = http or httpx.Client(headers={"User-Agent": USER_AGENT}, timeout=30.0,
                                         follow_redirects=False, limits=limits)  # fmt: skip
        self.pause_s, self.sleep = pause_s, sleep
        self.conc = concurrency or Concurrency()
        self._lock = threading.Lock()
        self._stats = {"throttled": 0, "lat": []}

    def get(self, url: str) -> tuple[int, bytes]:
        for attempt in range(3):
            try:
                t0 = time.monotonic()
                r = self.http.get(url)
                with self._lock:
                    self._stats["lat"].append(time.monotonic() - t0)
                self.sleep(self.pause_s)
                if r.status_code in (429, 500, 502, 503, 504):
                    with self._lock:
                        self._stats["throttled"] += 1
                    if attempt < 2:
                        self.sleep(30.0 * (attempt + 1))  # back off, then retry
                        continue
                return r.status_code, r.content
            except httpx.TransportError:
                with self._lock:
                    self._stats["throttled"] += 1
                self.sleep(30.0 * (attempt + 1))
        return -1, b""

    def fetch_window(self, w: Window) -> Bundle | None:
        status, xml = self.get(w.sitemap_url)
        if status != 200 or b"<urlset" not in xml:
            return None
        b = Bundle(w, xml)
        urls = [u for u in sitemap_urls(xml) if u.startswith(BASE + "/")]  # CafeF's own pages
        self._stats = {"throttled": 0, "lat": []}
        n = self.conc.n
        with ThreadPoolExecutor(max_workers=n) as ex:
            for url, (status, body) in zip(urls, ex.map(self.get, urls), strict=True):
                b.pages.append((url, status, body))
        lat = sorted(self._stats["lat"])
        b.stats = {"concurrency": n, "pages": len(urls), "throttled": self._stats["throttled"],
                   "median_latency": lat[len(lat) // 2] if lat else 0.0}  # fmt: skip
        b.stats["action"] = self.conc.update(b.stats)
        if b.stats["action"] == "down":
            self.sleep(60.0)  # let the server recover before the next window
        return b
