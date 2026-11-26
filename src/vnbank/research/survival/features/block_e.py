"""Build block E inputs (D-023) from the extraction outputs and the raw layer.

    uv run python -m vnbank.research.survival.features.block_e --snapshot b536ec69488162e0

Writes (git-ignored, data/extracted/):

* ``block_e_npl.parquet``: one row per bank-quarter: the first-release document, its creation
  date, the NPL ratio and where it came from (``ocr``, ``visual`` seed, or none),
  ``available_at``, ``npl_change`` and ``change_available_at``.
* ``news_counts.parquet``: per bank and HOSE session, ``news_count`` / ``news_rel_20`` (strict
  aliases) and ``*_all`` (all aliases). Sessions whose 09:00-09:00 window is not fully covered by
  the processed news bundles are NaN, not zero.

Prints a coverage summary: bank-quarters by value source, and news sessions covered.
"""

from __future__ import annotations

import argparse
import re
import sys
from datetime import date, timedelta

import numpy as np
import pandas as pd

from vnbank.common import paths
from vnbank.common.env import load_dotenv
from vnbank.common.raw_store import S3RawStore
from vnbank.documents.extract_bank_fs import filing_index
from vnbank.documents.parse.pdfmeta import document_created
from vnbank.research.survival.features.fundamentals import first_release, quarterly_values
from vnbank.research.survival.features.news import articles, session_counts

EXTRACTED = paths.REPO / "data" / "extracted"
SEED = paths.SEEDS / "loan_quality_transcribed.csv"
_WINDOW = re.compile(r"cafef_news_(\d{8})_(\d\d)\.")


def documents(store) -> pd.DataFrame:
    """Statement files block E may use (D-023 kinds, incl. clarification 5), from the filing
    index (file name, or CafeF's description for new-style names); earliest copy per name."""
    d = filing_index(store)
    d = d[d.kind.isin(["HN", "HNSX", "HNKT", "M", "Q", "SX", "KT"])]
    return d.sort_values("raw_key").drop_duplicates("name").drop(columns="name")


def drop_mislabelled(docs: pd.DataFrame) -> pd.DataFrame:
    """D-023 clarification 8: a file created within the 12 months before its quarter's end
    cannot be that quarter's statement (CafeF mislabel). Older creation dates are broken PDF
    metadata and are kept (the filing deadline governs publication time)."""
    from vnbank.research.survival.features.fundamentals import QUARTER, quarter_end

    qend = pd.to_datetime([quarter_end(int(y), QUARTER[p]) if p in QUARTER else pd.NaT
                           for y, p in zip(docs.year, docs.period, strict=True)])  # fmt: skip
    created = pd.to_datetime(docs.created)
    bad = created.notna() & (created < qend) & (created >= qend - pd.Timedelta(days=365))
    if bad.any():
        print(f"{int(bad.sum())} mislabelled file(s) excluded:",
              docs.loc[bad, ["symbol", "year", "period", "kind"]].to_dict("records"))  # fmt: skip
    return docs[~bad.to_numpy()]


def npl_values(fr: pd.DataFrame) -> pd.DataFrame:
    ocr = pd.read_parquet(EXTRACTED / "loan_quality.parquet")[["raw_key", "status", "npl_ratio"]]
    out = fr.merge(ocr, on="raw_key", how="left")
    out["value_source"] = np.where(out.status == "ok", "ocr", None)
    if SEED.exists():
        seed = pd.read_csv(SEED)
        g = seed[[f"g{i}" for i in range(1, 6)]].to_numpy(dtype="float64")
        seed = seed.assign(npl_seed=g[:, 2:].sum(axis=1) / g.sum(axis=1))[["raw_key", "npl_seed"]]
        out = out.merge(seed, on="raw_key", how="left")
        use = out.value_source.isna() & out.npl_seed.notna()
        out.loc[use, "npl_ratio"] = out.loc[use, "npl_seed"]
        out.loc[use, "value_source"] = "visual"
        out = out.drop(columns="npl_seed")
    out.loc[out.value_source.isna(), "npl_ratio"] = np.nan
    return out


def covered_dates(mention_files) -> set[date]:
    """Local dates covered by the processed news bundles (window names cafef_news_YYYYMMDD_DD)."""
    days = set()
    for f in mention_files:
        m = _WINDOW.match(f.name)
        if not m:
            continue
        d0 = date.fromisoformat(f"{m[1][:4]}-{m[1][4:6]}-{m[1][6:]}")
        d = d0
        while d.day <= int(m[2]) and d.month == d0.month:
            days.add(d)
            d += timedelta(days=1)
    return days


def news_counts(sessions: pd.Series, tickers: list[str]) -> pd.DataFrame:
    files = sorted((EXTRACTED / "news_mentions").glob("*.parquet"))
    men = pd.concat([pd.read_parquet(f) for f in files], ignore_index=True)
    strict = session_counts(articles(men, "tickers_strict"), sessions, tickers)
    every = session_counts(articles(men, "tickers"), sessions, tickers)
    out = strict.merge(every.drop(columns="window_end_session"), on=["ticker", "trade_date"],
                       suffixes=("", "_all"))  # fmt: skip
    cov = covered_dates(files)
    full = [all((s.date() + timedelta(days=i)) in cov for i in range((e - s).days + 1))
            for s, e in zip(pd.to_datetime(out.trade_date), pd.to_datetime(out.window_end_session),
                            strict=True)]  # fmt: skip
    cols = ["news_count", "news_rel_20", "news_count_all", "news_rel_20_all"]
    out.loc[~np.array(full), cols] = np.nan
    # the 20-session mean must also lie inside the covered period
    for c in ("news_rel_20", "news_rel_20_all"):
        ok = pd.Series(full, index=out.index).groupby(out.ticker).transform(
            lambda x: x.astype(float).rolling(21).min().fillna(0).astype(bool))  # fmt: skip
        out.loc[~ok, c] = np.nan
    return out


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--snapshot", required=True)
    a = p.parse_args(argv)
    sessions = pd.read_parquet(paths.SNAPSHOTS / a.snapshot / "sessions_hose.parquet").trade_date
    sess = np.sort(pd.to_datetime(sessions).to_numpy())
    load_dotenv(["S3_"])
    store = S3RawStore.from_env()
    docs = documents(store)
    # creation dates of every candidate: versions (clarification 4) and mislabels (clarification 8)
    from concurrent.futures import ThreadPoolExecutor

    with ThreadPoolExecutor(8) as ex:
        docs["created"] = list(ex.map(lambda k: document_created(store.get(k)), docs.raw_key))
    dup = docs.duplicated(["symbol", "year", "period", "kind"], keep=False)
    print(f"{int(dup.sum())} files share a bank-quarter and kind with another file")
    docs = drop_mislabelled(docs)
    fr = first_release(docs)
    vals = quarterly_values(npl_values(fr), sess)
    vals.to_parquet(EXTRACTED / "block_e_npl.parquet", index=False)
    print(pd.crosstab(vals.symbol, vals.value_source.fillna("none"), margins=True).to_string())
    print("kinds:", vals.kind.value_counts().to_dict(), "| created missing:",
          int(vals.created.isna().sum()))  # fmt: skip
    nc = news_counts(sessions, sorted(vals.symbol.unique()))
    nc.to_parquet(EXTRACTED / "news_counts.parquet", index=False)
    yr = pd.to_datetime(nc.trade_date).dt.year
    print("news sessions covered by year:", nc.news_count.notna().groupby(yr).mean().round(2)
          .to_dict())  # fmt: skip
    return 0


if __name__ == "__main__":
    sys.exit(main())


def ocr_only(npl: pd.DataFrame) -> pd.DataFrame:
    """D-023 robustness: drop visually transcribed values and recompute npl_change from the
    remaining first-release values (a change needs both quarters from OCR)."""
    out = npl.copy()
    out.loc[out.value_source != "ocr", "npl_ratio"] = np.nan
    prev = out[["symbol", "qidx", "npl_ratio"]].assign(qidx=lambda x: x.qidx + 1)
    out = out.drop(columns="npl_change").merge(prev, on=["symbol", "qidx"], how="left",
                                               suffixes=("", "_prev"))  # fmt: skip
    out["npl_change"] = out.npl_ratio - out.npl_ratio_prev
    return out.drop(columns="npl_ratio_prev")


E_VARIANTS = (None, "ocr_only", "margin0", "margin20", "all_aliases")  # D-023 robustness


def add_block_e(
    ds: pd.DataFrame,
    ocr_values_only: bool = False,
    snapshot: str | None = None,
    variant: str | None = None,
    sessions=None,
) -> tuple[pd.DataFrame, dict]:
    """D-023: add npl_ratio, npl_change, news_count, news_rel_20 and keep bank rows only.
    variant (pre-registered robustness): "ocr_only" drops the visually transcribed values;
    "margin0"/"margin20" recompute available_at with 0 or 20 sessions (needs `sessions`);
    "all_aliases" counts news with every alias. ocr_values_only=True is variant "ocr_only".
    snapshot: read the inputs from that frozen snapshot when it holds them (D-024 gate 1; the
    final run requires it), else from data/extracted/. Returns the dataset and each input's
    sha256 and source (recorded in the run config)."""
    import hashlib

    from vnbank.research.survival.features.fundamentals import add_npl_features
    from vnbank.research.survival.features.news import add_news_features

    variant = "ocr_only" if ocr_values_only else variant
    if variant not in E_VARIANTS:
        raise ValueError(f"unknown block E variant {variant}")
    meta, src = {"variant": variant}, {}
    for name in ("block_e_npl.parquet", "news_counts.parquet"):
        src[name], meta[f"{name}:source"] = paths.frozen_input(snapshot, name, EXTRACTED)
        meta[name] = hashlib.sha256(src[name].read_bytes()).hexdigest()
    npl = pd.read_parquet(src["block_e_npl.parquet"])
    if variant == "ocr_only":
        npl = ocr_only(npl)
    if variant in ("margin0", "margin20"):
        if sessions is None:
            raise ValueError("margin variants need the session calendar")
        base = npl[["symbol", "year", "q", "kind", "npl_ratio", "created", "value_source"]]
        npl = quarterly_values(base, np.sort(np.asarray(sessions)), int(variant[6:]))
    meta["ocr_values_only"] = variant == "ocr_only"
    nc = pd.read_parquet(src["news_counts.parquet"])
    if variant == "all_aliases":
        nc = nc.drop(columns=["news_count", "news_rel_20"]).rename(
            columns={"news_count_all": "news_count", "news_rel_20_all": "news_rel_20"}
        )
    bank = ds[ds.is_bank.astype(bool)].reset_index(drop=True)
    bank = add_npl_features(bank, npl)
    bank = add_news_features(bank, nc[["ticker", "trade_date", "window_end_session",
                                       "news_count", "news_rel_20"]])  # fmt: skip
    meta["bank_rows"] = len(bank)
    cols = ("npl_ratio", "npl_change", "news_count", "news_rel_20")
    meta["share_missing"] = {c: round(float(bank[c].isna().mean()), 4) for c in cols}
    return bank, meta
