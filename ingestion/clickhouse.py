"""ClickHouse connection for loaders (wraps clickhouse-connect; CLAUDE.md rule 7)."""

from __future__ import annotations

import os
from collections.abc import Mapping

import clickhouse_connect
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
