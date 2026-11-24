"""Crawl the CafeF article archive into the raw layer, one zip per 5-day sitemap window.

    uv run python -m vnbank.ingestion.news.cafef_news_ingest --start 2012-01-01 --end 2016-12-31

Resumable: windows already in the raw layer are skipped. Adaptive politeness: 3 parallel
connections to start, one more after each clean window, halved (and a 60 s pause) on any
429, on 5xx/connection errors above 0.5% of requests, or on a doubling of latency; never
above 16. Each connection waits 0.25 s after each request. Parsing and mention counts
come later (D-023).
"""

from __future__ import annotations

import argparse
import re
import sys
import time
from datetime import date

from vnbank.common.env import load_dotenv
from vnbank.common.raw_store import RawStore, S3RawStore, raw_key, sha256_hex
from vnbank.ingestion.news.cafef_news_client import CafefNewsClient, windows

SOURCE = "cafef_news"
_STEM = re.compile(r"^(cafef_news_\d{8}_\d{2})\.")


def done_stems(store: RawStore) -> set[str]:
    keys = store.list_keys(f"{SOURCE}/") if hasattr(store, "list_keys") else store.keys()
    return {m[1] for k in keys if k.startswith(f"{SOURCE}/")
            and (m := _STEM.match(k.rsplit("/", 1)[-1]))}  # fmt: skip


def crawl(client: CafefNewsClient, store: RawStore, start: date, end: date, log=print) -> dict:
    done = done_stems(store)
    stats = {"stored": 0, "skipped": 0, "missing_sitemaps": [], "pages": 0, "failed_pages": 0}
    for w in windows(start, end):
        if w.stem in done:
            stats["skipped"] += 1
            continue
        t0 = time.time()
        b = client.fetch_window(w)
        if b is None:
            stats["missing_sitemaps"].append(w.stem)
            log(f"{w.stem}: no sitemap")
            continue
        body = b.to_zip()
        key = raw_key(SOURCE, b.fetched_at_utc, b.filename, sha256_hex(body))
        bad = sum(1 for _, s, _ in b.pages if s != 200)
        meta = {
            "source_url": w.sitemap_url,
            "pages": str(len(b.pages)),
            "failed_pages": str(bad),
            "fetched_at_utc": b.fetched_at_utc.isoformat(),
        }
        store.put_immutable(key, body, meta)
        stats["stored"] += 1
        stats["pages"] += len(b.pages)
        stats["failed_pages"] += bad
        cs = b.stats
        log(f"{w.stem}: {len(b.pages)} pages ({bad} failed), {len(body) / 1e6:.1f} MB, "
            f"{time.time() - t0:.0f}s, conc {cs.get('concurrency')} "
            f"lat {cs.get('median_latency', 0):.2f}s 429 {cs.get('n429')} "
            f"5xx {cs.get('n5xx')} conn {cs.get('ntransport')} "
            f"-> {cs.get('action')} | {key}")  # fmt: skip
    return stats


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--start", type=date.fromisoformat, required=True)
    p.add_argument("--end", type=date.fromisoformat, required=True)
    a = p.parse_args(argv)
    load_dotenv(["S3_"])
    print(crawl(CafefNewsClient(), S3RawStore.from_env(), a.start, a.end,
                log=lambda m: print(m, flush=True)))  # fmt: skip
    return 0


if __name__ == "__main__":
    sys.exit(main())
