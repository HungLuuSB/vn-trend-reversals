"""Directional-change swing labeller (docs/proposals/paper1-trend-reversals.md Methodology 1;
research/DECISIONS.md D-011).

For one stock's daily adjusted prices, in order:

    TR_t      = max(H_t, C_{t-1}) - min(L_t, C_{t-1})
    ATR20_t   = mean(TR_{t-19..t})
    theta_t   = k * ATR20_{t-1} / C_{t-1}                     (trailing only)

An up-swing with running maximum close M (since its starting trough) is confirmed reversed on
the first day t with C_t <= M * (1 - theta_t); a down-swing mirrors this with the running
minimum m: C_t >= m * (1 + theta_t). The day of the extreme becomes the next swing's start.

Causality: everything known on day t (theta, running extreme, confirmed reversals) depends
only on prices up to t. `label_series(prices[:n])` therefore gives the same confirmed events
and states for the first n days as the full series; tests check this (truncation invariance).
The only forward-looking output is `next_confirm_index`, used to build survival TARGETS.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

UP, DOWN = 1, -1
ATR_WINDOW = 20


@dataclass(frozen=True)
class Reversal:
    confirm_index: int  # day the reversal is confirmed (close of that day)
    extreme_index: int  # day of the extreme the reversed swing ended at
    extreme_price: float
    ended_direction: int  # direction of the swing that ended (UP: a peak, DOWN: a trough)


@dataclass(frozen=True)
class Labels:
    theta: np.ndarray  # threshold used on day t (nan before it exists)
    direction: np.ndarray  # direction of the swing in force after the close of t (0 = none yet)
    swing_start_index: np.ndarray  # index of the starting extreme of that swing (-1 = none)
    swing_confirm_index: np.ndarray  # index where that swing was confirmed (became known)
    running_extreme: np.ndarray  # running max (up) / min (down) since the swing's start, at t
    reversals: list[Reversal]
    next_confirm_index: np.ndarray  # FUTURE: index where the current swing ends (-1 = never)


def true_range(high: np.ndarray, low: np.ndarray, close: np.ndarray) -> np.ndarray:
    tr = np.full(close.shape, np.nan)
    prev = close[:-1]
    tr[1:] = np.maximum(high[1:], prev) - np.minimum(low[1:], prev)
    return tr


def atr20(high: np.ndarray, low: np.ndarray, close: np.ndarray) -> np.ndarray:
    tr = true_range(high, low, close)
    out = np.full(close.shape, np.nan)
    for t in range(ATR_WINDOW, len(close)):
        out[t] = tr[t - ATR_WINDOW + 1 : t + 1].mean()
    return out


def thresholds(high, low, close, k: float) -> np.ndarray:
    a = atr20(high, low, close)
    theta = np.full(close.shape, np.nan)
    theta[1:] = k * a[:-1] / close[:-1]
    return theta


def label_series(high, low, close, k: float = 2.0) -> Labels:
    high, low, close = (np.asarray(x, dtype="float64") for x in (high, low, close))
    n = len(close)
    if not (len(high) == len(low) == n):
        raise ValueError("high, low and close must have the same length")
    if np.any(~np.isfinite(close)) or np.any(close <= 0):
        raise ValueError("close must be finite and positive")
    theta = thresholds(high, low, close, k)

    direction = np.zeros(n, dtype=np.int8)
    start_idx = np.full(n, -1, dtype=np.int64)
    conf_idx = np.full(n, -1, dtype=np.int64)
    extreme = np.full(n, np.nan)
    reversals: list[Reversal] = []

    cur_dir = 0
    cur_start = cur_conf = -1
    # running extremes: before the first swing both are tracked; afterwards only the one of
    # the swing in force (max for UP, min for DOWN)
    run_max = run_min = np.nan
    run_max_i = run_min_i = -1

    for t in range(n):
        c = close[t]
        th = theta[t]
        if cur_dir == 0:
            if np.isnan(th):
                continue  # no threshold yet: nothing is tracked
            if np.isnan(run_max):
                run_max = run_min = c
                run_max_i = run_min_i = t
            else:
                if c > run_max:
                    run_max, run_max_i = c, t
                if c < run_min:
                    run_min, run_min_i = c, t
                # first confirmation in either direction starts the first swing
                if c <= run_max * (1 - th) and run_max_i < t:
                    reversals.append(Reversal(t, run_max_i, run_max, UP))
                    cur_dir, cur_start, cur_conf = DOWN, run_max_i, t
                    run_min, run_min_i = _min_from(close, run_max_i, t)
                elif c >= run_min * (1 + th) and run_min_i < t:
                    reversals.append(Reversal(t, run_min_i, run_min, DOWN))
                    cur_dir, cur_start, cur_conf = UP, run_min_i, t
                    run_max, run_max_i = _max_from(close, run_min_i, t)
        elif cur_dir == UP:
            if c > run_max:
                run_max, run_max_i = c, t
            elif c <= run_max * (1 - th):
                reversals.append(Reversal(t, run_max_i, run_max, UP))
                cur_dir, cur_start, cur_conf = DOWN, run_max_i, t
                run_min, run_min_i = _min_from(close, run_max_i, t)
        else:  # DOWN
            if c < run_min:
                run_min, run_min_i = c, t
            elif c >= run_min * (1 + th):
                reversals.append(Reversal(t, run_min_i, run_min, DOWN))
                cur_dir, cur_start, cur_conf = UP, run_min_i, t
                run_max, run_max_i = _max_from(close, run_min_i, t)

        direction[t] = cur_dir
        start_idx[t] = cur_start
        conf_idx[t] = cur_conf
        if cur_dir == UP:
            extreme[t] = run_max
        elif cur_dir == DOWN:
            extreme[t] = run_min

    # FUTURE information, for targets only: when does the swing in force on day t end?
    next_conf = np.full(n, -1, dtype=np.int64)
    conf_days = [r.confirm_index for r in reversals]
    j = 0
    for t in range(n):
        while j < len(conf_days) and conf_days[j] <= t:
            j += 1
        if direction[t] != 0 and j < len(conf_days):
            next_conf[t] = conf_days[j]
    return Labels(theta, direction, start_idx, conf_idx, extreme, reversals, next_conf)


def _max_from(close: np.ndarray, i0: int, t: int) -> tuple[float, int]:
    seg = close[i0 : t + 1]
    j = int(np.argmax(seg))
    return float(seg[j]), i0 + j


def _min_from(close: np.ndarray, i0: int, t: int) -> tuple[float, int]:
    seg = close[i0 : t + 1]
    j = int(np.argmin(seg))
    return float(seg[j]), i0 + j
