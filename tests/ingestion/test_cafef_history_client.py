import json
from datetime import UTC, date, datetime, timedelta

import httpx
import pytest

from ingestion.market.cafef_history_client import (
    CafefHistoryClient,
    CafefHistoryFormatError,
    HistoryBundle,
    parse_bundle,
)
from ingestion.market.cafef_history_ingest import already_fetched, year_chunks

NOW = datetime(2026, 11, 24, 6, 0, tzinfo=UTC)


def row(day: str, close: float, vol: int = 1000, value: float = 0.02) -> dict:
    return {
        "Symbol": "ACB", "Ngay": day, "GiaDieuChinh": close / 6, "GiaDongCua": close,
        "ThayDoi": "0 (0,00%)", "KhoiLuongKhopLenh": vol, "GiaTriKhopLenh": value,
        "KLThoaThuan": 0, "GtThoaThuan": 0, "GiaMoCua": close, "GiaCaoNhat": close,
        "GiaThapNhat": close,
    }  # fmt: skip


def page(rows: list[dict], total: int) -> bytes:
    return json.dumps(
        {
            "Data": {"TotalCount": total, "Index": "VNINDEX", "Data": rows},
            "Message": None,
            "Success": True,
        }  # fmt: skip
    ).encode()


def client_for(handler) -> CafefHistoryClient:
    http = httpx.Client(transport=httpx.MockTransport(handler))
    return CafefHistoryClient(http, sleep=lambda s: None, now=lambda: NOW)


def test_fetch_range_pages_until_total_and_uses_us_dates():
    seen = []
    days = [date(2015, 6, 1) + timedelta(days=i) for i in range(35)]  # 35 rows -> 2 pages
    rows = [row(f"{d:%d/%m/%Y}", 20 + (i + 1) / 10) for i, d in enumerate(days)]

    def handler(req):
        seen.append(req.url.params)
        p = int(req.url.params["PageIndex"])
        return httpx.Response(200, content=page(rows[(p - 1) * 30 : p * 30], total=35))

    bundle = client_for(handler).fetch_range("ACB", date(2015, 6, 1), date(2015, 7, 31))
    assert len(bundle.pages) == 2 and bundle.total_count == 35
    assert seen[0]["StartDate"] == "06/01/2015" and seen[0]["EndDate"] == "07/31/2015"
    df = parse_bundle(bundle.to_zip())
    assert len(df) == 35
    assert df.iloc[0].trade_date.date() == date(2015, 6, 1)  # dd/mm/yyyy in the payload
    assert df.iloc[0].close == 20.1


def test_empty_range_gives_one_empty_page():
    bundle = client_for(lambda r: httpx.Response(200, content=page([], 0))).fetch_range(
        "HBB", date(2012, 1, 3), date(2012, 8, 16)
    )
    assert bundle.total_count == 0 and len(bundle.pages) == 1
    assert parse_bundle(bundle.to_zip()).empty


def test_zip_is_deterministic_for_same_pages():
    b1 = HistoryBundle("ACB", date(2015, 1, 1), date(2015, 1, 2), [b"a", b"b"], ["u"], 2, NOW)
    b2 = HistoryBundle("ACB", date(2015, 1, 1), date(2015, 1, 2), [b"a", b"b"], ["u"], 2, NOW)
    assert b1.to_zip() == b2.to_zip()


def test_rejects_unsuccessful_or_foreign_payload():
    bad = json.dumps({"Data": None, "Success": False}).encode()
    with pytest.raises(CafefHistoryFormatError):
        client_for(lambda r: httpx.Response(200, content=bad)).fetch_range(
            "ACB", date(2015, 1, 1), date(2015, 1, 2)
        )


def test_total_count_must_not_change_while_paging():
    def handler(req):
        p = int(req.url.params["PageIndex"])
        return httpx.Response(200, content=page([row("01/06/2015", 20)] * 30, total=60 + p))

    with pytest.raises(CafefHistoryFormatError, match="TotalCount changed"):
        client_for(handler).fetch_range("ACB", date(2015, 1, 1), date(2015, 12, 31))


def test_year_chunks():
    assert year_chunks(date(2019, 7, 30), date(2021, 2, 3)) == [
        (date(2019, 7, 30), date(2019, 12, 31)),
        (date(2020, 1, 1), date(2020, 12, 31)),
        (date(2021, 1, 1), date(2021, 2, 3)),
    ]


def test_already_fetched_matches_ticker_and_exact_range():
    keys = ["cafef_history/2026-11-24/ACB_20150101_20151231.abcd1234.zip"]
    assert already_fetched(keys, "ACB", date(2015, 1, 1), date(2015, 12, 31))
    assert not already_fetched(keys, "ACB", date(2016, 1, 1), date(2016, 12, 31))
    assert not already_fetched(keys, "AC", date(2015, 1, 1), date(2015, 12, 31))


def test_exchange_type_is_sent_and_named():
    seen = []

    def handler(req):
        seen.append(req.url.params)
        return httpx.Response(200, content=page([row("03/01/2022", 10)], total=1))

    bundle = client_for(handler).fetch_range("ABB", date(2022, 1, 1), date(2022, 1, 31), "UPCOM")
    assert seen[0]["ExchangeType"] == "UPCOM"
    assert bundle.filename == "ABB_UPCOM_20220101_20220131.zip"
    keys = ["cafef_history/2026-11-24/ABB_20220101_20220131.00000000.zip"]  # old default fetch
    assert not already_fetched(keys, "ABB", date(2022, 1, 1), date(2022, 1, 31), "UPCOM")
    assert already_fetched(keys, "ABB", date(2022, 1, 1), date(2022, 1, 31))
