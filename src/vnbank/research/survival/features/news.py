"""Block E news features (research/paper1/DECISIONS.md D-023 and its clarification 3).

* Articles: CafeF pages, deduplicated by URL, publication time from the page (UTC).
* Mention: a strict alias of the bank (ambiguous aliases such as "MB" excluded; the
  all-aliases count is a robustness check) in the title, sapo or body.
* ``news_count`` for (bank, session s): articles published in [09:00 on s, 09:00 on the next
  session), Asia/Ho_Chi_Minh. For a dataset row (t, decision_date) this is the window that ends
  at the row's decision time, so every counted article is public before it.
* ``news_rel_20``: log((1 + news_count) / (1 + mean news_count over the previous 20 sessions)),
  computed on the full session calendar, so it does not depend on which rows are in the risk
  set. NaN until 20 earlier sessions exist.
"""

from __future__ import annotations

from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

VN = ZoneInfo("Asia/Ho_Chi_Minh")
REL_WINDOW = 20


def articles(mentions: pd.DataFrame, column: str = "tickers_strict") -> pd.DataFrame:
    """(ticker, published_at_utc) per article mention, one per URL and ticker."""
    m = mentions.dropna(subset=["published_at_utc"]).drop_duplicates("url")
    m = m[["url", "published_at_utc", column]].explode(column).dropna(subset=[column])
    return m.rename(columns={column: "ticker"})[["ticker", "published_at_utc"]]


def _at_nine(days) -> np.ndarray:
    local = pd.to_datetime(pd.Series(days)) + pd.Timedelta(hours=9)
    return local.dt.tz_localize(VN).dt.tz_convert("UTC").to_numpy()


def session_counts(arts: pd.DataFrame, sessions, tickers) -> pd.DataFrame:
    """news_count and news_rel_20 for every (ticker, session) except the last session (whose
    window has no end in the calendar)."""
    cal = pd.Series(pd.to_datetime(list(sessions))).sort_values().reset_index(drop=True)
    starts, ends = _at_nine(cal[:-1]), _at_nine(cal[1:])
    out = []
    for tk in tickers:
        t = np.sort(pd.to_datetime(arts.loc[arts.ticker == tk, "published_at_utc"], utc=True)
                    .to_numpy())  # fmt: skip
        n = np.searchsorted(t, ends, side="left") - np.searchsorted(t, starts, side="left")
        prev = pd.Series(n, dtype="float64").rolling(REL_WINDOW).mean().shift(1).to_numpy()
        out.append(pd.DataFrame({"ticker": tk, "trade_date": cal[:-1].to_numpy(),
                                 "window_end_session": cal[1:].to_numpy(), "news_count": n,
                                 "news_rel_20": np.log((1 + n) / (1 + prev))}))  # fmt: skip
    return pd.concat(out, ignore_index=True)


def add_news_features(ds: pd.DataFrame, counts: pd.DataFrame) -> pd.DataFrame:
    """Join on (ticker, trade_date); non-bank rows get NaN."""
    c = counts.assign(trade_date=pd.to_datetime(counts.trade_date))
    out = ds.assign(trade_date=pd.to_datetime(ds.trade_date)).merge(
        c, on=["ticker", "trade_date"], how="left")  # fmt: skip
    bank = out.is_bank.astype(bool)
    have = bank & out.window_end_session.notna()
    if (
        out.loc[have, "window_end_session"] != pd.to_datetime(out.loc[have, "decision_date"])
    ).any():
        raise ValueError("count window does not end at the row's decision date")
    out.loc[~bank, ["news_count", "news_rel_20"]] = np.nan
    return out.drop(columns="window_end_session")
