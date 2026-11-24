"""Fetch Yahoo chart payloads, store them raw, and load their events into ClickHouse.

Used only to cross-check the corporate actions we infer from CafeF (ADR 0002, step 2).

    uv run python -m vnbank.ingestion.market.yahoo_ingest                  # validation sample
    uv run python -m vnbank.ingestion.market.yahoo_ingest --symbol VCB.VN
"""

from __future__ import annotations

import argparse
import json
import sys
import uuid
from datetime import UTC, date, datetime

import pandas as pd

from vnbank.common.clickhouse import client_from_env, count_partition, replace_partition
from vnbank.common.env import load_dotenv
from vnbank.common.raw_store import RawStore, S3RawStore, raw_key, sha256_hex
from vnbank.ingestion.market.yahoo_client import YahooChart, YahooChartClient, parse_events

SOURCE = "yahoo"
TABLE = "raw_yahoo_events"

# Validation sample: the listed banks plus large HOSE stocks that were VN30 members for long
# stretches. Not the research universe (that comes from point-in-time VN30 membership).
# Yahoo carries HOSE symbols (".VN"); HNX/UPCoM banks are expected to be missing.
BANKS = (
    "ABB ACB BAB BID BVB CTG EIB HDB KLB LPB MBB MSB NAB NVB OCB PGB SGB SHB SSB STB TCB "
    "TPB VAB VBB VCB VIB VPB"
).split()
LARGE_HOSE = (
    "VNM VIC VHM VRE HPG MSN MWG FPT GAS SAB PLX POW GVR BCM SSI VJC BVH PNJ REE KDH NVL "
    "PDR DPM DHG CII HSG ITA KDC FLC ROS"
).split()
VALIDATION_SAMPLE = [f"{t}.VN" for t in BANKS + LARGE_HOSE]

DDL = f"""
CREATE TABLE IF NOT EXISTS {TABLE}
(
    raw_key          String COMMENT 'object key in the S3 raw layer',
    raw_sha256       String,
    symbol           LowCardinality(String) COMMENT 'Yahoo symbol, e.g. VCB.VN',
    ticker           LowCardinality(String) COMMENT 'symbol without the exchange suffix',
    event_type       LowCardinality(String) COMMENT 'split, dividend, or none (coverage only)',
    ex_date          Date COMMENT 'ex-date in the exchange time zone',
    event_ts_utc     DateTime64(3, 'UTC'),
    numerator        Float64,
    denominator      Float64,
    amount           Float64 COMMENT 'dividend in VND, rescaled by later splits (Yahoo)',
    currency         LowCardinality(String),
    exchange_tz      LowCardinality(String),
    data_first_date  Nullable(Date),
    data_last_date   Nullable(Date),
    fetched_at_utc   DateTime64(3, 'UTC'),
    load_run_id      String
)
ENGINE = MergeTree
PARTITION BY raw_key
ORDER BY (ticker, ex_date, event_type)
COMMENT 'Yahoo dividend/split events for cross-checking corporate actions'
"""


def store_chart(store: RawStore, chart: YahooChart) -> str:
    digest = sha256_hex(chart.content)
    key = raw_key(SOURCE, chart.fetched_at_utc, f"{chart.symbol}.json", digest)
    store.put_immutable(
        key,
        chart.content,
        {
            "source": SOURCE,
            "source_url": chart.url,
            "symbol": chart.symbol,
            "fetched_at_utc": chart.fetched_at_utc.isoformat(),
        },
    )
    return key


def load_chart(client, store: RawStore, key: str, fetched_at_utc: datetime, run_id: str) -> int:
    content = store.get(key)
    events = parse_events(content)
    client.command(DDL)
    if count_partition(client, TABLE, key) == len(events) and len(events):
        return len(events)
    events.insert(0, "raw_key", key)
    events.insert(1, "raw_sha256", sha256_hex(content))
    events.insert(3, "ticker", events["symbol"].str.split(".").str[0])
    events["fetched_at_utc"] = pd.Timestamp(fetched_at_utc).tz_convert("UTC")
    events["load_run_id"] = run_id
    replace_partition(client, TABLE, key, events, run_id)
    return len(events)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--symbol", action="append", help="Yahoo symbol (repeatable)")
    parser.add_argument("--start", type=date.fromisoformat, default=date(2000, 1, 1))
    args = parser.parse_args(argv)

    load_dotenv(["S3_"])
    store = S3RawStore.from_env()
    client = client_from_env()
    yahoo = YahooChartClient()
    run_id = uuid.uuid4().hex
    end = datetime.now(UTC).date()
    for symbol in args.symbol or VALIDATION_SAMPLE:
        chart = yahoo.fetch_chart(symbol, args.start, end)
        if chart is None:
            print(json.dumps({"symbol": symbol, "status": "not_found"}))
            continue
        key = store_chart(store, chart)
        n = load_chart(client, store, key, chart.fetched_at_utc, run_id)
        print(json.dumps({"symbol": symbol, "key": key, "events": n}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
