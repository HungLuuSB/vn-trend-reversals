"""Download VNDirect foreign-flow history into the raw layer (P2-018; research use only).

    uv run python -m vnbank.ingestion.market.vndirect_foreign_ingest --snapshot b536ec69488162e0
    uv run python -m vnbank.ingestion.market.vndirect_foreign_ingest --codes VNINDEX,VCB \
        --years 2018-2026

Codes default to VNINDEX plus every ticker in the frozen snapshot's research universe. One
request per code and calendar year (from 2018-08-30); each reply page is stored unchanged at
``vndirect_foreign/<fetch date>/vndirect_foreign_<CODE>_<YEAR>_p<n>.<sha8>.json``. Resumable: a
(code, year) already stored is skipped, except the current year, which is always fetched again
(it is still growing).
"""

from __future__ import annotations

import argparse
import re
import sys
from datetime import UTC, date, datetime

import pandas as pd

from vnbank.common import paths
from vnbank.common.env import load_dotenv
from vnbank.common.raw_store import RawStore, S3RawStore, raw_key, sha256_hex
from vnbank.ingestion.market.vndirect_foreign_client import (
    FIRST_DATE,
    ForeignFormatError,
    VndirectForeignClient,
)

SOURCE = "vndirect_foreign"
_STORED = re.compile(r"vndirect_foreign_([A-Z0-9]+)_(\d{4})_p\d+\.")


def stored(store: RawStore) -> set[tuple[str, int]]:
    keys = store.list_keys(f"{SOURCE}/") if hasattr(store, "list_keys") else store.keys()
    out = set()
    for k in keys:
        if m := _STORED.search(k):
            out.add((m[1], int(m[2])))
    return out


def ingest(client: VndirectForeignClient, store: RawStore, codes: list[str], years: list[int],
           today: date | None = None, log=print) -> dict:  # fmt: skip
    today = today or datetime.now(UTC).date()
    have = stored(store)
    st = {"requests": 0, "pages": 0, "rows": 0, "skipped": 0, "failed": []}
    for code in codes:
        for y in years:
            if (code, y) in have and y != today.year:
                st["skipped"] += 1
                continue
            start, end = max(date(y, 1, 1), FIRST_DATE), min(date(y, 12, 31), today)
            if start > end:
                continue
            try:
                pages = client.fetch(code, start, end)
            except ForeignFormatError as e:
                st["failed"].append(f"{code} {y}: {e}")
                log(f"{code} {y}: FAILED {e}")
                continue
            st["requests"] += 1
            n = 0
            for p in pages:
                key = raw_key(SOURCE, p.fetched_at_utc, f"{SOURCE}_{code}_{y}_p{p.page}.json",
                              sha256_hex(p.body))  # fmt: skip
                meta = {"code": code, "year": str(y), "start": str(start), "end": str(end)}
                store.put_immutable(key, p.body, meta)
                st["pages"] += 1
                n += p.body.count(b'"tradingDate"')
            st["rows"] += n
            log(f"{code} {y}: {len(pages)} page(s), {n} rows")
    return st


def universe_codes(snapshot: str) -> list[str]:
    u = pd.read_parquet(paths.SNAPSHOTS / snapshot / "universe_daily.parquet")
    return ["VNINDEX", *sorted(u.ticker.unique())]


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--snapshot", help="frozen snapshot id: codes = VNINDEX + its universe")
    p.add_argument("--codes", default="", help="comma-separated codes instead of --snapshot")
    p.add_argument("--years", default=f"2018-{datetime.now(UTC).year}")
    a = p.parse_args(argv)
    codes = [c.strip().upper() for c in a.codes.split(",") if c.strip()] or (
        universe_codes(a.snapshot) if a.snapshot else [])  # fmt: skip
    if not codes:
        p.error("give --snapshot or --codes")
    y0, y1 = map(int, a.years.split("-"))
    load_dotenv(["S3_"])
    st = ingest(VndirectForeignClient(), S3RawStore.from_env(), codes, list(range(y0, y1 + 1)),
                log=lambda m: print(m, flush=True))  # fmt: skip
    print(st)
    return 0


if __name__ == "__main__":
    sys.exit(main())
