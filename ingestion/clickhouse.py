"""ClickHouse connection for loaders (wraps clickhouse-connect; CLAUDE.md rule 7)."""

from __future__ import annotations

import os
from collections.abc import Mapping

import clickhouse_connect
import pandas as pd
from clickhouse_connect.driver.client import Client

from ingestion.env import load_dotenv


def client_from_env(env: Mapping[str, str] | None = None, database: str | None = None) -> Client:
    """Connect with ``CLICKHOUSE_*`` settings (from the environment or ``.env``)."""
    if env is None:
        load_dotenv(["CLICKHOUSE_"])
        env = os.environ
    missing = [k for k in ("CLICKHOUSE_USER", "CLICKHOUSE_PASSWORD") if not env.get(k)]
    if missing:
        raise RuntimeError(f"missing environment variables: {', '.join(missing)}")
    return clickhouse_connect.get_client(
        host=env.get("CLICKHOUSE_HOST", "localhost"),
        port=int(env.get("CLICKHOUSE_HTTP_PORT", "8123")),
        username=env["CLICKHOUSE_USER"],
        password=env["CLICKHOUSE_PASSWORD"],
        database=database or env.get("CLICKHOUSE_DB", "vnbank"),
        settings={"session_timezone": "UTC"},
        send_receive_timeout=600,
    )


def count_partition(client: Client, table: str, raw_key: str) -> int:
    """Rows currently loaded from one raw object (tables are partitioned by ``raw_key``)."""
    return int(
        client.query(
            f"SELECT count() FROM {table} WHERE raw_key = {{k:String}}", parameters={"k": raw_key}
        ).result_rows[0][0]
    )


def replace_partition(
    client: Client, table: str, raw_key: str, rows: pd.DataFrame, run_id: str
) -> None:
    """Atomically make ``rows`` the full content of partition ``raw_key`` in ``table``.

    Rows go into a scratch copy of the table first; only when the scratch row count is right is
    the partition swapped in with ``REPLACE PARTITION``. A crash leaves the old partition intact
    (or absent), never half loaded. No rows are deleted outside the replaced partition.
    """
    expected = len(rows)
    if expected == 0:
        # Nothing to load. ClickHouse refuses REPLACE PARTITION from an empty source, and an
        # empty load must never wipe rows loaded earlier from the same immutable raw object.
        if count_partition(client, table, raw_key):
            raise RuntimeError(f"{raw_key}: empty load would replace existing rows")
        return
    scratch = f"_load_{table}_{run_id}"
    client.command(f"CREATE TABLE {scratch} AS {table}")
    try:
        if expected:
            client.insert_df(scratch, rows)
        got = int(client.query(f"SELECT count() FROM {scratch}").result_rows[0][0])
        if got != expected:
            raise RuntimeError(f"{raw_key}: scratch table has {got} rows, expected {expected}")
        client.command(
            f"ALTER TABLE {table} REPLACE PARTITION {{k:String}} FROM {scratch}",
            parameters={"k": raw_key},
        )
    finally:
        client.command(f"DROP TABLE IF EXISTS {scratch}")
    got = count_partition(client, table, raw_key)
    if got != expected:
        raise RuntimeError(f"{raw_key}: table has {got} rows after load, expected {expected}")
