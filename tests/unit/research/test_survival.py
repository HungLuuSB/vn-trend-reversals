import numpy as np

from tests.unit.research.test_directional_change import unit_steps
from vnbank.research.swings.directional_change import label_series
from vnbank.research.swings.risk_set import survival_rows

# The known series: flat 100 (25 days), up +1/day to 120, then a one-day drop to 100.
PATH = [100.0] * 25 + [100.0 + i for i in range(1, 21)] + [100.0]
LAB = label_series(*unit_steps(PATH), k=2.0)
N = len(PATH)
CONF_UP = PATH.index(104.0)  # up-swing confirmed (became known)
PEAK = PATH.index(120.0)
DROP = N - 1  # reversal confirmed


def rows(**kw):
    args = dict(
        labels=LAB,
        session_no=np.arange(N),
        in_universe=np.ones(N, dtype=bool),
        end_index=N - 1,
        min_history=0,
    )
    args.update(kw)
    return survival_rows(**args)


def test_event_rows_run_from_confirmation_to_day_before_reversal():
    df = rows()
    up = df[df.direction == 1]
    assert up["index"].min() == CONF_UP and up["index"].max() == DROP - 1
    assert (up.event == 1).all()
    assert (up["index"] + up.duration == DROP).all()  # duration counts to the confirmation
    first = up.iloc[0]
    assert first.age == CONF_UP - 21 and first.age_conf == 0  # delayed entry at age > 0


def test_end_of_sample_censors():
    df = rows(end_index=PEAK)
    up = df[df.direction == 1]
    assert up["index"].max() == PEAK - 1  # censored on its own day -> no row
    assert (up.event == 0).all() and set(up.censor_reason) == {"end_of_sample"}
    assert (up["index"] + up.duration == PEAK).all()


def test_universe_exit_censors_and_reentry_starts_new_rows():
    inu = np.ones(N, dtype=bool)
    inu[35:38] = False
    df = rows(in_universe=inu)
    before = df[(df["index"] < 35) & (df.direction == 1)]
    assert (before.event == 0).all() and set(before.censor_reason) == {"universe_exit"}
    assert (before["index"] + before.duration == 34).all()
    after = df[(df["index"] >= 38) & (df.direction == 1)]
    assert (after.event == 1).all() and after["index"].min() == 38


def test_halt_gap_censors_but_short_gaps_do_not():
    s = np.arange(N)
    s[40:] += 5  # 5 missing sessions between trading days 39 and 40 -> halt
    df = rows(session_no=s)
    assert set(df[(df["index"] < 40) & (df.direction == 1)].censor_reason) == {"halt"}
    s2 = np.arange(N)
    s2[40:] += 4  # 4 missing sessions: days without trades, the swing continues
    df2 = rows(session_no=s2)
    assert (df2[df2.direction == 1].event == 1).all()


def test_min_history_excludes_early_days():
    df = rows(min_history=40)
    assert df["index"].min() == 40


def test_only_targets_use_the_future():
    # state columns on day t must match a run on data truncated at t
    t = PEAK
    full = rows().set_index("index").loc[t]
    lab_cut = label_series(*unit_steps(PATH[: t + 1]), k=2.0)
    assert lab_cut.direction[t] == full.direction
    assert t - lab_cut.swing_start_index[t] == full.age
    assert lab_cut.running_extreme[t] == full.running_extreme


def test_reaching_sample_end_is_end_of_sample_and_early_data_stop_is_data_end():
    # sample end == last trading day: censoring there is end_of_sample, not data_end
    df = rows(labels=label_series(*unit_steps(PATH[:PEAK + 1]), k=2.0),
              session_no=np.arange(PEAK + 1), in_universe=np.ones(PEAK + 1, dtype=bool),
              end_index=PEAK)  # fmt: skip
    assert set(df[df.event == 0].censor_reason) == {"end_of_sample"}
    # a stock whose data stops before the sample end (e.g. delisted): data_end
    lab = label_series(*unit_steps(PATH[: PEAK + 1]), k=2.0)
    df2 = survival_rows(lab, np.arange(PEAK + 1), np.ones(PEAK + 1, dtype=bool),
                        end_index=PEAK + 100, min_history=0)  # fmt: skip
    assert set(df2[df2.event == 0].censor_reason) == {"data_end"}
