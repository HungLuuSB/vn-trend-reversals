"""Daily input sequences for the neural hazard model (research/paper1/DECISIONS.md D-022).

For a survival row (stock, t) the sequence is the stock's own last SEQ_LEN trading days, ending
with t (all known at the close of t, before the 09:00 decision on t+1). Channels are
scale-free and come from adjusted prices (CLAUDE.md data rule 9):
  r  log close-to-close return
  hl log(high / low)
  co log(close / open)
  vr log(volume / mean volume of the previous VOLUME_WINDOW days)
Columns are named seq_<channel>_<lag>, lag = SEQ_LEN - 1 .. 0 (0 = day t), oldest first.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from vnbank.research.shared.config import load

CFG = load(1)["neural"]
SEQ_LEN = CFG["seq_len"]
VOLUME_WINDOW = CFG["volume_window"]
CHANNELS = ["r", "hl", "co", "vr"]
SEQ = "seq"  # feature-list token: "all sequence columns" (models/neural.py)


def seq_columns(seq_len: int = SEQ_LEN) -> list[str]:
    return [f"seq_{c}_{lag}" for c in CHANNELS for lag in range(seq_len - 1, -1, -1)]


def daily_channels(px: pd.DataFrame) -> pd.DataFrame:
    """px: one ticker's adjusted OHLCV rows sorted by trade_date. Returns the four channels."""
    with np.errstate(divide="ignore", invalid="ignore"):
        close = px.close_adj.to_numpy(dtype="float64")
        vol = px.volume.to_numpy(dtype="float64")
        high, low = px.high_adj.to_numpy(dtype="float64"), px.low_adj.to_numpy(dtype="float64")
        open_ = px.open_adj.to_numpy(dtype="float64")
        prev_mean = pd.Series(vol).shift(1).rolling(VOLUME_WINDOW, min_periods=VOLUME_WINDOW)
        prev_mean = prev_mean.mean().to_numpy()
        out = pd.DataFrame({
            "r": np.log(close / np.r_[np.nan, close[:-1]]),
            "hl": np.log(high / low),
            "co": np.log(close / open_),
            "vr": np.log(vol / prev_mean),
        })  # fmt: skip
    return out.replace([np.inf, -np.inf], np.nan)


def add_sequences(ds: pd.DataFrame, prices: pd.DataFrame, seq_len: int = SEQ_LEN) -> pd.DataFrame:
    """Append seq_* columns (float32) to the survival rows ds (ticker, trade_date)."""
    cols = seq_columns(seq_len)
    block = np.full((len(ds), len(CHANNELS), seq_len), np.nan, dtype="float32")
    pos_in_ds = {t: np.flatnonzero(ds.ticker.to_numpy() == t) for t in ds.ticker.unique()}
    for t, idx in pos_in_ds.items():
        px = prices[prices.ticker == t].sort_values("trade_date")
        if px.empty:
            continue
        ch = daily_channels(px).to_numpy(dtype="float32")  # (n_days, 4)
        dates = px.trade_date.to_numpy()
        want = ds.trade_date.to_numpy()[idx].astype(dates.dtype)
        pos = np.searchsorted(dates, want)
        found = (pos < len(dates)) & (dates[np.minimum(pos, len(dates) - 1)] == want)
        for j, p, ok in zip(idx, pos, found, strict=True):
            if not ok:
                continue
            lo = p - seq_len + 1
            w = ch[max(lo, 0) : p + 1]  # days up to and including t only
            block[j, :, seq_len - len(w) :] = w.T
    seq = pd.DataFrame(block.reshape(len(ds), -1), columns=cols, index=ds.index)
    return pd.concat([ds, seq], axis=1)
