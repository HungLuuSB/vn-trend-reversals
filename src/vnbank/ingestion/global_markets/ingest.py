"""Fetch the global series listed in dbt/seeds/global_series.csv, store them raw, load them.

    uv run python -m vnbank.ingestion.global_markets.ingest            # every series in the seed
    uv run python -m vnbank.ingestion.global_markets.ingest --series spx --series vix

Yahoo and FRED: one raw object per symbol. GPR: one file holds all three GPR series.
Everything lands in ClickHouse table raw_global_obs (one partition per raw object).
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
import uuid
from datetime import UTC, date, datetime
from pathlib import Path

import pandas as pd

from vnbank.common import paths
from vnbank.common.clickhouse import client_from_env, count_partition, replace_partition
from vnbank.common.env import load_dotenv
from vnbank.common.raw_store import RawStore, S3RawStore, raw_key, sha256_hex
from vnbank.ingestion.global_markets.sources import (
    Download,
    HttpSource,
    parse_fred_csv,
    parse_gpr_dta,
)
from vnbank.ingestion.market.yahoo_client import YahooChartClient, parse_quotes

SEED = paths.REPO / "dbt" / "seeds" / "global_series.csv"
TABLE = "raw_global_obs"
HISTORY_START = date(2000, 1, 1)  # well before the 2011-10 warm-up (D-001)

DDL = f"""
CREATE TABLE IF NOT EXISTS {TABLE}
(
    raw_key        String COMMENT 'object key in the S3 raw layer',
    raw_sha256     String,
    source         LowCardinality(String) COMMENT 'yahoo, fred or gpr',
    symbol         LowCardinality(String) COMMENT 'symbol as in seed global_series',
    obs_date       Date COMMENT 'date the value describes (local to its market)',
    open           Nullable(Float64),
    high           Nullable(Float64),
    low            Nullable(Float64),
    close          Float64 COMMENT 'close, or the value for FRED and GPR series',
    volume         Nullable(Int64),
    fetched_at_utc DateTime64(3, 'UTC'),
    load_run_id    String
)
ENGINE = MergeTree
PARTITION BY raw_key
ORDER BY (symbol, obs_date)
COMMENT 'Global series for feature block D (D-009); availability rules in seed global_series'
"""


def read_seed(path: Path = SEED) -> list[dict]:
    with open(path, encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def store(store_: RawStore, d: Download) -> str:
    key = raw_key(f"global_{d.source}", d.fetched_at_utc, d.filename, sha256_hex(d.content))
    store_.put_immutable(
        key,
        d.content,
        {
            "source": d.source,
            "symbol": d.symbol,
            "source_url": d.url,
            "fetched_at_utc": d.fetched_at_utc.isoformat(),
        },  # fmt: skip
    )
    return key


def parse(source: str, symbol: str, content: bytes) -> pd.DataFrame:
    if source == "yahoo":
        return parse_quotes(content).assign(symbol=symbol)
    if source == "fred":
        df = parse_fred_csv(content, symbol)
    elif source == "gpr":
        df = parse_gpr_dta(content)
    else:
        raise ValueError(f"unknown source {source!r}")
    return df.rename(columns={"value": "close"}).assign(open=None, high=None, low=None, volume=None)


def load(client, store_: RawStore, key: str, source: str, symbol: str, fetched_at, run_id) -> int:
    content = store_.get(key)
    rows = parse(source, symbol, content)
    # ClickHouse Date starts at 1970 (FRED DGS10 starts in 1962). Only data from 2000 is used;
    # the raw object in the raw layer keeps the full history.
    rows = rows[rows["obs_date"] >= date(1970, 1, 1)]
    client.command(DDL)
    if rows.empty:
        return 0
    if count_partition(client, TABLE, key) == len(rows):
        return len(rows)
    rows = rows[["symbol", "obs_date", "open", "high", "low", "close", "volume"]].copy()
    rows.insert(0, "raw_key", key)
    rows.insert(1, "raw_sha256", sha256_hex(content))
    rows.insert(2, "source", source)
    rows["fetched_at_utc"] = pd.Timestamp(fetched_at).tz_convert("UTC")
    rows["load_run_id"] = run_id
    for c in ("open", "high", "low"):
        rows[c] = rows[c].astype("Float64")
    rows["volume"] = rows["volume"].astype("Int64")
    replace_partition(client, TABLE, key, rows, run_id)
    return len(rows)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--series", action="append", help="series_id from the seed (repeatable)")
    args = parser.parse_args(argv)

    seed = [r for r in read_seed() if not args.series or r["series_id"] in args.series]
    load_dotenv(["S3_"])
    raw = S3RawStore.from_env()
    client = client_from_env()
    yahoo, http = YahooChartClient(), HttpSource()
    run_id = uuid.uuid4().hex
    gpr_done = False
    for r in seed:
        source, symbol = r["source"], r["symbol"]
        if source == "yahoo":
            chart = yahoo.fetch_chart(symbol, HISTORY_START, datetime.now(UTC).date())
            if chart is None:
                print(json.dumps({"series": r["series_id"], "status": "not_found"}))
                continue
            d = Download("yahoo", symbol, chart.url, f"{symbol}.json", chart.content,
                         chart.fetched_at_utc)  # fmt: skip
        elif source == "fred":
            d = http.fetch_fred(symbol)
        elif source == "gpr":
            if gpr_done:
                continue  # one file carries every GPR series
            d, gpr_done = http.fetch_gpr(), True
        else:
            raise ValueError(f"unknown source {source!r}")
        key = store(raw, d)
        n = load(client, raw, key, source, symbol, d.fetched_at_utc, run_id)
        print(json.dumps({"series": r["series_id"], "source": source, "rows": n, "key": key}),
              flush=True)  # fmt: skip
    return 0


if __name__ == "__main__":
    sys.exit(main())
