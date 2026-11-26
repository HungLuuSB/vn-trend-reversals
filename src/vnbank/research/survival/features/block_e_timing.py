"""Pre-registered check of block E publication timing (research/paper1/DECISIONS.md D-023,
"Validation"): for each first-release statement, the earliest CafeF article that mentions the
bank (strict aliases) and its result for that quarter is compared with the statement's
``available_at``.

    uv run python -m vnbank.research.survival.features.block_e_timing

Articles are matched on their URL slug (CafeF slugs are the ASCII-folded title): a period
phrase for the quarter (``quy-3``, ``quy-iii``, ``9-thang``; ``6-thang``/``nua-dau-nam`` for
Q2; ``nam-2015``/``ca-nam`` for Q4) together with a result word (``loi-nhuan``, ``lai``,
``lo``, ``no-xau``, ``bctc``, ``bao-cao-tai-chinh``, ``kinh-doanh``), published between the
quarter end and 150 days after it. News earlier than ``available_at`` shows the rule is
conservative; the earliest matching news **after** ``available_at`` flags a statement that may
have been published later than assumed. This measures the rule; it is not a feature.
"""

from __future__ import annotations

import re
import sys
from datetime import timedelta

import pandas as pd

from vnbank.common import paths
from vnbank.research.survival.features.fundamentals import quarter_end

EXTRACTED = paths.REPO / "data" / "extracted"
WINDOW_DAYS = 150
_ROMAN = {1: "i", 2: "ii", 3: "iii", 4: "iv"}
_RESULT = re.compile(r"(?:^|-)(loi-nhuan|lai|lo|no-xau|bctc|bao-cao-tai-chinh|kinh-doanh)(?:-|$)")


def period_pattern(year: int, q: int) -> re.Pattern:
    yy = str(year)
    alts = [rf"quy-{q}", rf"quy-{_ROMAN[q]}"]
    if q == 2:
        alts += ["6-thang", "nua-dau-nam", "ban-nien"]
    if q == 3:
        alts += ["9-thang"]
    if q == 4:
        alts += ["ca-nam", rf"nam-{yy}"]
    return re.compile(r"(?:^|-)(?:" + "|".join(alts) + r")(?:-|$)")


def slug(url: str) -> str:
    s = url.rsplit("/", 1)[-1]
    return re.sub(r"-\d{10,}\.chn$", "", s.removesuffix(".chn"))


def is_result_news(url: str, year: int, q: int) -> bool:
    s = slug(url)
    return bool(period_pattern(year, q).search(s) and _RESULT.search(s))


def earliest_news(statements: pd.DataFrame, articles: pd.DataFrame) -> pd.Series:
    """statements: symbol, year, q. articles: ticker, published_at_utc, url (one row per
    article and bank). Returns the earliest matching article time (UTC) per statement."""
    out = []
    by_bank = {t: g.sort_values("published_at_utc") for t, g in articles.groupby("ticker")}
    for s in statements.itertuples():
        g = by_bank.get(s.symbol)
        if g is None:
            out.append(pd.NaT)
            continue
        qe = pd.Timestamp(quarter_end(int(s.year), int(s.q)), tz="Asia/Ho_Chi_Minh")
        lo, hi = qe + timedelta(days=1), qe + timedelta(days=WINDOW_DAYS)
        w = g[(g.published_at_utc >= lo) & (g.published_at_utc < hi)]
        hit = w[[is_result_news(u, int(s.year), int(s.q)) for u in w.url]]
        out.append(hit.published_at_utc.iloc[0] if len(hit) else pd.NaT)
    return pd.Series(out, index=statements.index, dtype="datetime64[ns, UTC]")


def main(argv: list[str] | None = None) -> int:  # pragma: no cover - CLI wiring
    npl = pd.read_parquet(EXTRACTED / "block_e_npl.parquet")
    st = npl[npl.npl_ratio.notna() & npl.available_at.notna()].copy()
    files = sorted((EXTRACTED / "news_mentions").glob("*.parquet"))
    cols = ["url", "published_at_utc", "tickers_strict"]
    m = pd.concat([pd.read_parquet(f, columns=cols) for f in files], ignore_index=True)
    m = m.dropna(subset=["published_at_utc"]).drop_duplicates("url")
    arts = m.explode("tickers_strict").dropna(subset=["tickers_strict"])
    arts = arts.rename(columns={"tickers_strict": "ticker"})
    arts["published_at_utc"] = pd.to_datetime(arts.published_at_utc, utc=True)
    arts = arts[arts.ticker.isin(set(st.symbol))]
    st["news_at"] = earliest_news(st, arts)
    st["available_at"] = pd.to_datetime(st.available_at, utc=True)
    st["dated"] = st.created.notna()
    st["lead_days"] = (st.available_at - st.news_at).dt.total_seconds() / 86400
    has = st.news_at.notna()
    print(f"statements with a value: {len(st)}; with matching result news: {int(has.sum())}")
    for name, g in (("dated", st[has & st.dated]), ("undated", st[has & ~st.dated])):
        if len(g):
            share, lead = (g.lead_days > 0).mean(), g.lead_days.median()
            print(f"  {name:8s} n={len(g):4d}  news before available_at: {share:.1%}  "
                  f"median lead {lead:.1f} d")  # fmt: skip
    late = st[has & (st.lead_days <= 0)].sort_values("lead_days")
    print(f"earliest result news AT/AFTER available_at: {len(late)}")
    show = ["symbol", "year", "period", "kind", "created", "available_at", "news_at", "lead_days"]
    print(late[show].to_string(index=False))
    out = EXTRACTED / "block_e_timing_check.parquet"
    st[[*show, "dated", "raw_key"]].to_parquet(out, index=False)
    print(f"written: {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
