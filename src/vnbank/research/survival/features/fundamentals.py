"""Block E fundamentals (research/paper1/DECISIONS.md D-023): first-released NPL ratios.

* **Document per bank-quarter** (first release): the consolidated quarterly statement (HN);
  for Q2 without HN the reviewed half-year statement (HNSX); for Q4 without HN the audited
  annual statement (HNKT); the parent-only quarterly statement (M) only when the quarter has no
  consolidated statement at all. Later versions are never used.
* **Value:** the current-period column of that document's loan-quality table (OCR extraction,
  or the curated visual-transcription seed when OCR could not read it).
* **available_at:** 09:00 (Asia/Ho_Chi_Minh) of the ``margin``-th HOSE session after the later
  of the filing deadline (quarter end + 45 days; half-year end + 45 days for HNSX; year end +
  90 days for HNKT) and the PDF's own creation date.
* **Features** for a bank row with decision time T (09:00 on ``decision_date``): ``npl_ratio``
  = the latest value with available_at < T; ``npl_change`` = that quarter's value minus the
  previous quarter's first-released value, public once both are.
"""

from __future__ import annotations

from datetime import date, timedelta
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

VN = ZoneInfo("Asia/Ho_Chi_Minh")
CONSOLIDATED_FALLBACK = {"HNSX": 2, "HNKT": 4}  # kind -> the only quarter it may stand in for
DEADLINE_DAYS = {"HN": 45, "M": 45, "HNSX": 45, "HNKT": 90}
QUARTER = {"Q1": 1, "Q2": 2, "Q3": 3, "Q4": 4, "CN": 4}
MARGIN_SESSIONS = 5  # D-023 main; robustness 0 and 20


def quarter_end(year: int, q: int) -> date:
    return date(year, 12, 31) if q == 4 else date(year, 3 * q + 1, 1) - timedelta(days=1)


def first_release(docs: pd.DataFrame) -> pd.DataFrame:
    """One document per (symbol, year, q). docs: symbol, year, period, kind, raw_key, ..."""
    d = docs.assign(q=docs.period.map(QUARTER))
    rank = pd.Series(np.nan, index=d.index)
    rank[d.kind == "HN"] = 0
    for kind, q in CONSOLIDATED_FALLBACK.items():
        rank[(d.kind == kind) & (d.q == q)] = 1
    rank[d.kind == "M"] = 2
    d = d.assign(rank=rank).dropna(subset=["rank"])
    return (d.sort_values(["symbol", "year", "q", "rank", "raw_key"])
            .groupby(["symbol", "year", "q"], as_index=False).head(1)
            .drop(columns="rank").reset_index(drop=True))  # fmt: skip


def available_at(year: int, q: int, kind: str, created: date | None, sessions: np.ndarray,
                 margin: int = MARGIN_SESSIONS) -> pd.Timestamp:  # fmt: skip
    """09:00 local of the margin-th session strictly after max(deadline, created), in UTC.
    margin = 0 means 09:00 of the first session after that date."""
    later = quarter_end(year, q) + timedelta(days=DEADLINE_DAYS[kind])
    if created is not None and not pd.isna(created) and created > later:
        later = created
    i = np.searchsorted(sessions, np.datetime64(later), side="right") + max(margin - 1, 0)
    if i >= len(sessions):
        return pd.NaT
    s = pd.Timestamp(sessions[i]).date()
    return pd.Timestamp(year=s.year, month=s.month, day=s.day, hour=9, tz=VN).tz_convert("UTC")


def quarterly_values(fr: pd.DataFrame, sessions: np.ndarray,
                     margin: int = MARGIN_SESSIONS) -> pd.DataFrame:  # fmt: skip
    """fr: first-release rows with symbol, year, q, kind, npl_ratio, created (date or NaT).
    Adds available_at, and npl_change with its own (later of the two) available_at."""
    out = fr.copy()
    out["available_at"] = [available_at(y, q, k, c, sessions, margin) for y, q, k, c in
                           zip(out.year, out.q, out.kind, out.created, strict=True)]  # fmt: skip
    out["qidx"] = out.year * 4 + out.q - 1
    prev = out[["symbol", "qidx", "npl_ratio", "available_at"]].assign(qidx=lambda x: x.qidx + 1)
    out = out.merge(prev, on=["symbol", "qidx"], how="left", suffixes=("", "_prev"))
    out["npl_change"] = out.npl_ratio - out.npl_ratio_prev
    out["change_available_at"] = out[["available_at", "available_at_prev"]].max(axis=1)
    return out.drop(columns=["npl_ratio_prev", "available_at_prev"])


def decision_utc(decision_date: pd.Series) -> pd.Series:
    local = pd.to_datetime(decision_date) + pd.Timedelta(hours=9)
    return local.dt.tz_localize(VN).dt.tz_convert("UTC")


def _asof(rows: pd.DataFrame, vals: pd.DataFrame, value: str, at: str) -> pd.Series:
    """Latest vals[value] per symbol with vals[at] strictly before the row's decision time."""
    v = vals.dropna(subset=[value, at]).sort_values(at)[["symbol", at, value]]
    v[at] = pd.to_datetime(v[at], utc=True).astype("datetime64[ns, UTC]")  # parquet may give us
    r = rows.sort_values("_t")
    r["_t"] = pd.to_datetime(r["_t"], utc=True).astype("datetime64[ns, UTC]")
    m = pd.merge_asof(r, v.rename(columns={at: "_t", "symbol": "ticker"}), on="_t", by="ticker",
                      allow_exact_matches=False)  # fmt: skip
    return m.set_index("_row")[value].reindex(rows["_row"]).to_numpy()


def add_npl_features(ds: pd.DataFrame, values: pd.DataFrame) -> pd.DataFrame:
    """npl_ratio and npl_change on bank rows (NaN elsewhere and when nothing is public yet)."""
    rows = pd.DataFrame({"_row": np.arange(len(ds)), "ticker": ds.ticker.to_numpy(),
                         "_t": decision_utc(ds.decision_date).to_numpy()})  # fmt: skip
    rows["_t"] = pd.to_datetime(rows["_t"], utc=True)
    out = ds.copy()
    out["npl_ratio"] = _asof(rows, values, "npl_ratio", "available_at")
    out["npl_change"] = _asof(rows, values, "npl_change", "change_available_at")
    bank = ds.is_bank.astype(bool).to_numpy()
    out.loc[~bank, ["npl_ratio", "npl_change"]] = np.nan
    return out
