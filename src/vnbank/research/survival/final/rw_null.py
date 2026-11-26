"""Model-free random-walk null for "beyond the mechanics" (D-027 item 1).

For a survival row (stock, t) the directional-change labeller (D-011) is rolled forward from
its exact state after the close of t: direction, running extreme, close, and the last 20 true
ranges (so theta is recomputed every simulated day from the simulated ATR20). Each simulated
day is a whole-day tuple (close-to-close log return, high/close, low/close) resampled with
replacement from the stock's own last 250 sessions up to t (adjusted prices, rule 9). S(h) is
the share of the 500 paths not yet confirmed reversed by day h. Nothing is fitted; only data up
to the close of t is used.
"""

from __future__ import annotations

import zlib

import numpy as np
import pandas as pd

from vnbank.research.shared.config import load
from vnbank.research.swings.directional_change import ATR_WINDOW, label_series, true_range

CFG = load(1)
N_PATHS = 500
WINDOW = 250
STEPS = CFG["evaluation"]["max_step"]  # 20


def roll(direction, extreme, close, tr_hist, k, paths) -> np.ndarray:
    """Duration (1..STEPS) of the first confirmed reversal on each path, STEPS + 1 if none.

    direction, extreme, close: (n,) state after the close of t; tr_hist: (n, ATR_WINDOW) the
    true ranges of days t-19..t; paths: (n, p, STEPS, 3) tuples (log return, high/close,
    low/close). Mirrors label_series: theta_s = k * ATR20(s-1) / close(s-1); an up-swing is
    confirmed reversed when close <= extreme * (1 - theta), a down-swing when close >=
    extreme * (1 + theta); a new extreme updates first."""
    n, p = paths.shape[:2]
    d = np.repeat(np.asarray(direction, float)[:, None], p, axis=1)
    ext = np.repeat(np.asarray(extreme, float)[:, None], p, axis=1)
    c_prev = np.repeat(np.asarray(close, float)[:, None], p, axis=1)
    trs = np.repeat(np.asarray(tr_hist, float)[:, None, :], p, axis=1)  # (n, p, 20)
    done = np.full((n, p), STEPS + 1, dtype=np.int16)
    alive = np.ones((n, p), dtype=bool)
    for s in range(STEPS):
        theta = k * trs.mean(axis=2) / c_prev
        r, hc, lc = paths[:, :, s, 0], paths[:, :, s, 1], paths[:, :, s, 2]
        c = c_prev * np.exp(r)
        h, lo = c * hc, c * lc
        tr = np.maximum(h, c_prev) - np.minimum(lo, c_prev)
        up, dn = d > 0, d < 0
        new_hi, new_lo = up & (c > ext), dn & (c < ext)
        conf = alive & ((up & ~new_hi & (c <= ext * (1 - theta)))
                        | (dn & ~new_lo & (c >= ext * (1 + theta))))  # fmt: skip
        done[conf] = s + 1
        alive &= ~conf
        ext = np.where(new_hi | new_lo, c, ext)
        trs = np.concatenate([trs[:, :, 1:], tr[:, :, None]], axis=2)
        c_prev = c
    return done


def survival_from_durations(done: np.ndarray) -> np.ndarray:
    """(n, p) first-reversal days -> S(1..STEPS) per row."""
    steps = np.arange(1, STEPS + 1)
    return (done[:, :, None] > steps[None, None, :]).mean(axis=1).astype("float32")


def stock_state(px: pd.DataFrame, k: float):
    """One stock's adjusted series (sorted) -> per-day state arrays and day tuples."""
    h, lo, c = (px[x].to_numpy(dtype="float64") for x in ("high_adj", "low_adj", "close_adj"))
    lab = label_series(h, lo, c, k=k)
    tr = true_range(h, lo, c)
    r = np.full(len(c), np.nan)
    r[1:] = np.log(c[1:] / c[:-1])
    tuples = np.column_stack([r, h / c, lo / c])
    return lab, tr, c, tuples


def rw_survival(prices: pd.DataFrame, rows: pd.DataFrame, k: float, seed: int = 20261126,
                n_paths: int = N_PATHS, chunk: int = 400) -> np.ndarray:  # fmt: skip
    """S(1..20) under the random-walk null for each row (ticker, trade_date) of `rows`.
    prices: adjusted OHLC of every stock (ticker, trade_date, high_adj, low_adj, close_adj).
    Deterministic: each stock draws from its own generator seeded by (seed, ticker)."""
    out = np.full((len(rows), STEPS), np.nan, dtype="float32")
    pos = {t: np.flatnonzero(rows.ticker.to_numpy() == t) for t in rows.ticker.unique()}
    for tk, idx in pos.items():
        px = prices[prices.ticker == tk].sort_values("trade_date").reset_index(drop=True)
        if px.empty:
            continue
        lab, tr, c, tuples = stock_state(px, k)
        dates = px.trade_date.to_numpy()
        want = rows.trade_date.to_numpy()[idx].astype(dates.dtype)
        order = np.argsort(want, kind="stable")
        ti = np.searchsorted(dates, want[order])
        rng = np.random.default_rng([seed, zlib.crc32(str(tk).encode())])
        for a in range(0, len(order), chunk):
            sel, t = order[a : a + chunk], ti[a : a + chunk]
            ok = (t < len(dates)) & (dates[np.minimum(t, len(dates) - 1)] == want[sel])
            ok &= (t >= ATR_WINDOW) & (lab.direction[np.minimum(t, len(dates) - 1)] != 0)
            u = rng.random(size=(len(t), n_paths, STEPS))  # drawn for every row: determinism
            sel, t, u = sel[ok], t[ok], u[ok]
            if not len(t):
                continue
            lo_w = np.maximum(1, t - WINDOW + 1)
            span = t - lo_w + 1
            day = lo_w[:, None, None] + (u * span[:, None, None]).astype(np.int64)
            paths = tuples[day]  # (n, p, 20, 3)
            hist = np.stack([tr[x - ATR_WINDOW + 1 : x + 1] for x in t])
            done = roll(lab.direction[t], lab.running_extreme[t], c[t], hist, k, paths)
            out[idx[sel]] = survival_from_durations(done)
    return out
