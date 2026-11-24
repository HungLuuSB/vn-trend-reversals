import io
import json
from datetime import UTC, date, datetime

import pandas as pd
import pytest

from ingestion.global_markets.ingest import parse, read_seed
from ingestion.global_markets.sources import SourceFormatError, parse_fred_csv, parse_gpr_dta
from ingestion.market.yahoo_client import parse_quotes


def test_seed_lists_every_proposal_series_once():
    seed = read_seed()
    ids = [r["series_id"] for r in seed]
    assert len(ids) == len(set(ids))
    # D-009: replacements for look-ahead-prone FRED series
    sym = {r["series_id"]: (r["source"], r["symbol"]) for r in seed}
    assert sym["brent"] == ("yahoo", "BZ=F") and sym["usdcny"] == ("yahoo", "CNY=X")
    assert sym["ust10"] == ("fred", "DGS10")
    assert {r["availability_rule"] for r in seed} <= {"close", "next_day_midnight", "gpr_weekly"}


def test_fred_csv_drops_missing_and_checks_header():
    csv = b"observation_date,DGS10\n2026-11-19,4.90\n2026-11-20,.\n2026-11-21,4.92\n"
    df = parse_fred_csv(csv, "DGS10")
    assert df.obs_date.tolist() == [date(2026, 11, 19), date(2026, 11, 21)]
    assert df.value.tolist() == [4.90, 4.92]
    with pytest.raises(SourceFormatError):
        parse_fred_csv(b"date,value\n2026-11-19,1\n", "DGS10")


def test_gpr_parser_keeps_series_and_drops_hindsight_event_labels():
    src = pd.DataFrame(
        {
            "DAY": ["20261120", "20261121"],
            "GPRD": [140.0, 111.0],
            "GPRD_ACT": [97.7, 136.2],
            "GPRD_THREAT": [186.4, 99.4],
            "event": ["", "some labelled event"],
        }
    )
    buf = io.BytesIO()
    src.to_stata(buf, write_index=False)
    df = parse_gpr_dta(buf.getvalue())
    assert set(df.symbol) == {"GPRD", "GPRD_ACT", "GPRD_THREAT"}
    assert "event" not in df.columns and len(df) == 6
    assert df[df.symbol == "GPRD"].value.tolist() == [140.0, 111.0]


def chart(stamps, closes, tz="America/New_York"):
    return json.dumps(
        {
            "chart": {
                "error": None,
                "result": [
                    {
                        "meta": {"symbol": "^GSPC", "exchangeTimezoneName": tz},
                        "timestamp": stamps,
                        "indicators": {
                            "quote": [
                                {
                                    "open": closes,
                                    "high": closes,
                                    "low": closes,
                                    "close": closes,
                                    "volume": [1] * len(stamps),
                                }
                            ],
                            "adjclose": [{"adjclose": [c * 0.5 if c else None for c in closes]}],
                        },
                    }
                ],
            }
        }  # fmt: skip
    ).encode()


def test_yahoo_quotes_use_exchange_local_date_raw_close_and_drop_null_bars():
    # 09:30 New York on 2026-03-06 (EST) and 2026-03-09 (EDT: DST began 2026-03-08)
    t1 = int(datetime(2026, 3, 6, 14, 30, tzinfo=UTC).timestamp())
    t2 = int(datetime(2026, 3, 9, 13, 30, tzinfo=UTC).timestamp())
    t3 = int(datetime(2026, 3, 10, 13, 30, tzinfo=UTC).timestamp())
    df = parse_quotes(chart([t1, t2, t3], [100.0, 101.0, None]))
    assert df.obs_date.tolist() == [date(2026, 3, 6), date(2026, 3, 9)]
    assert df.close.tolist() == [100.0, 101.0]  # raw close, not adjclose (rule 7)


def test_parse_dispatch_puts_fred_value_in_close():
    df = parse("fred", "VIXCLS", b"observation_date,VIXCLS\n2026-11-20,35.89\n")
    assert df.close.tolist() == [35.89] and df.open.isna().all()
