"""Block E fundamentals (D-023): first-release choice, publication time, point-in-time join."""

from datetime import date

import numpy as np
import pandas as pd

from vnbank.research.survival.features.fundamentals import (
    add_npl_features,
    available_at,
    first_release,
    quarter_end,
    quarterly_values,
)


def test_quarter_end():
    assert [quarter_end(2015, q) for q in (1, 2, 3, 4)] == [
        date(2015, 3, 31), date(2015, 6, 30), date(2015, 9, 30), date(2015, 12, 31)]  # fmt: skip


def test_first_release_precedence():
    docs = pd.DataFrame(
        [
            ("ACB", 2015, "Q2", "HNSX"),
            ("ACB", 2015, "Q2", "HN"),
            ("ACB", 2015, "Q2", "M"),
            ("ACB", 2015, "Q3", "M"),  # no consolidated statement: parent-only stands in
            ("ACB", 2015, "Q1", "HNSX"),  # HNSX only stands in for Q2: Q1 has no document
            ("ACB", 2015, "CN", "HNKT"),
            ("ACB", 2015, "Q4", "M"),  # audited consolidated beats M
        ],
        columns=["symbol", "year", "period", "kind"],
    ).assign(raw_key=lambda d: d.index.astype(str))
    fr = first_release(docs)
    assert dict(zip(fr.q, fr.kind, strict=True)) == {2: "HN", 3: "M", 4: "HNKT"}


SESSIONS = pd.bdate_range("2015-04-01", "2015-07-31").to_numpy()  # weekdays as sessions


def test_available_at_is_5th_session_after_later_of_deadline_and_creation():
    # Q1/2015 HN: deadline 2015-05-15 (Fri). Sessions after: 18,19,20,21,22 May -> 22 May 09:00
    t = available_at(2015, 1, "HN", None, SESSIONS)
    assert t == pd.Timestamp("2015-05-22 09:00", tz="Asia/Ho_Chi_Minh")
    # created after the deadline (Wed 2015-05-20): 21,22,25,26,27 -> 27 May
    t = available_at(2015, 1, "HN", date(2015, 5, 20), SESSIONS)
    assert t == pd.Timestamp("2015-05-27 09:00", tz="Asia/Ho_Chi_Minh")
    # created before the deadline changes nothing; margin 0 = first session after
    assert available_at(2015, 1, "HN", date(2015, 4, 20), SESSIONS, margin=0) == pd.Timestamp(
        "2015-05-18 09:00", tz="Asia/Ho_Chi_Minh")  # fmt: skip


def test_npl_features_strictly_before_decision_time_and_bank_rows_only():
    fr = pd.DataFrame({"symbol": ["ACB", "ACB"], "year": [2014, 2015], "q": [4, 1],
                       "kind": ["HN", "HN"], "npl_ratio": [0.020, 0.025],
                       "created": [None, None]})  # fmt: skip
    vals = quarterly_values(fr, pd.bdate_range("2015-01-01", "2015-07-31").to_numpy())
    # Q4/2014 HN deadline 2015-02-14 -> 5th session after: 2015-02-20; Q1/2015 -> 2015-05-22
    ds = pd.DataFrame({
        "ticker": ["ACB", "ACB", "ACB", "ACB", "FPT"],
        # decision 09:00 on 2015-05-22 equals available_at: not yet usable; next day is
        "decision_date": pd.to_datetime(["2015-02-19", "2015-05-21", "2015-05-22", "2015-05-25",
                                         "2015-05-25"]),
        "is_bank": [True, True, True, True, False],
    })  # fmt: skip
    out = add_npl_features(ds, vals)
    assert np.isnan(out.npl_ratio.iloc[0])  # nothing public yet
    assert out.npl_ratio.tolist()[1:4] == [0.020, 0.020, 0.025]
    assert np.isnan(out.npl_change.iloc[2]) and np.isclose(out.npl_change.iloc[3], 0.005)
    assert np.isnan(out.npl_ratio.iloc[4])  # not a bank
