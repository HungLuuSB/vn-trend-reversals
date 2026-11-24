import os
import uuid
from datetime import UTC, datetime, timedelta, timezone

import pytest

from vnbank.common.raw_store import (
    InMemoryRawStore,
    RawObjectConflictError,
    S3RawStore,
    raw_key,
    sha256_hex,
)

SHA = sha256_hex(b"x")


def test_raw_key_uses_utc_download_date_and_hash():
    # 01:30 on Nov 21 in Vietnam is still Nov 20 in UTC.
    vn = timezone(timedelta(hours=7))
    t = datetime(2026, 11, 21, 1, 30, tzinfo=vn)
    key = raw_key("cafef", t, "CafeF.SolieuGD.Raw.Upto20112026.zip", SHA)
    assert key == f"cafef/2026-11-20/CafeF.SolieuGD.Raw.Upto20112026.{SHA[:8]}.zip"


def test_raw_key_keeps_multi_part_suffix():
    t = datetime(2026, 1, 2, tzinfo=UTC)
    assert raw_key("x", t, "a.csv.gz", SHA) == f"x/2026-01-02/a.{SHA[:8]}.csv.gz"


@pytest.mark.parametrize("bad", ["../a.zip", "dir/a.zip", ""])
def test_raw_key_rejects_paths(bad):
    with pytest.raises(ValueError):
        raw_key("cafef", datetime(2026, 1, 1, tzinfo=UTC), bad, SHA)


def test_raw_key_rejects_naive_datetime():
    with pytest.raises(ValueError):
        raw_key("cafef", datetime(2026, 1, 1), "a.zip", SHA)  # noqa: DTZ001


def test_in_memory_store_is_idempotent_and_immutable():
    store = InMemoryRawStore()
    first = store.put_immutable("k", b"abc", {"source": "t"})
    again = store.put_immutable("k", b"abc")
    assert first.created and not again.created
    assert store.get("k") == b"abc"
    with pytest.raises(RawObjectConflictError):
        store.put_immutable("k", b"different")
    assert store.get("k") == b"abc"


@pytest.mark.integration
def test_s3_store_against_local_seaweedfs():
    """Needs `docker compose --profile research up -d` and S3_* settings in the environment."""
    from vnbank.common.env import load_dotenv

    load_dotenv(["S3_"])
    if not os.environ.get("S3_SECRET_KEY"):
        pytest.skip("S3 settings not available")
    store = S3RawStore.from_env()
    key = f"_tests/{uuid.uuid4()}.bin"
    obj = store.put_immutable(key, b"hello", {"source": "test"})
    assert obj.created and store.exists(key)
    assert store.get(key) == b"hello"
    assert not store.put_immutable(key, b"hello").created
    with pytest.raises(RawObjectConflictError):
        store.put_immutable(key, b"other")
    assert store.get(key) == b"hello"
