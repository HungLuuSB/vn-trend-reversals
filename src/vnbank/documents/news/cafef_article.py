"""Parse CafeF article pages (raw/cafef_news/ bundles) and find bank mentions (block E, D-023).

Article fields: url, published_at (aware, from the ``pdate`` span's ``datetime`` with its
+07:00 offset), title (``h1.title``), sapo (``h2.sapo``) and body text (the element whose class
contains ``detail-content``). Standard library only.

Mentions: an alias matches as a whole word; tickers and short Latin names are case-sensitive,
Vietnamese names are matched case-insensitively.
"""

from __future__ import annotations

import io
import json
import re
import zipfile
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import datetime
from html import unescape
from html.parser import HTMLParser


@dataclass(frozen=True)
class Article:
    url: str
    published_at: datetime | None
    title: str
    sapo: str
    body: str

    @property
    def text(self) -> str:
        return f"{self.title}\n{self.sapo}\n{self.body}"


class _Extract(HTMLParser):
    """Collects text inside h1.title, h2.sapo and the first *detail-content* element."""

    VOID = {"br", "img", "meta", "link", "input", "hr", "source", "area", "col", "wbr"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.stack: list[tuple[str, str | None]] = []  # (tag, field being captured)
        self.buf = {"title": [], "sapo": [], "body": []}
        self.published = None
        self.body_done = False

    def _field(self) -> str | None:
        for _, f in reversed(self.stack):
            if f:
                return f
        return None

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        cls = a.get("class") or ""
        if a.get("data-role") == "publishdate" and a.get("datetime") and not self.published:
            self.published = a["datetime"]
        if tag in self.VOID:
            return
        field = None
        if tag == "h1" and "title" in cls.split():
            field = "title"
        elif tag == "h2" and "sapo" in cls.split():
            field = "sapo"
        elif "detail-content" in cls and not self.body_done and self._field() is None:
            field = "body"
        if tag in ("script", "style"):
            field = "skip"
        self.stack.append((tag, field))

    def handle_endtag(self, tag):
        if tag in self.VOID:
            return
        while self.stack:
            t, f = self.stack.pop()
            if f == "body":
                self.body_done = True
            if t == tag:
                break

    def handle_data(self, data):
        f = self._field()
        if f in self.buf:
            self.buf[f].append(data)


def _clean(parts: list[str]) -> str:
    return re.sub(r"\s+", " ", unescape(" ".join(parts))).strip()


def parse_article(url: str, html: bytes) -> Article:
    p = _Extract()
    p.feed(html.decode("utf-8", errors="replace"))
    pub = datetime.fromisoformat(p.published) if p.published else None
    if pub is not None and pub.tzinfo is None:
        pub = None  # never guess a time zone
    return Article(url, pub, _clean(p.buf["title"]), _clean(p.buf["sapo"]),
                   _clean(p.buf["body"]))  # fmt: skip


def iter_bundle(zip_bytes: bytes) -> Iterator[Article]:
    """Articles in one raw window bundle (pages with HTTP 200 only)."""
    zf = zipfile.ZipFile(io.BytesIO(zip_bytes))
    index = json.loads(zf.read("index.json"))
    for page in index["pages"]:
        if page["status"] == 200:
            yield parse_article(page["url"], zf.read(page["member"]))


def alias_patterns(aliases: list[tuple[str, str]]) -> dict[str, re.Pattern]:
    """aliases: (ticker, alias) pairs -> one compiled pattern per ticker."""
    by: dict[str, list[str]] = {}
    for t, a in aliases:
        by.setdefault(t, []).append(a)
    out = {}
    for t, names in by.items():
        cs = [re.escape(n) for n in names if n.isascii()]
        ci = [re.escape(n) for n in names if not n.isascii()]
        parts = []
        if cs:
            parts.append(r"(?<![\w])(?:" + "|".join(cs) + r")(?![\w])")
        if ci:
            parts.append(r"(?i:(?<![\w])(?:" + "|".join(ci) + r")(?![\w]))")
        out[t] = re.compile("|".join(parts))
    return out


def mentions(text: str, patterns: dict[str, re.Pattern]) -> set[str]:
    return {t for t, p in patterns.items() if p.search(text)}
