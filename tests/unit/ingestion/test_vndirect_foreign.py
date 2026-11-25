"""VNDirect foreign flows (P2-018): parsing, paging, raw storage, resume (hand-built replies)."""

import json
from datetime import date

import pytest

from vnbank.common.raw_store import InMemoryRawStore
from vnbank.ingestion.market import vndirect_foreign_client as vc
from vnbank.ingestion.market.vndirect_foreign_ingest import ingest, stored


def _reply(rows, page=1, total=1):
    return json.dumps({"data": rows, "currentPage": page, "size": 500, "totalElements": len(rows),
                       "totalPages": total}).encode()  # fmt: skip


ROW = {"code": "VNINDEX", "type": "INDEX", "tradingDate": "2018-08-30", "floor": "HOSE",
       "buyVal": 9.2e11, "sellVal": 9.4e11, "netVal": -1.5e10, "buyVol": 1.96e7,
       "sellVol": 2.21e7, "netVol": -2.56e6}  # fmt: skip


def test_parse_reply_and_reject_other_payloads():
    df, total = vc.parse(_reply([ROW]))
    assert total == 1 and df.tradingDate.iloc[0] == date(2018, 8, 30)
    assert df.netVal.iloc[0] == pytest.approx(-1.5e10)
    for bad in (b"<html>", b'{"data": "x", "totalPages": 1}', json.dumps(
            {"data": [{"code": "X"}], "totalPages": 1}).encode()):  # fmt: skip
        with pytest.raises(vc.ForeignFormatError):
            vc.parse(bad)


class FakeHttp:
    def __init__(self, pages=1):
        self.calls, self.pages = [], pages

    def get(self, url, params=None):
        self.calls.append(params)
        p = int(params["page"])
        body = _reply([dict(ROW, tradingDate=f"2018-09-0{p}")], page=p, total=self.pages)

        class R:
            status_code = 200
            content = body

        return R()


def test_fetch_follows_pages_and_query_format():
    http = FakeHttp(pages=2)
    c = vc.VndirectForeignClient(http=http, pause_s=0, sleep=lambda s: None)
    pages = c.fetch("VCB", date(2018, 8, 30), date(2018, 12, 31))
    assert [p.page for p in pages] == [1, 2] and len(http.calls) == 2
    assert http.calls[0]["q"] == "code:VCB~tradingDate:gte:2018-08-30~tradingDate:lte:2018-12-31"


def test_ingest_stores_raw_pages_resumes_and_refetches_current_year():
    http = FakeHttp()
    c = vc.VndirectForeignClient(http=http, pause_s=0, sleep=lambda s: None)
    store = InMemoryRawStore()
    st = ingest(c, store, ["VNINDEX"], [2017, 2018, 2026], today=date(2026, 11, 25),
                log=lambda m: None)  # fmt: skip
    # 2017 is before the first date (no request); 2018 starts at 2018-08-30
    assert st["requests"] == 2 and st["pages"] == 2
    assert http.calls[0]["q"].startswith("code:VNINDEX~tradingDate:gte:2018-08-30")
    assert http.calls[1]["q"].endswith("tradingDate:lte:2026-11-25")
    assert stored(store) == {("VNINDEX", 2018), ("VNINDEX", 2026)}
    st2 = ingest(c, store, ["VNINDEX"], [2018, 2026], today=date(2026, 11, 25), log=lambda m: None)
    assert st2["skipped"] == 1 and st2["requests"] == 1  # the current year is fetched again
