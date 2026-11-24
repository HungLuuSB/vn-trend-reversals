import json
from datetime import UTC, date, datetime

import httpx
import pytest

from vnbank.ingestion.market.yahoo_client import YahooChartClient, YahooFormatError, parse_events

# 09:00 Asia/Ho_Chi_Minh on 2023-07-25 and 2026-07-23 (Yahoo stamps events at the open).
TS_SPLIT = int(datetime(2023, 7, 25, 2, 0, tzinfo=UTC).timestamp())
TS_DIV = int(datetime(2026, 7, 23, 2, 0, tzinfo=UTC).timestamp())
TS_FIRST = int(datetime(2010, 2, 22, 2, 0, tzinfo=UTC).timestamp())
TS_LAST = int(datetime(2026, 11, 20, 2, 0, tzinfo=UTC).timestamp())


def payload(events=None, error=None, stamps=(TS_FIRST, TS_LAST)) -> bytes:
    if error:
        return json.dumps({"chart": {"result": None, "error": {"code": "Not Found"}}}).encode()
    result = {
        "meta": {"symbol": "VCB.VN", "currency": "VND", "exchangeTimezoneName": "Asia/Bangkok"},
        "timestamp": list(stamps),
        "indicators": {"quote": [{}]},
    }
    if events is not None:
        result["events"] = events
    return json.dumps({"chart": {"result": [result], "error": None}}).encode()


EVENTS = {
    "splits": {str(TS_SPLIT): {"numerator": 1181.0, "denominator": 1000.0}},
    "dividends": {str(TS_DIV): {"amount": 450.0}},
}


def test_parse_events_dates_are_local_ex_dates():
    df = parse_events(payload(EVENTS))
    assert df.event_type.tolist() == ["split", "dividend"]
    split, div = df.iloc[0], df.iloc[1]
    assert split.ex_date == date(2023, 7, 25)
    assert (split.numerator, split.denominator) == (1181.0, 1000.0)
    assert div.ex_date == date(2026, 7, 23) and div.amount == 450.0
    assert (df.data_first_date == date(2010, 2, 22)).all()
    assert (df.data_last_date == date(2026, 11, 20)).all()


def test_symbol_without_events_keeps_a_coverage_row():
    df = parse_events(payload(events=None))
    assert df.event_type.tolist() == ["none"]
    assert df.iloc[0].data_first_date == date(2010, 2, 22)


def test_error_payload_yields_no_rows():
    assert parse_events(payload(error=True)).empty


def client_for(handler, **kw):
    http = httpx.Client(transport=httpx.MockTransport(handler))
    return YahooChartClient(http, sleep=lambda s: None, **kw)


def test_fetch_retries_rate_limit_then_succeeds():
    calls = []

    def handler(req):
        calls.append(req)
        return (
            httpx.Response(429) if len(calls) == 1 else httpx.Response(200, content=payload(EVENTS))
        )

    chart = client_for(handler).fetch_chart("VCB.VN", date(2000, 1, 1), date(2026, 11, 24))
    assert len(calls) == 2 and chart.content == payload(EVENTS)
    assert calls[1].url.params["events"] == "div|split"


def test_fetch_returns_none_on_404():
    client = client_for(lambda req: httpx.Response(404))
    assert client.fetch_chart("XXX.VN", date(2000, 1, 1), date(2026, 1, 1)) is None


def test_fetch_rejects_non_chart_body():
    client = client_for(lambda req: httpx.Response(200, content=b"<html>consent</html>"))
    with pytest.raises(YahooFormatError):
        client.fetch_chart("VCB.VN", date(2000, 1, 1), date(2026, 1, 1))


def test_requests_are_paced():
    clock = iter([0.0, 0.2, 1.5])  # first call at 0.0; second asks at 0.2, resumes at 1.5
    slept = []
    http = httpx.Client(
        transport=httpx.MockTransport(lambda r: httpx.Response(200, content=payload()))
    )
    client = YahooChartClient(
        http, sleep=slept.append, monotonic=lambda: next(clock), min_interval_seconds=1.5
    )
    client.fetch_chart("A.VN", date(2000, 1, 1), date(2026, 1, 1))
    client.fetch_chart("B.VN", date(2000, 1, 1), date(2026, 1, 1))
    assert slept == [pytest.approx(1.3)]
