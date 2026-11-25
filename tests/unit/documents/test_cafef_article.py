"""CafeF article parsing and bank-mention matching on hand-built HTML."""

import io
import json
import zipfile
from datetime import UTC, datetime

from vnbank.documents.news.cafef_article import (
    alias_patterns,
    iter_bundle,
    mentions,
    parse_article,
)

HTML = """<html><head><script>var x = "Vietcombank";</script></head><body>
<h1 class="title" data-role="title">VCB lãi lớn trong quý 3</h1>
<span class="pdate" data-role="publishdate" itemprop="datePublished"
 datetime="2014-06-10T23:11:12+07:00">10-06-2014</span>
<h2 class="sapo">Ngân hàng TMCP Ngoại thương Việt Nam công bố kết quả.</h2>
<div class="detail-content afcbc-body"><p>Lợi nhuận của <b>Vietcombank</b> tăng.</p>
<div class="inner"><p>So với ACB và MBBank.</p></div><br></div>
<div class="related">Sacombank related link</div></body></html>""".encode()


def test_parse_article_fields_and_timezone():
    a = parse_article("https://cafef.vn/x.chn", HTML)
    assert a.title == "VCB lãi lớn trong quý 3"
    assert a.sapo.startswith("Ngân hàng TMCP Ngoại thương")
    assert "Vietcombank tăng" in a.body and "So với ACB" in a.body
    assert "Sacombank" not in a.text  # outside the article body
    assert a.published_at == datetime(2014, 6, 10, 16, 11, 12, tzinfo=UTC)


ALIASES = [("VCB", "VCB"), ("VCB", "Vietcombank"),
           ("VCB", "Ngân hàng TMCP Ngoại thương Việt Nam"), ("ACB", "ACB"),
           ("MBB", "MB"), ("STB", "Sacombank"), ("SHB", "SHB")]  # fmt: skip


def test_mentions_whole_words_and_case():
    pats = alias_patterns(ALIASES)
    a = parse_article("u", HTML)
    assert mentions(a.text, pats) == {"VCB", "ACB"}  # "MBBank" is not the word "MB"
    assert mentions("ngân hàng tmcp ngoại thương việt nam", pats) == {"VCB"}  # Vietnamese: any case
    assert mentions("acb and shb", pats) == set()  # tickers: case-sensitive
    assert mentions("SHB-ACB merger", pats) == {"SHB", "ACB"}


def test_iter_bundle_skips_failed_pages():
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("p00000.html", HTML)
        zf.writestr("p00001.html", b"")
        zf.writestr("index.json", json.dumps({"pages": [
            {"member": "p00000.html", "url": "u0", "status": 200},
            {"member": "p00001.html", "url": "u1", "status": 404}]}))  # fmt: skip
    arts = list(iter_bundle(buf.getvalue()))
    assert [a.url for a in arts] == ["u0"]


def test_bundle_rows_strict_excludes_ambiguous_aliases():
    from vnbank.documents.news.extract_mentions import bundle_rows

    html = HTML.replace("So với ACB và MBBank.".encode(), "Cổ phiếu MB tăng.".encode())
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("p0.html", html)
        zf.writestr("index.json", json.dumps({"pages": [
            {"member": "p0.html", "url": "u0", "status": 200}]}))  # fmt: skip
    pats_all = alias_patterns(ALIASES)
    pats_strict = alias_patterns([x for x in ALIASES if x[1] != "MB"])
    df = bundle_rows(buf.getvalue(), pats_all, pats_strict)
    assert df.tickers.iloc[0] == ["MBB", "VCB"] and df.tickers_strict.iloc[0] == ["VCB"]
    assert str(df.published_at_utc.iloc[0]) == "2014-06-10 16:11:12+00:00"


def test_bundle_rows_of_an_empty_bundle_keep_their_columns():
    from vnbank.documents.news.extract_mentions import COLUMNS, bundle_rows

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:  # a repair bundle in which every page failed again
        zf.writestr("index.json", json.dumps({"pages": [{"url": "u0", "status": 404}]}))
    df = bundle_rows(buf.getvalue(), alias_patterns(ALIASES), alias_patterns(ALIASES))
    assert len(df) == 0 and list(df.columns) == COLUMNS
    assert df.tickers.map(len).gt(0).sum() == 0
