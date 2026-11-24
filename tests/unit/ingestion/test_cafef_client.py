import io
import zipfile
from datetime import UTC, date, datetime

import httpx
import pandas as pd
import pytest

from vnbank.common.raw_store import InMemoryRawStore
from vnbank.ingestion.market.cafef_client import (
    CafefClient,
    CafefFormatError,
    Variant,
    archive_url,
    parse_archive,
)
from vnbank.ingestion.market.cafef_ingest import ingest

HEADER = "<Ticker>,<DTYYYYMMDD>,<Open>,<High>,<Low>,<Close>,<Volume>"
FIXED_NOW = datetime(2026, 11, 24, 3, 0, tzinfo=UTC)  # 10:00 in Vietnam


def make_zip(files: dict[str, str]) -> bytes:
    """Build an archive the way CafeF does: UTF-8 with BOM, CRLF line ends."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for name, body in files.items():
            zf.writestr(name, ("﻿" + body.replace("\n", "\r\n")).encode("utf-8"))
    return buf.getvalue()


RAW_ZIP = make_zip(
    {
        "CafeF.RAW_HSX.Upto20.11.2026.csv": f"{HEADER}\nVCB,20261120,61.5,62,61.2,61.8,1785800\n"
        "VCB,20261119,61,61.6,60.9,61.5,1500000\n",
        "CafeF.RAW_HNX.Upto20.11.2026.csv": f"{HEADER}\nNAN,20261120,1,1.1,1,1,139100\n",
        "CafeF.RAW_UPCOM.Upto20.11.2026.csv": f"{HEADER}\nABB,20261120,9.5,9.6,9.4,9.5,100\n",
    }
)


def client_for(handler, **kw) -> CafefClient:
    http = httpx.Client(transport=httpx.MockTransport(handler))
    return CafefClient(http, sleep=lambda s: None, now=lambda: FIXED_NOW, **kw)


def test_archive_urls():
    d = date(2026, 11, 20)
    assert archive_url(d, Variant.RAW) == (
        "https://cafef1.mediacdn.vn/data/ami_data/20261120/CafeF.SolieuGD.Raw.Upto20112026.zip"
    )
    assert archive_url(d, Variant.ADJUSTED).endswith("/20261120/CafeF.SolieuGD.Upto20112026.zip")


def test_fetch_returns_none_on_404():
    client = client_for(lambda req: httpx.Response(404))
    assert client.fetch(date(2026, 11, 21), Variant.RAW) is None


def test_fetch_retries_server_errors_then_succeeds():
    calls = []

    def handler(req):
        calls.append(req.url)
        if len(calls) < 3:
            return httpx.Response(503)
        return httpx.Response(200, content=RAW_ZIP, headers={"Last-Modified": "Fri, 20 Nov"})

    archive = client_for(handler).fetch(date(2026, 11, 20), Variant.RAW)
    assert len(calls) == 3
    assert archive.content == RAW_ZIP
    assert archive.fetched_at_utc == FIXED_NOW
    assert archive.last_modified == "Fri, 20 Nov"


def test_fetch_gives_up_after_retries():
    client = client_for(lambda req: httpx.Response(503), retries=2)
    with pytest.raises(httpx.HTTPStatusError):
        client.fetch(date(2026, 11, 20), Variant.RAW)


def test_fetch_rejects_non_zip_body():
    client = client_for(lambda req: httpx.Response(200, content=b"<html>error</html>"))
    with pytest.raises(CafefFormatError):
        client.fetch(date(2026, 11, 20), Variant.RAW)


def test_fetch_latest_walks_back_from_vietnam_today():
    seen = []

    def handler(req):
        seen.append(req.url.path.split("/")[-2])
        return (
            httpx.Response(200, content=RAW_ZIP)
            if "20261120" in req.url.path
            else httpx.Response(404)
        )

    archive = client_for(handler).fetch_latest(Variant.RAW)
    assert archive.as_of == date(2026, 11, 20)
    assert seen == ["20261124", "20261123", "20261122", "20261121", "20261120"]


def test_fetch_latest_raises_when_nothing_found():
    with pytest.raises(LookupError):
        client_for(lambda req: httpx.Response(404)).fetch_latest(Variant.RAW, max_lookback_days=2)


def test_parse_archive_shapes_types_and_tricky_tickers():
    df = parse_archive(RAW_ZIP)
    assert len(df) == 4
    assert set(df.exchange) == {"HSX", "HNX", "UPCOM"}
    assert "NAN" in set(df.ticker)  # not turned into a missing value
    assert (df.variant == "raw").all()
    assert df.trade_date.dtype == "datetime64[ns]" or str(df.trade_date.dtype).startswith(
        "datetime64"
    )
    assert df.volume.dtype == "int64"
    vcb = df[(df.ticker == "VCB") & (df.trade_date == pd.Timestamp("2026-11-20"))].iloc[0]
    assert (vcb.open, vcb.high, vcb.low, vcb.close, vcb.volume) == (61.5, 62.0, 61.2, 61.8, 1785800)
    assert vcb.upto == pd.Timestamp("2026-11-20")


def test_parse_archive_reads_adjusted_files():
    z = make_zip({"CafeF.HSX.Upto20.11.2026.csv": f"{HEADER}\nVCB,20261120,61.5,62,61.2,61.8,10\n"})
    assert (parse_archive(z).variant == "adjusted").all()


def test_parse_archive_rejects_changed_header():
    z = make_zip({"CafeF.RAW_HSX.Upto20.11.2026.csv": "Ticker,Date,Open,High,Low,Close,Volume\n"})
    with pytest.raises(CafefFormatError, match="header"):
        parse_archive(z)


def test_parse_archive_rejects_unknown_member():
    with pytest.raises(CafefFormatError, match="unexpected file"):
        parse_archive(make_zip({"readme.txt": "hi"}))


def test_parse_archive_rejects_mixed_variants():
    z = make_zip(
        {
            "CafeF.RAW_HSX.Upto20.11.2026.csv": f"{HEADER}\n",
            "CafeF.HNX.Upto20.11.2026.csv": f"{HEADER}\n",
        }
    )
    with pytest.raises(CafefFormatError, match="mixes"):
        parse_archive(z)


def test_ingest_stores_bytes_unchanged_and_is_idempotent():
    client = client_for(lambda req: httpx.Response(200, content=RAW_ZIP))
    store = InMemoryRawStore()
    [first] = ingest(client, store, [Variant.RAW], as_of=date(2026, 11, 20))
    [again] = ingest(client, store, [Variant.RAW], as_of=date(2026, 11, 20))
    assert first.created and not again.created and first.key == again.key
    assert first.key.startswith("cafef/2026-11-24/CafeF.SolieuGD.Raw.Upto20112026.")
    assert store.get(first.key) == RAW_ZIP
    assert first.metadata["upto_date"] == "2026-11-20"
    assert first.metadata["fetched_at_utc"] == FIXED_NOW.isoformat()


def test_ingest_raises_when_date_missing():
    client = client_for(lambda req: httpx.Response(404))
    with pytest.raises(LookupError):
        ingest(client, InMemoryRawStore(), [Variant.RAW], as_of=date(2026, 11, 22))
