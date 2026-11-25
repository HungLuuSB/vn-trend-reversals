"""OCR stored bank statements and extract the loan-quality table (block E).

    uv run python -m vnbank.documents.extract_bank_fs --kinds HN,HNSX,HNKT [--limit 10]

Reads PDFs from the raw layer (raw/cafef_filings/), OCRs them (cached by hash) and writes one
row per document to data/extracted/loan_quality.parquet: symbol, period, kind, raw key, page,
the five groups and the total (current and comparison columns), NPL ratio, and status
(ok / no_table / not_pdf). Archives (.zip/.rar/.7z) are read member by member (PDFs in name
order, pages numbered across them); a .docx is read from its XML (``container`` column).
"""

from __future__ import annotations

import argparse
import re
import sys
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import pandas as pd

from vnbank.common import paths
from vnbank.common.env import load_dotenv
from vnbank.common.raw_store import S3RawStore
from vnbank.documents.parse.containers import ARCHIVES, archive_pdfs, docx_lines, is_docx
from vnbank.documents.parse.ocr import ocr_pdf
from vnbank.documents.tables.loan_quality import find_loan_quality

OUT = paths.REPO / "data" / "extracted" / "loan_quality.parquet"
_NAME = re.compile(
    r"^(?P<sym>[A-Z]+)_(?P<yy>\d\d)(?P<per>Q\d|CN)_(?:BCTC|KQKD)_(?P<kind>[A-Z]+)"
    r"(?:_(?P<suffix>[0-9A-Za-z-]+))?\."
)  # suffix: later re-uploads (D-023 c. 4)


def parse_name(name: str) -> dict | None:
    m = _NAME.match(name)
    if not m:
        return None
    return {"symbol": m["sym"], "year": 2000 + int(m["yy"]), "period": m["per"],
            "kind": m["kind"], "suffix": m["suffix"] or ""}  # fmt: skip


def _one(key: str) -> dict:
    load_dotenv(["S3_"])
    store = S3RawStore.from_env()
    name = key.rsplit("/", 1)[-1]
    row = {"raw_key": key, **(parse_name(name) or {})}
    body = store.get(key)
    t0 = time.time()
    if body.startswith(b"%PDF"):
        row["container"], pages = "pdf", ocr_pdf(body, workers=2)
    elif is_docx(body):
        row["container"], pages = "docx", ["\n".join(docx_lines(body))]
    elif body.startswith(ARCHIVES) and (pdfs := archive_pdfs(body)):
        row["container"], pages = "archive", [p for _, b in pdfs for p in ocr_pdf(b, workers=2)]
        row["members"] = " | ".join(n for n, _ in pdfs)
    else:
        return {**row, "status": "not_pdf"}
    lq = find_loan_quality(pages)
    row.update({"n_pages": len(pages), "ocr_s": round(time.time() - t0, 1)})
    if lq is None:
        return {**row, "status": "no_table"}
    for i, (cur, prev) in enumerate(lq.groups, start=1):
        row[f"g{i}"], row[f"g{i}_prior"] = cur, prev
    row.update({"total": lq.total[0], "total_prior": lq.total[1], "page": lq.page,
                "extra": lq.extra[0], "extra_prior": lq.extra[1],
                "npl_ratio": lq.npl_ratio, "npl_ratio_prior": lq.npl_ratio_prior,
                "status": "ok"})  # fmt: skip
    return row


def candidate_keys(keys) -> list[str]:
    """Every file of the kind that wins the D-023 precedence for its bank-quarter (all versions
    of it, so the creation-date rule can choose later), earliest stored copy per file name."""
    from vnbank.research.survival.features.fundamentals import CONSOLIDATED_FALLBACK, QUARTER

    rows = []
    for k in sorted(keys):
        meta = parse_name(k.rsplit("/", 1)[-1])
        if not meta or meta["period"] not in QUARTER:
            continue
        q, kind = QUARTER[meta["period"]], meta["kind"]
        rank = 0 if kind == "HN" else 1 if CONSOLIDATED_FALLBACK.get(kind) == q else (
            2 if kind == "M" else None)  # fmt: skip
        if rank is not None:
            rows.append({**meta, "q": q, "rank": rank, "key": k,
                         "name": k.rsplit("/", 1)[-1].split(".")[0]})  # fmt: skip
    d = pd.DataFrame(rows).drop_duplicates("name")  # keys are sorted: earliest copy kept
    best = d.groupby(["symbol", "year", "q"])["rank"].transform("min")
    return sorted(d[d["rank"] == best].key)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--kinds", default="HN,HNSX,HNKT")
    p.add_argument("--symbols", default="")
    p.add_argument("--limit", type=int, default=0)
    p.add_argument("--processes", type=int, default=6)
    p.add_argument(
        "--first-release-only",
        action="store_true",
        help="only files of the kind that is the first release of each bank-quarter "
        "(every version of it; D-023), including M where nothing else exists",
    )
    p.add_argument("--years", default="", help="e.g. 2016-2026")
    p.add_argument("--out", default="", help="output parquet (default data/extracted/...)")
    a = p.parse_args(argv)
    load_dotenv(["S3_"])
    keys = S3RawStore.from_env().list_keys("cafef_filings/")
    kinds, syms = set(a.kinds.split(",")), set(filter(None, a.symbols.split(",")))
    todo = []
    for k in sorted(keys):
        meta = parse_name(k.rsplit("/", 1)[-1])
        if meta and meta["kind"] in kinds and (not syms or meta["symbol"] in syms):
            todo.append(k)
    if a.first_release_only:
        todo = candidate_keys(keys)
    if a.years:
        y0, y1 = map(int, a.years.split("-"))
        todo = [k for k in todo if y0 <= parse_name(k.rsplit("/", 1)[-1])["year"] <= y1]
    if syms:
        todo = [k for k in todo if parse_name(k.rsplit("/", 1)[-1])["symbol"] in syms]
    if a.limit:
        todo = todo[: a.limit]
    print(f"{len(todo)} documents", flush=True)
    rows = []
    with ProcessPoolExecutor(max_workers=a.processes) as ex:
        for r in ex.map(_one, todo):
            rows.append(r)
            npl = f"npl={r['npl_ratio']:.4f}" if r["status"] == "ok" else ""
            print(r.get("symbol"), r.get("year"), r.get("period"), r.get("kind"), r["status"],
                  npl, flush=True)  # fmt: skip
    df = pd.DataFrame(rows)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    out = Path(a.out) if a.out else OUT
    df.to_parquet(out, index=False)
    print(df.status.value_counts().to_dict(), "->", out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
