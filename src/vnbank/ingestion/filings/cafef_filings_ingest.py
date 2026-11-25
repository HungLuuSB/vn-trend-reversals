"""Download banks' financial-statement PDFs (CafeF mirror) into the raw layer (block E).

    uv run python -m vnbank.ingestion.filings.cafef_filings_ingest --symbols ACB --years 2011-2017
    ... --kinds HN,HNSX,HNKT,M     # only the statement kinds block E uses (D-023)

Stores each list reply and each PDF unchanged. Resumable: PDFs already stored (by file name,
any download date) are skipped. Bank tickers default to dbt/seeds/bank_spells.csv.

The list endpoint intermittently answers an empty list for a year that has filings (observed
2026-11-25: BID 2015 empty four times, then 12 filings), so an empty list is retried up to
EMPTY_RETRIES times before the year is reported as empty.
"""

from __future__ import annotations

import argparse
import re
import sys

import pandas as pd

from vnbank.common import paths
from vnbank.common.env import load_dotenv
from vnbank.common.raw_store import RawStore, S3RawStore, raw_key, sha256_hex
from vnbank.ingestion.filings.cafef_filings_client import CafefFilingsClient

SOURCE = "cafef_filings"
EMPTY_RETRIES = 8
RETRY_PAUSE_S = 3.0


def stored_pdfs(store: RawStore) -> set[str]:
    keys = store.list_keys(f"{SOURCE}/") if hasattr(store, "list_keys") else store.keys()
    out = set()
    for k in keys:
        name = k.rsplit("/", 1)[-1]
        m = re.match(r"^(.*)\.[0-9a-f]{8}(\.(?:pdf|zip|rar|7z|docx))$", name, re.I)
        if k.startswith(f"{SOURCE}/") and m:
            out.add(m[1] + m[2])
    return out


def wanted(filename: str, kinds: set[str] | None) -> bool:
    """kinds filter (e.g. the four statement kinds D-023 uses). A name the parser does not
    recognise is always downloaded, so nothing is lost to an unexpected naming scheme."""
    if not kinds:
        return True
    from vnbank.documents.extract_bank_fs import parse_name

    meta = parse_name(filename)
    return meta is None or meta["kind"] in kinds


def ingest(client: CafefFilingsClient, store: RawStore, symbols: list[str], years: list[int],
           log=print, kinds: set[str] | None = None) -> dict:  # fmt: skip
    have = stored_pdfs(store)
    st = {"lists": 0, "pdfs": 0, "skipped": 0, "failed": [], "empty": [], "not_wanted": 0}
    for sym in (s.upper() for s in symbols):
        for y in years:
            for _ in range(EMPTY_RETRIES):
                body, filings, fetched = client.list_filings(sym, y)
                key = raw_key(SOURCE, fetched, f"list_{sym}_{y}.json", sha256_hex(body))
                store.put_immutable(key, body, {"symbol": sym, "year": str(y)})
                st["lists"] += 1
                if filings:
                    break
                client.sleep(RETRY_PAUSE_S)
            else:
                st["empty"].append(f"{sym} {y}")
                log(f"{sym} {y}: empty list after {EMPTY_RETRIES} tries")
            for f in filings:
                if not wanted(f.filename, kinds):
                    st["not_wanted"] += 1
                    continue
                if f.filename in have:
                    st["skipped"] += 1
                    continue
                status, pdf, fetched = client.pdf(f)
                if status != 200:
                    st["failed"].append(f"{f.filename} ({status})")
                    log(f"{sym} {y} {f.period} {f.filename}: FAILED {status}")
                    continue
                meta = {"symbol": sym, "year": str(y), "quarter": str(f.quarter),
                        "period": f.period, "listed_link": f.link, "source_url": f.pdf_url,
                        "fetched_at_utc": fetched.isoformat()}  # fmt: skip
                store.put_immutable(raw_key(SOURCE, fetched, f.filename, sha256_hex(pdf)), pdf,
                                    meta)  # fmt: skip
                have.add(f.filename)
                st["pdfs"] += 1
                log(f"{sym} {y} {f.period} {f.filename}: {len(pdf) / 1e6:.1f} MB")
    return st


def bank_tickers() -> list[str]:
    return sorted(pd.read_csv(paths.SEEDS / "bank_spells.csv").ticker.unique())


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--symbols", default="", help="comma-separated; default: all bank tickers")
    p.add_argument("--years", required=True, help="e.g. 2011-2017")
    p.add_argument("--kinds", default="", help="e.g. HN,HNSX,HNKT,M (default: every kind)")
    a = p.parse_args(argv)
    y0, y1 = map(int, a.years.split("-"))
    syms = a.symbols.split(",") if a.symbols else bank_tickers()
    load_dotenv(["S3_"])
    kinds = set(a.kinds.split(",")) if a.kinds else None
    print(ingest(CafefFilingsClient(), S3RawStore.from_env(), syms, list(range(y0, y1 + 1)),
                 log=lambda m: print(m, flush=True), kinds=kinds))  # fmt: skip
    return 0


if __name__ == "__main__":
    sys.exit(main())
