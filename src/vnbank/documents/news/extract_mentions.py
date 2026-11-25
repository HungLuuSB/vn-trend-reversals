"""Per-article bank mentions from the raw CafeF bundles (block E, D-023).

    uv run python -m vnbank.documents.news.extract_mentions

Incremental: each raw bundle is processed once and written to
data/extracted/news_mentions/<bundle name without .zip>.parquet (window and content hash, so a
repair bundle for an already processed window is still read) with one row per article: url,
published_at_utc, n_chars, and `tickers` (all aliases) / `tickers_strict` (ambiguous aliases
excluded). Daily counts and features are built from these files, never from live pages.
"""

from __future__ import annotations

import csv
import sys

import pandas as pd

from vnbank.common import paths
from vnbank.common.env import load_dotenv
from vnbank.common.raw_store import S3RawStore
from vnbank.documents.news.cafef_article import alias_patterns, iter_bundle, mentions

OUT = paths.REPO / "data" / "extracted" / "news_mentions"


def load_aliases() -> tuple[list[tuple[str, str]], list[tuple[str, str]]]:
    rows = list(csv.DictReader(open(paths.SEEDS / "bank_aliases.csv", encoding="utf-8")))
    every = [(r["ticker"], r["alias"]) for r in rows]
    strict = [(r["ticker"], r["alias"]) for r in rows if r["ambiguous"] != "true"]
    return every, strict


def bundle_rows(zip_bytes: bytes, pats_all, pats_strict) -> pd.DataFrame:
    out = []
    for a in iter_bundle(zip_bytes):
        text = a.text
        out.append({
            "url": a.url,
            "published_at_utc": pd.Timestamp(a.published_at).tz_convert("UTC")
            if a.published_at else pd.NaT,
            "n_chars": len(a.body),
            "tickers": sorted(mentions(text, pats_all)),
            "tickers_strict": sorted(mentions(text, pats_strict)),
        })  # fmt: skip
    return pd.DataFrame(out)


def main() -> int:
    load_dotenv(["S3_"])
    store = S3RawStore.from_env()
    every, strict = load_aliases()
    pa, ps = alias_patterns(every), alias_patterns(strict)
    OUT.mkdir(parents=True, exist_ok=True)
    done = {p.stem for p in OUT.glob("*.parquet")}
    n = 0
    for key in sorted(store.list_keys("cafef_news/")):
        stem = key.rsplit("/", 1)[-1].removesuffix(".zip")  # keeps the hash: repair bundles
        # cover the same window under a new hash and must not be skipped
        if stem in done:
            continue
        df = bundle_rows(store.get(key), pa, ps)
        df["raw_key"] = key
        df.to_parquet(OUT / f"{stem}.parquet", index=False)
        n += 1
        print(f"{stem}: {len(df)} articles, {df.tickers.map(len).gt(0).sum()} with a bank",
              flush=True)  # fmt: skip
    print(f"{n} new bundles -> {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
