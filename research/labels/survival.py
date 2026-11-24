"""Survival rows from swing labels (docs/proposal.md Methodology 2; research/DECISIONS.md D-011).

One row per (stock, trading day t) inside a swing not yet confirmed as reversed. The row's
state is as of the close of t (used at the 09:00 decision on the next session). Its target:

    duration = trading days of this stock from t until the swing's reversal is confirmed
               (event = 1), or until it is censored (event = 0) by
                 - the end of the sample (last day <= end_index),
                 - the stock leaving the universe (last consecutive in-universe day),
                 - a halt: a gap of >= HALT_GAP_SESSIONS exchange sessions without a price.
    age        = trading days since the swing's starting extreme (main time scale)
    age_conf   = trading days since the swing became known (its confirmation day)

Rows require >= MIN_HISTORY_DAYS prior trading days of the stock (D-009).
Everything except `duration`, `event`, `censor_reason` is known at the close of t.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from research.labels.directional_change import Labels

HALT_GAP_SESSIONS = 5
MIN_HISTORY_DAYS = 250


def survival_rows(
    labels: Labels,
    session_no: np.ndarray,
    in_universe: np.ndarray,
    end_index: int,
    min_history: int = MIN_HISTORY_DAYS,
    halt_gap: int = HALT_GAP_SESSIONS,
) -> pd.DataFrame:
    """Rows for one stock.

    session_no: exchange session number of each of the stock's trading days (increasing);
                a jump > halt_gap marks a halt between two consecutive trading days.
    in_universe: whether the stock is in the research universe on each trading day.
    end_index: index of the stock's last trading day within the sample (-1 = none).
    """
    n = len(labels.direction)
    session_no = np.asarray(session_no, dtype="int64")
    in_universe = np.asarray(in_universe, dtype=bool)
    if not (len(session_no) == len(in_universe) == n):
        raise ValueError("all inputs must have one entry per trading day")

    # halt_after[t]: a halt starts right after day t (next trading day is > halt_gap sessions on)
    halt_after = np.zeros(n, dtype=bool)
    halt_after[:-1] = np.diff(session_no) - 1 >= halt_gap

    # last index of the run (no halt, all in universe) that contains t
    run_end = np.full(n, -1, dtype=np.int64)
    run_reason = np.empty(n, dtype=object)
    nxt, reason = -1, ""
    for t in range(n - 1, -1, -1):
        if not in_universe[t]:
            nxt, reason = -1, ""
            continue
        if t == n - 1 or not in_universe[t + 1]:
            nxt, reason = t, ("universe_exit" if t < n - 1 else "data_end")
        elif halt_after[t]:
            nxt, reason = t, "halt"
        run_end[t], run_reason[t] = nxt, reason

    rows = []
    for t in range(n):
        if t > end_index or labels.direction[t] == 0 or not in_universe[t] or t < min_history:
            continue
        cens = run_end[t]
        reason = run_reason[t]
        if cens >= end_index:
            # reaching the sample end is "end_of_sample" even when the stock's data also ends
            # there; "data_end" is kept for stocks whose price history stops earlier
            cens, reason = end_index, "end_of_sample"
        ev = labels.next_confirm_index[t]
        if ev != -1 and ev <= cens:
            duration, event, reason = ev - t, 1, ""
        else:
            duration, event = cens - t, 0
            if duration == 0:
                continue  # censored on the row's own day: no time at risk
        rows.append(
            (
                t,
                int(labels.direction[t]),
                int(t - labels.swing_start_index[t]),
                int(t - labels.swing_confirm_index[t]),
                float(labels.theta[t]),
                float(labels.running_extreme[t]),
                int(duration),
                event,
                reason,
            )
        )
    return pd.DataFrame(
        rows,
        columns=[
            "index",
            "direction",
            "age",
            "age_conf",
            "theta",
            "running_extreme",
            "duration",
            "event",
            "censor_reason",
        ],
    )
