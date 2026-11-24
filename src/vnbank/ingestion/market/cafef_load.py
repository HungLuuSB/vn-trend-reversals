"""Load CafeF archives from the raw layer into ClickHouse table ``raw_cafef_eod``.

Rows are copied exactly as parsed, plus lineage columns (``raw_key``, ``raw_sha256``,
``row_num``, ``loaded_at_utc``, ``load_run_id``). The table is partitioned by ``raw_key``; each
archive is loaded into a scratch table, its row count checked, and then swapped in with
``REPLACE PARTITION``, which is atomic. Re-running is a no-op when the partition is complete.

Usage (from the repo root, research stack running):

    uv run python -m vnbank.ingestion.market.cafef_load            # every CafeF archive in raw
    uv run python -m vnbank.ingestion.market.cafef_load --key <raw_key>
"""

from __future__ import annotations

import argparse
import json
import sys
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

import pandas as pd

from vnbank.common.clickhouse import client_from_env, count_partition, replace_partition
from vnbank.common.env import load_dotenv
from vnbank.common.raw_store import RawStore, S3RawStore, sha256_hex
from vnbank.ingestion.market.cafef_client import parse_archive

TABLE = "raw_cafef_eod"

COLUMNS = [
    "raw_key",
    "raw_sha256",
    "variant",
    "upto",
    "source_file",
    "row_num",
    "exchange",
    "ticker",
    "trade_date",
    "open",
    "high",
    "low",
    "close",
    "volume",
    "loaded_at_utc",
    "load_run_id",
]

DDL = """
CREATE TABLE IF NOT EXISTS {table}
(
    raw_key        String COMMENT 'object key in the S3 raw layer',
    raw_sha256     String COMMENT 'SHA-256 of the raw archive',
    variant        LowCardinality(String) COMMENT 'raw or adjusted',
    upto           Date COMMENT 'last trading date in the archive',
    source_file    LowCardinality(String) COMMENT 'CSV inside the archive',
    row_num        UInt32 COMMENT '1-based data line in source_file',
    exchange       LowCardinality(String) COMMENT 'HSX, HNX or UPCOM',
    ticker         String,
    trade_date     Date COMMENT 'Vietnamese trading date',
    open           Float64 COMMENT 'thousand VND, as published',
    high           Float64,
    low            Float64,
    close          Float64,
    volume         Int64,
    loaded_at_utc  DateTime64(3, 'UTC'),
    load_run_id    String
)
ENGINE = MergeTree
PARTITION BY raw_key
ORDER BY (variant, ticker, trade_date, exchange, row_num)
COMMENT 'CafeF end-of-day archives, one partition per raw object; see ADR 0002'
"""


@dataclass(frozen=True)
class LoadResult:
    raw_key: str
    rows: int
    loaded: bool  # False when the partition was already complete


def ensure_table(client, table: str = TABLE) -> None:
    client.command(DDL.format(table=table))


def to_rows(
    df: pd.DataFrame, raw_key: str, raw_sha256: str, run_id: str, now: datetime
) -> pd.DataFrame:
    out = df.copy()
    out.insert(0, "raw_key", raw_key)
    out.insert(1, "raw_sha256", raw_sha256)
    out["loaded_at_utc"] = pd.Timestamp(now).tz_convert("UTC")
    out["load_run_id"] = run_id
    out["trade_date"] = out["trade_date"].dt.date
    out["upto"] = out["upto"].dt.date
    return out[COLUMNS]


def partition_rows(client, raw_key: str, table: str = TABLE) -> int:
    return count_partition(client, table, raw_key)


def load_object(
    client,
    store: RawStore,
    raw_key: str,
    *,
    table: str = TABLE,
    run_id: str | None = None,
    now: datetime | None = None,
) -> LoadResult:
    content = store.get(raw_key)
    digest = sha256_hex(content)
    df = parse_archive(content)
    expected = len(df)

    ensure_table(client, table)
    if partition_rows(client, raw_key, table) == expected:
        return LoadResult(raw_key, expected, loaded=False)

    run_id = run_id or uuid.uuid4().hex
    rows = to_rows(df, raw_key, digest, run_id, now or datetime.now(UTC))
    replace_partition(client, table, raw_key, rows, run_id)
    return LoadResult(raw_key, expected, loaded=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--key", action="append", help="raw-layer key to load (repeatable)")
    args = parser.parse_args(argv)

    load_dotenv(["S3_"])
    store = S3RawStore.from_env()
    keys = args.key or [k for k in store.list_keys("cafef/") if k.endswith(".zip")]
    client = client_from_env()
    run_id = uuid.uuid4().hex
    for key in keys:
        result = load_object(client, store, key, run_id=run_id)
        print(json.dumps({"key": result.raw_key, "rows": result.rows, "loaded": result.loaded}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
