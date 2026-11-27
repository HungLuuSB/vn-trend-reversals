"""Data-quality facts reported in Paper 1's data section, written as a logged run.

    uv run --env-file .env python -m vnbank.research.survival.data_checks

Two checks, each already part of the pipeline, are recorded here so the paper can cite their
numbers from code (CLAUDE.md):

* CafeF sources: where the bulk archive and the per-ticker history both have a stock-day, how
  often all five fields agree (dbt mart ``qa_cafef_history_vs_bulk``, ClickHouse).
* Block E timing (D-023 validation): for each first-release statement with a matching result
  article, whether the article appeared before the statement's usable time (the logic of
  ``features.block_e_timing``).

Writes research/paper1/runs/<UTC timestamp>-datachecks/{config.json, metrics.json}.
"""

from __future__ import annotations

import json
import sys
from datetime import UTC, datetime

import pandas as pd

from vnbank.common import paths
from vnbank.research.shared.run_meta import code_version
from vnbank.research.survival.features import block_e_timing as T


def cafef_overlap() -> dict:
    from vnbank.common.clickhouse import client_from_env

    c = client_from_env()
    row = c.query(
        "select count(), sum(n_overlap), sum(ohlc_equal), sum(volume_equal), "
        "sum(ohlc_equal * (volume_equal = n_overlap)), min(first_date), max(last_date) "
        "from vnbank.qa_cafef_history_vs_bulk"
    ).result_rows[0]
    n_t, n, ohlc, vol, _, first, last = row
    both = c.query(
        "select count() from vnbank.stg_cafef_history h inner join (select ticker, trade_date, "
        "open_vnd, high_vnd, low_vnd, close_vnd, volume from vnbank.int_cafef__eod_checked "
        "where variant = 'raw' and dq_outcome = 'kept') b on h.ticker = b.ticker and "
        "h.trade_date = b.trade_date where h.open_vnd = b.open_vnd and h.high_vnd = b.high_vnd "
        "and h.low_vnd = b.low_vnd and h.close_vnd = b.close_vnd and h.volume = b.volume"
    ).result_rows[0][0]
    return {"tickers": int(n_t), "overlap_days": int(n), "ohlc_equal": int(ohlc),
            "volume_equal": int(vol), "all_five_equal": int(both),
            "first_date": str(first), "last_date": str(last)}  # fmt: skip


def block_e_news() -> dict:
    npl = pd.read_parquet(T.EXTRACTED / "block_e_npl.parquet")
    st = npl[npl.npl_ratio.notna() & npl.available_at.notna()].copy()
    files = sorted((T.EXTRACTED / "news_mentions").glob("*.parquet"))
    m = pd.concat([pd.read_parquet(f, columns=["url", "published_at_utc", "tickers_strict"])
                   for f in files], ignore_index=True)  # fmt: skip
    m = m.dropna(subset=["published_at_utc"]).drop_duplicates("url")
    arts = m.explode("tickers_strict").dropna(subset=["tickers_strict"])
    arts = arts.rename(columns={"tickers_strict": "ticker"})
    arts["published_at_utc"] = pd.to_datetime(arts.published_at_utc, utc=True)
    arts = arts[arts.ticker.isin(set(st.symbol))]
    st["news_at"] = T.earliest_news(st, arts)
    st["available_at"] = pd.to_datetime(st.available_at, utc=True)
    st["lead_days"] = (st.available_at - st.news_at).dt.total_seconds() / 86400
    has = st[st.news_at.notna()]
    return {
        "statements": int(len(st)),
        "with_result_news": int(len(has)),
        "news_before_available": int((has.lead_days > 0).sum()),
        "median_lead_days": float(has.lead_days.median()),
        "news_files": len(files),
    }


def main(argv: list[str] | None = None) -> int:
    commit = code_version()
    out = paths.runs_dir(1) / f"{datetime.now(UTC):%Y%m%dT%H%M%SZ}-datachecks"
    out.mkdir(parents=True)
    (out / "config.json").write_text(json.dumps(
        {"git_commit": commit, "created_at_utc": datetime.now(UTC).isoformat(),
         "checks": ["cafef_overlap", "block_e_news"]}, indent=1))  # fmt: skip
    metrics = {"cafef_overlap": cafef_overlap(), "block_e_news": block_e_news()}
    (out / "metrics.json").write_text(json.dumps(metrics, indent=1))
    print(out.name)
    print(json.dumps(metrics, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
