"""Stock-level features: block A (swing state) and block B (technicals)
(docs/proposals/paper1-trend-reversals.md,
Methodology 3). Every value on day t uses only data up to the close of t; tests check this
by truncation. Prices are adjusted (scale-free ratios only; CLAUDE.md rule 9).
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from research.labels.directional_change import Labels, atr20

RSI_WINDOW = 14
VOLUME_WINDOW = 20
LIMIT_WINDOW = 5


def block_a(close: np.ndarray, labels: Labels) -> pd.DataFrame:
    """Swing state after the close of t: direction, age, and the move so far and the distance
    from the running extreme, both in units of the day's threshold theta."""
    n = len(close)
    start = labels.swing_start_index
    has = start >= 0
    start_price = np.where(has, close[np.where(has, start, 0)], np.nan)
    idx = np.arange(n)
    th = labels.theta
    return pd.DataFrame(
        {
            "swing_dir": labels.direction.astype("int8"),
            "swing_age": np.where(has, idx - start, np.nan),
            "swing_age_conf": np.where(
                labels.swing_confirm_index >= 0, idx - labels.swing_confirm_index, np.nan
            ),  # fmt: skip
            # signed move since the swing's start, in thresholds (>0 = along the swing)
            "swing_move": labels.direction * (close / start_price - 1) / th,
            # distance from the running extreme, in thresholds: reversal at -1
            "swing_dist": labels.direction * (close / labels.running_extreme - 1) / th,
            "theta": th,
        }
    )


def rsi(close: np.ndarray, window: int = RSI_WINDOW) -> np.ndarray:
    """RSI from simple averages of gains and losses over the last `window` changes."""
    d = np.diff(close, prepend=np.nan)
    gain, loss = np.clip(d, 0, None), np.clip(-d, 0, None)
    g = pd.Series(gain).rolling(window, min_periods=window).mean().to_numpy()
    lo = pd.Series(loss).rolling(window, min_periods=window).mean().to_numpy()
    with np.errstate(divide="ignore", invalid="ignore"):
        out = 100 - 100 / (1 + g / lo)
    return np.where(lo == 0, np.where(g > 0, 100.0, 50.0), out)


def block_b(px: pd.DataFrame) -> pd.DataFrame:
    """Technicals after the close of t. px: one stock, sorted by date, with close_adj, high_adj,
    low_adj, volume, close_at_ceiling, close_at_floor, limit_status."""
    c = px["close_adj"].to_numpy(dtype="float64")
    logc = np.log(c)
    vol = px["volume"].to_numpy(dtype="float64")
    vol_avg = pd.Series(vol).rolling(VOLUME_WINDOW, min_periods=VOLUME_WINDOW).mean().to_numpy()
    up_hit = (px["close_at_ceiling"].fillna(False).to_numpy(dtype=bool)).astype("float64")
    dn_hit = (px["close_at_floor"].fillna(False).to_numpy(dtype=bool)).astype("float64")
    known = (px["limit_status"] == "computed").to_numpy(dtype="float64")

    def lagdiff(k: int) -> np.ndarray:
        out = np.full(len(c), np.nan)
        out[k:] = logc[k:] - logc[:-k]
        return out

    roll = lambda x: pd.Series(x).rolling(LIMIT_WINDOW, min_periods=1).sum().to_numpy()  # noqa: E731
    return pd.DataFrame(
        {
            "ret_1": lagdiff(1),
            "ret_5": lagdiff(5),
            "ret_20": lagdiff(20),
            "atr_pct": atr20(px["high_adj"].to_numpy(), px["low_adj"].to_numpy(), c) / c,
            "rsi_14": rsi(c),
            "vol_rel_20": np.where(vol_avg > 0, vol / vol_avg, np.nan),
            "limit_up_hits_5": roll(up_hit),
            "limit_down_hits_5": roll(dn_hit),
            "limit_known_5": roll(known) / LIMIT_WINDOW,  # share of the last 5 days with limits
            "close_at_limit": np.maximum(up_hit, dn_hit),  # proposal: limit-close days flagged
        }
    )
