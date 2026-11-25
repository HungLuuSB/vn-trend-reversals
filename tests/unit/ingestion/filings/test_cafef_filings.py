"""CafeF filings: list parsing, PDF host fix, raw storage, resume (hand-built replies)."""

import json

import pytest

from vnbank.common.raw_store import InMemoryRawStore
from vnbank.ingestion.filings import cafef_filings_client as fc
from vnbank.ingestion.filings.cafef_filings_ingest import ingest

LINK = "https://cafefnew.mediacdn.vn/Images/Uploaded/DuLieuDownload/2013/VCB_13Q3_BCTC_HN.pdf"
LIST = json.dumps({"Data": [{"Type": 0, "Quarter": 3, "Year": 2013, "Time": "Q3/2013",
                             "Name": "Báo cáo tài chính hợp nhất quý 3 năm 2013", "Link": LINK}],
                   "Message": None, "Success": True}).encode()  # fmt: skip


def test_parse_list_and_pdf_host():
    (f,) = fc.parse_list("VCB", 2013, LIST)
    assert (f.quarter, f.period, f.filename) == (3, "Q3/2013", "VCB_13Q3_BCTC_HN.pdf")
    assert f.pdf_url.startswith("https://cafef1.mediacdn.vn/Images/Uploaded/")


@pytest.mark.parametrize("body", [b"<html>", b'{"Data": [], "Success": false}'])
def test_parse_list_rejects_unexpected_payloads(body):
    with pytest.raises(fc.FilingsFormatError):
        fc.parse_list("VCB", 2013, body)


class FakeHttp:
    def __init__(self):
        self.calls = []

    def get(self, url, params=None):
        self.calls.append((url, params))

        class R:
            status_code = 200
            content = LIST if params else b"%PDF-1.4 fake"

        return R()


def test_ingest_stores_list_and_pdf_then_resumes():
    http = FakeHttp()
    c = fc.CafefFilingsClient(http=http, pause_s=0, sleep=lambda s: None)
    store = InMemoryRawStore()
    st = ingest(c, store, ["vcb"], [2013], log=lambda m: None)
    assert st == {"lists": 1, "pdfs": 1, "skipped": 0, "failed": [], "empty": []}
    assert http.calls[0][1]["Symbol"] == "VCB"  # upper case
    keys = store.keys()
    assert any("list_VCB_2013." in k for k in keys) and any("VCB_13Q3_BCTC_HN." in k for k in keys)
    st2 = ingest(c, store, ["VCB"], [2013], log=lambda m: None)
    assert st2["pdfs"] == 0 and st2["skipped"] == 1


def test_archives_are_accepted_and_other_bodies_rejected():
    f = fc.Filing("EIB", 2012, 1, "Q1/2012", "x", LINK.replace("VCB_13Q3_BCTC_HN.pdf",
                                                              "EIB_12Q1_BCTC_HN.rar"))  # fmt: skip

    class H:
        def __init__(self, body):
            self.body = body

        def get(self, url, params=None):
            body = self.body

            class R:
                status_code = 200
                content = body

            return R()

    for body, ok in ((b"Rar!\x1a\x07\x00x", True), (b"PK\x03\x04x", True),
                     (b"<html>404</html>", False)):  # fmt: skip
        c = fc.CafefFilingsClient(http=H(body), pause_s=0, sleep=lambda s: None)
        assert (c.pdf(f)[0] == 200) is ok


class FlakyHttp(FakeHttp):
    """Answers an empty list `empties` times, then the real one."""

    def __init__(self, empties):
        super().__init__()
        self.empties = empties

    def get(self, url, params=None):
        if params and self.empties > 0:
            self.empties -= 1
            self.calls.append((url, params))

            class R:
                status_code = 200
                content = b'{"Data": [], "Message": null, "Success": true}'

            return R()
        return super().get(url, params)


def test_empty_list_is_retried_then_reported():
    c = fc.CafefFilingsClient(http=FlakyHttp(2), pause_s=0, sleep=lambda s: None)
    st = ingest(c, InMemoryRawStore(), ["BID"], [2015], log=lambda m: None)
    assert st["lists"] == 3 and st["pdfs"] == 1 and st["empty"] == []
    c = fc.CafefFilingsClient(http=FlakyHttp(99), pause_s=0, sleep=lambda s: None)
    st = ingest(c, InMemoryRawStore(), ["BID"], [2015], log=lambda m: None)
    assert st["empty"] == ["BID 2015"] and st["pdfs"] == 0
