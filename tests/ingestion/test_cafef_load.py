import uuid
from datetime import UTC, datetime

import pandas as pd
import pytest

from ingestion.market.cafef_client import parse_archive
from ingestion.market.cafef_load import COLUMNS, load_object, partition_rows, to_rows
from ingestion.raw_store import InMemoryRawStore
from tests.ingestion.test_cafef_client import RAW_ZIP

NOW = datetime(2026, 11, 24, 4, 0, tzinfo=UTC)


def test_to_rows_adds_lineage_and_keeps_values():
    df = parse_archive(RAW_ZIP)
    rows = to_rows(df, "cafef/x.zip", "ab" * 32, "run1", NOW)
    assert list(rows.columns) == COLUMNS
    assert len(rows) == len(df)
    assert (rows.raw_key == "cafef/x.zip").all() and (rows.load_run_id == "run1").all()
    assert rows.row_num.tolist()[:2] == [1, 2]  # position within each source file
    vcb = rows[rows.ticker == "VCB"].iloc[0]
    assert vcb.close == 61.8 and vcb.trade_date == pd.Timestamp("2026-11-20").date()


@pytest.mark.integration
def test_load_object_is_atomic_and_idempotent():
    """Needs the research stack (ClickHouse) and CLICKHOUSE_* settings in .env."""
    from ingestion.clickhouse import client_from_env

    try:
        client = client_from_env()
    except Exception as e:  # pragma: no cover - depends on local stack
        pytest.skip(f"ClickHouse not available: {e}")
    table = f"test_raw_cafef_eod_{uuid.uuid4().hex[:12]}"
    store = InMemoryRawStore()
    store.put_immutable("cafef/test/a.zip", RAW_ZIP)
    try:
        first = load_object(client, store, "cafef/test/a.zip", table=table, now=NOW)
        again = load_object(client, store, "cafef/test/a.zip", table=table, now=NOW)
        assert first.loaded and not again.loaded
        assert first.rows == partition_rows(client, "cafef/test/a.zip", table) == 4
        got = client.query(
            f"SELECT ticker, close, row_num FROM {table} WHERE ticker = 'NAN'"
        ).result_rows
        assert got == [("NAN", 1.0, 1)]
        leftovers = client.query(
            "SELECT count() FROM system.tables WHERE database = currentDatabase() "
            f"AND name LIKE '_load_{table}_%'"
        ).result_rows[0][0]
        assert leftovers == 0
    finally:
        client.command(f"DROP TABLE IF EXISTS {table}")
