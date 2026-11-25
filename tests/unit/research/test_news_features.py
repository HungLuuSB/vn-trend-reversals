"""Block E news features (D-023): windows end at the decision time; relative attention."""

import numpy as np
import pandas as pd
import pytest

from vnbank.research.survival.features.news import (
    add_news_features,
    articles,
    session_counts,
)

SESSIONS = pd.to_datetime(["2015-06-04", "2015-06-05", "2015-06-08", "2015-06-09"])


def _utc(*local):
    return pd.to_datetime(list(local)).tz_localize("Asia/Ho_Chi_Minh").tz_convert("UTC")


def test_counts_use_09_to_09_windows_over_weekends_and_dedupe_urls():
    pub = _utc(
        "2015-06-04 08:59",
        "2015-06-04 09:00",
        "2015-06-05 08:59",  # Thu window: 2
        "2015-06-06 12:00",
        "2015-06-08 08:59",  # Fri window runs to Mon 09:00: 2
        "2015-06-08 09:00",
    )  # Mon window: 1 (exactly 09:00 belongs to Mon)
    m = pd.DataFrame({"url": list("abcdef") + ["a"], "published_at_utc": [*pub, pub[0]],
                      "tickers_strict": [["ACB"]] * 6 + [["ACB"]],
                      "tickers": [["ACB", "MBB"]] * 7})  # fmt: skip
    c = session_counts(articles(m), SESSIONS, ["ACB"])
    assert c.news_count.tolist() == [2, 2, 1]  # last session has no window end
    assert c.news_rel_20.isna().all()  # fewer than 20 earlier sessions
    assert articles(m, "tickers").ticker.value_counts().to_dict() == {"ACB": 6, "MBB": 6}


def test_rel_20_uses_only_previous_sessions():
    cal = pd.bdate_range("2015-01-01", periods=23)
    pub = _utc(*[f"{d:%Y-%m-%d} 10:00" for d in cal[:21]])  # one article a day, then 2
    extra = _utc(f"{cal[21]:%Y-%m-%d} 10:00", f"{cal[21]:%Y-%m-%d} 11:00")
    m = pd.DataFrame({"url": [str(i) for i in range(23)], "published_at_utc": [*pub, *extra],
                      "tickers_strict": [["VCB"]] * 23})  # fmt: skip
    c = session_counts(articles(m), cal, ["VCB"]).set_index("trade_date")
    assert c.loc[cal[21], "news_count"] == 2
    assert c.loc[cal[20], "news_rel_20"] == pytest.approx(0.0)  # 1 vs mean 1
    assert c.loc[cal[21], "news_rel_20"] == pytest.approx(np.log(3 / 2))


def test_join_checks_the_window_ends_at_the_decision_date():
    c = session_counts(articles(pd.DataFrame({"url": ["x"], "published_at_utc": _utc(
        "2015-06-05 10:00"), "tickers_strict": [["ACB"]]})), SESSIONS, ["ACB"])  # fmt: skip
    ds = pd.DataFrame({"ticker": ["ACB", "FPT"], "trade_date": SESSIONS[[1, 1]],
                       "decision_date": SESSIONS[[2, 2]], "is_bank": [True, False]})  # fmt: skip
    out = add_news_features(ds, c)
    assert out.news_count.iloc[0] == 1 and np.isnan(out.news_count.iloc[1])
    with pytest.raises(ValueError):
        add_news_features(ds.assign(decision_date=SESSIONS[[3, 3]]), c)
