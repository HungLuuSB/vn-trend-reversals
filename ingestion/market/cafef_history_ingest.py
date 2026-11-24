"""Fetch CafeF per-ticker history for the planned ranges, store it raw, load it to ClickHouse.

    uv run python -m ingestion.market.cafef_history_ingest              # whole FETCH_PLAN
    uv run python -m ingestion.market.cafef_history_ingest --ticker ACB # one ticker

Ranges are fetched in calendar-year chunks; each chunk is one raw object (zip of the pages).
"""

from __future__ import annotations

import argparse
import json
import sys
import uuid
from dataclasses import dataclass
from datetime import date

import pandas as pd

from ingestion.clickhouse import client_from_env, count_partition, replace_partition
from ingestion.env import load_dotenv
from ingestion.market.cafef_history_client import (
    CafefHistoryClient,
    HistoryBundle,
    bundle_stem,
    parse_bundle,
    parse_foreign_bundle,
)
from ingestion.raw_store import RawStore, S3RawStore, raw_key, sha256_hex

SOURCE = "cafef_history"
TABLE = "raw_cafef_history"
STUDY_END = date(2026, 11, 20)


@dataclass(frozen=True)
class Fetch:
    ticker: str
    start: date
    end: date
    purpose: str  # gap_fill | vwap_reference | overlap_check
    exchange_type: str = ""  # CafeF filter; "" = endpoint default (works for today's HOSE stocks)
    endpoint: str = "PriceHistory"  # or GDKhoiNgoai (daily foreign trading)


D = date.fromisoformat
# Why each range is fetched. Gap fills follow seed known_price_gaps (clipped to the study period);
# VWAP ranges are UPCoM bank spells and NVB's HNX session-VWAP period (D-003); overlap ranges
# test the endpoint against the bulk archive.
FETCH_PLAN: list[Fetch] = [
    Fetch("ACB", D("2012-01-03"), D("2020-12-01"), "gap_fill"),
    Fetch("SHB", D("2012-01-03"), D("2021-10-05"), "gap_fill"),
    Fetch("HBB", D("2012-01-03"), D("2012-08-16"), "gap_fill"),
    Fetch("VIB", D("2017-01-09"), D("2020-10-29"), "gap_fill"),
    Fetch("LPB", D("2017-10-05"), D("2020-10-23"), "gap_fill"),
    Fetch("NAB", D("2020-10-09"), D("2024-02-28"), "gap_fill"),
    Fetch("BAB", D("2017-12-28"), D("2021-02-24"), "gap_fill", "HNX"),
    Fetch("BVB", D("2020-07-09"), D("2026-07-08"), "gap_fill", "UPCOM"),
    Fetch("VBB", D("2019-07-30"), D("2026-06-29"), "gap_fill", "UPCOM"),
    Fetch("HVG", D("2012-01-03"), D("2018-02-07"), "gap_fill", "UPCOM"),
    Fetch("PVF", D("2012-01-03"), D("2013-09-23"), "gap_fill"),
    Fetch("ABB", D("2020-12-28"), STUDY_END, "vwap_reference", "UPCOM"),
    Fetch("PGB", D("2020-12-24"), STUDY_END, "vwap_reference", "UPCOM"),
    Fetch("SGB", D("2020-10-15"), STUDY_END, "vwap_reference", "UPCOM"),
    Fetch("KLB", D("2017-06-29"), D("2026-01-06"), "vwap_reference", "UPCOM"),
    Fetch("VAB", D("2021-07-20"), D("2025-07-09"), "vwap_reference", "UPCOM"),
    Fetch("PCB", D("2026-08-12"), STUDY_END, "vwap_reference", "UPCOM"),
    Fetch("NVB", D("2012-01-03"), D("2012-03-25"), "vwap_reference", "HNX"),
    Fetch("VCB", D("2015-01-01"), D("2015-12-31"), "overlap_check"),
    Fetch("ACB", D("2021-01-01"), D("2021-12-31"), "overlap_check"),
    Fetch("HPG", D("2020-01-01"), D("2020-12-31"), "overlap_check"),
    # Feature block C (local market, D-009): index levels from the warm-up start, and the
    # market's daily foreign net trading.
    Fetch("VNINDEX", D("2011-10-03"), STUDY_END, "index_level"),
    Fetch("VN30INDEX", D("2012-02-06"), STUDY_END, "index_level"),
    Fetch("VNINDEX", D("2011-10-03"), STUDY_END, "foreign_flow", endpoint="GDKhoiNgoai"),
]

DDL = f"""
CREATE TABLE IF NOT EXISTS {TABLE}
(
    raw_key        String COMMENT 'object key in the S3 raw layer (zip of all pages)',
    raw_sha256     String,
    purpose        LowCardinality(String) COMMENT 'gap_fill, vwap_reference or overlap_check',
    ticker         LowCardinality(String),
    trade_date     Date,
    open           Float64 COMMENT 'thousand VND',
    high           Float64,
    low            Float64,
    close          Float64,
    adj_close      Float64 COMMENT 'CafeF adjusted close, thousand VND',
    volume         Int64 COMMENT 'matched (order-matching) volume',
    value_bn       Float64 COMMENT 'matched value, billion VND, 2 decimals',
    pt_volume      Int64 COMMENT 'put-through volume',
    pt_value_bn    Float64,
    page           LowCardinality(String),
    row_in_page    UInt16,
    fetched_at_utc DateTime64(3, 'UTC'),
    load_run_id    String
)
ENGINE = MergeTree
PARTITION BY raw_key
ORDER BY (ticker, trade_date)
COMMENT 'CafeF per-ticker price history (gap fills, VWAP); see cafef_history_client.py'
"""


def year_chunks(start: date, end: date) -> list[tuple[date, date]]:
    out, y = [], start.year
    while y <= end.year:
        out.append((max(start, date(y, 1, 1)), min(end, date(y, 12, 31))))
        y += 1
    return out


def already_fetched(
    keys: list[str],
    ticker: str,
    start: date,
    end: date,
    exchange_type: str = "",
    endpoint: str = "PriceHistory",
) -> bool:
    stem = bundle_stem(ticker, exchange_type, start, end, endpoint)
    return any(k.rsplit("/", 1)[-1].startswith(stem) for k in keys)


def store_bundle(store: RawStore, bundle: HistoryBundle, purpose: str) -> str:
    content = bundle.to_zip()
    key = raw_key(SOURCE, bundle.fetched_at_utc, bundle.filename, sha256_hex(content))
    store.put_immutable(
        key,
        content,
        {
            "source": SOURCE,
            "ticker": bundle.ticker,
            "range": f"{bundle.start.isoformat()}..{bundle.end.isoformat()}",
            "purpose": purpose,
            "exchange_type": bundle.exchange_type,
            "pages": str(len(bundle.pages)),
            "total_count": str(bundle.total_count),
            "first_url": bundle.urls[0] if bundle.urls else "",
            "fetched_at_utc": bundle.fetched_at_utc.isoformat(),
        },
    )
    return key


FOREIGN_TABLE = "raw_cafef_foreign"
FOREIGN_DDL = f"""
CREATE TABLE IF NOT EXISTS {FOREIGN_TABLE}
(
    raw_key        String COMMENT 'object key in the S3 raw layer (zip of all pages)',
    raw_sha256     String,
    ticker         LowCardinality(String) COMMENT 'stock, or VNINDEX for the whole HOSE market',
    trade_date     Date,
    net_volume     Int64 COMMENT 'foreign buy - sell volume (matched + put-through, as published)',
    net_value_vnd  Float64,
    buy_volume     Int64,
    buy_value_vnd  Float64,
    sell_volume    Int64,
    sell_value_vnd Float64,
    room_remaining Float64,
    ownership_pct  Float64,
    page           LowCardinality(String),
    row_in_page    UInt16,
    fetched_at_utc DateTime64(3, 'UTC'),
    load_run_id    String
)
ENGINE = MergeTree
PARTITION BY raw_key
ORDER BY (ticker, trade_date)
COMMENT 'CafeF daily foreign trading (GDKhoiNgoai); feature block C'
"""


def load_foreign_bundle(client, store: RawStore, key: str, fetched_at, run_id: str) -> int:
    content = store.get(key)
    rows = parse_foreign_bundle(content)
    client.command(FOREIGN_DDL)
    if rows.empty:
        return 0
    if count_partition(client, FOREIGN_TABLE, key) == len(rows):
        return len(rows)
    rows.insert(0, "raw_key", key)
    rows.insert(1, "raw_sha256", sha256_hex(content))
    rows["trade_date"] = rows["trade_date"].dt.date
    rows["fetched_at_utc"] = pd.Timestamp(fetched_at).tz_convert("UTC")
    rows["load_run_id"] = run_id
    replace_partition(client, FOREIGN_TABLE, key, rows, run_id)
    return len(rows)


def load_bundle(client, store: RawStore, key: str, purpose: str, fetched_at, run_id: str) -> int:
    content = store.get(key)
    rows = parse_bundle(content)
    client.command(DDL)
    if rows.empty:
        return 0  # the empty response stays in the raw layer as evidence; nothing to load
    if len(rows) and count_partition(client, TABLE, key) == len(rows):
        return len(rows)
    rows.insert(0, "raw_key", key)
    rows.insert(1, "raw_sha256", sha256_hex(content))
    rows.insert(2, "purpose", purpose)
    rows["trade_date"] = rows["trade_date"].dt.date
    rows["fetched_at_utc"] = pd.Timestamp(fetched_at).tz_convert("UTC")
    rows["load_run_id"] = run_id
    replace_partition(client, TABLE, key, rows, run_id)
    return len(rows)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--ticker", action="append", help="only these tickers from FETCH_PLAN")
    args = parser.parse_args(argv)

    load_dotenv(["S3_"])
    store = S3RawStore.from_env()
    client = client_from_env()
    cafef = CafefHistoryClient()
    run_id = uuid.uuid4().hex
    plan = [f for f in FETCH_PLAN if not args.ticker or f.ticker in args.ticker]
    stored = store.list_keys(f"{SOURCE}/")
    for f in plan:
        for start, end in year_chunks(f.start, f.end):
            if already_fetched(stored, f.ticker, start, end, f.exchange_type, f.endpoint):
                continue  # resumable: this chunk is already in the raw layer
            bundle = cafef.fetch_range(f.ticker, start, end, f.exchange_type, f.endpoint)
            key = store_bundle(store, bundle, f.purpose)
            if f.endpoint == "GDKhoiNgoai":
                n = load_foreign_bundle(client, store, key, bundle.fetched_at_utc, run_id)
            else:
                n = load_bundle(client, store, key, f.purpose, bundle.fetched_at_utc, run_id)
            print(
                json.dumps(
                    {
                        "ticker": f.ticker,
                        "range": f"{start}..{end}",
                        "purpose": f.purpose,
                        "pages": len(bundle.pages),
                        "total": bundle.total_count,
                        "rows": n,
                        "key": key,
                    }  # fmt: skip
                ),
                flush=True,
            )
    return 0


if __name__ == "__main__":
    sys.exit(main())
