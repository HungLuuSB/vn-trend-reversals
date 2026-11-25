"""CafeF news crawler: windows, sitemap parsing, timestamps, raw bundles, resume (hand-built)."""

import io
import json
import zipfile
from datetime import date

from vnbank.common.raw_store import InMemoryRawStore
from vnbank.ingestion.news import cafef_news_client as nc
from vnbank.ingestion.news.cafef_news_ingest import crawl


def test_windows_follow_the_sitemap_day_ranges():
    w = list(nc.windows(date(2012, 2, 24), date(2012, 3, 7)))
    assert [(x.month, x.d1, x.d2) for x in w] == [(2, 21, 25), (2, 26, 29), (3, 1, 5), (3, 6, 10)]
    assert w[1].sitemap_url == "https://cafef.vn/sitemaps/sitemaps-2012-2-26-29.xml"


def test_published_at_reads_the_offset_timestamp():
    html = (b'<span class="pdate" data-role="publishdate" itemprop="datePublished" '
            b'datetime="2014-06-10T23:11:12+07:00">10-06-2014</span>')  # fmt: skip
    assert nc.published_at(html) == "2014-06-10T23:11:12+07:00"
    assert nc.published_at(b"<html></html>") is None


SITEMAP = (b'<?xml version="1.0"?><urlset><url><loc>https://cafef.vn/a-1.chn</loc></url>'
           b"<url><loc>https://other.site/x</loc></url>"
           b"<url><loc> https://cafef.vn/b-2.chn </loc></url></urlset>")  # fmt: skip


class FakeHttp:
    def __init__(self):
        self.urls = []

    def get(self, url):
        self.urls.append(url)

        class R:
            status_code = 200 if not url.endswith("b-2.chn") else 404
            content = SITEMAP if url.endswith(".xml") else b"<html>page</html>"

        if "2012-1-6-10" in url:
            R.status_code, R.content = 404, b""
        return R()


def test_crawl_stores_one_zip_per_window_and_resumes():
    http = FakeHttp()
    c = nc.CafefNewsClient(http=http, pause_s=0, sleep=lambda s: None)
    store = InMemoryRawStore()
    st = crawl(c, store, date(2012, 1, 1), date(2012, 1, 10), log=lambda m: None)
    assert st["stored"] == 1 and st["missing_sitemaps"] == ["cafef_news_20120106_10"]
    assert st["pages"] == 2 and st["failed_pages"] == 1
    assert "https://other.site/x" not in http.urls  # only CafeF's own pages
    (key,) = store.keys()
    zf = zipfile.ZipFile(io.BytesIO(store.get(key)))
    idx = json.loads(zf.read("index.json"))
    assert [p["status"] for p in idx["pages"]] == [200, 404]
    assert zf.read("sitemap.xml") == SITEMAP
    again = crawl(c, store, date(2012, 1, 1), date(2012, 1, 5), log=lambda m: None)
    assert again["skipped"] == 1 and again["stored"] == 0


def test_concurrency_increases_when_clean_and_halves_on_pushback():
    def st(lat, n429=0, n5xx=0, conn=0, pages=1000):
        return {"pages": pages, "n429": n429, "n5xx": n5xx, "ntransport": conn,
                "median_latency": lat}  # fmt: skip

    c = nc.Concurrency(start=3, cap=5)
    assert c.update(st(0.2)) == "up" and c.n == 4
    assert c.update(st(0.3, conn=1)) == "up" and c.n == 5  # one blip in 1000 is noise
    assert c.update(st(0.3)) == "hold" and c.n == 5
    assert c.update(st(0.3, n429=1)) == "down" and c.n == 2  # any 429 is pushback
    assert c.update(st(0.3)) == "up" and c.n == 3
    assert c.update(st(0.3, n5xx=4, conn=2)) == "down" and c.n == 1  # 6 > 0.5% of 1000
    assert c.update(st(0.5)) == "down" and c.n == 1  # latency more than doubled


def test_parallel_fetch_keeps_sitemap_order():
    http = FakeHttp()
    c = nc.CafefNewsClient(http=http, pause_s=0, sleep=lambda s: None,
                           concurrency=nc.Concurrency(start=3))  # fmt: skip
    b = c.fetch_window(nc.Window(2012, 1, 1, 5))
    assert [u for u, _, _ in b.pages] == ["https://cafef.vn/a-1.chn", "https://cafef.vn/b-2.chn"]
    assert b.stats["concurrency"] == 3 and b.stats["pages"] == 2


def test_repair_refetches_only_failed_pages_into_a_new_bundle():
    from vnbank.ingestion.news.cafef_news_ingest import repair

    http = FakeHttp()
    c = nc.CafefNewsClient(http=http, pause_s=0, sleep=lambda s: None)
    store = InMemoryRawStore()
    crawl(c, store, date(2012, 1, 1), date(2012, 1, 5), log=lambda m: None)  # b-2 -> 404
    before = set(store.keys())
    http.urls.clear()
    st = repair(c, store, log=lambda m: None)
    assert st["urls"] == 1 and http.urls == ["https://cafef.vn/b-2.chn"]
    new = set(store.keys()) - before
    assert len(new) == 1 and "cafef_news_20120101_05_repair_1." in new.pop()
