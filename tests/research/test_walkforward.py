import numpy as np
import pandas as pd
import pytest

from research.walkforward import EMBARGO_SESSIONS, main, split


def toy():
    sessions = pd.bdate_range("2013-01-01", "2017-03-31").to_numpy()
    rows = []
    for i, d in enumerate(sessions[:-30]):
        dur = 3 + i % 7
        rows.append({"trade_date": d, "end_date": sessions[i + dur], "duration": dur, "event": 1,
                     "days_to_dev_end": int(np.searchsorted(sessions, np.datetime64("2016-12-31"))
                                            - 1 - i)})  # fmt: skip
    return pd.DataFrame(rows), sessions


def test_purge_and_embargo_keep_training_clear_of_the_fold():
    ds, sessions = toy()
    train, val = split(ds, sessions, 2015, dev=True)
    start = pd.Timestamp("2015-01-01")
    assert (train.end_date < start).all()  # purged: no training label reaches the fold
    k = np.searchsorted(sessions, start.to_datetime64())
    assert (train.trade_date < sessions[k - EMBARGO_SESSIONS]).all()  # embargo
    assert val.trade_date.dt.year.eq(2015).all()


def test_dev_validation_never_sees_test_year_prices():
    ds, sessions = toy()
    _, val = split(ds, sessions, 2016, dev=True)
    late = val[val.trade_date > pd.Timestamp("2016-12-15")]
    assert (late.event == 0).any()  # labels reaching 2017 were censored
    ends = val.trade_date.to_numpy()  # durations now stop by 2016-12-31
    last_idx = np.searchsorted(sessions, np.datetime64("2016-12-31")) - 1
    pos = np.searchsorted(sessions, ends)
    assert (pos + val.duration.to_numpy() <= last_idx).all()


def test_final_mode_is_refused():
    with pytest.raises(SystemExit, match="i-confirm-final-run"):
        main(["--features-run", "x", "--final"])
    with pytest.raises(SystemExit, match="reserved for the final run"):
        main(["--features-run", "x", "--final", "--i-confirm-final-run"])
