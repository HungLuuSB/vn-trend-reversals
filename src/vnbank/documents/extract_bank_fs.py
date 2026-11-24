"""OCR stored bank statements and extract the loan-quality table (block E).

    uv run python -m vnbank.documents.extract_bank_fs --kinds HN,HNSX,HNKT [--limit 10]

Reads PDFs from the raw layer (raw/cafef_filings/), OCRs them (cached by hash) and writes one
row per document to data/extracted/loan_quality.parquet: symbol, period, kind, raw key, page,
the five groups and the total (current and comparison columns), NPL ratio, and status
(ok / no_table / not_pdf). Archives (.zip/.rar/.7z) and .docx are skipped for now.
"""

from __future__ import annotations

import argparse
import re
import sys
import time
from concurrent.futures import ProcessPoolExecutor

import pandas as pd

from vnbank.common import paths
from vnbank.common.env import load_dotenv
from vnbank.common.raw_store import S3RawStore
from vnbank.documents.parse.ocr import ocr_pdf
from vnbank.documents.tables.loan_quality import find_loan_quality

OUT = paths.REPO / "data" / "extracted" / "loan_quality.parquet"
_NAME = re.compile(r"^(?P<sym>[A-Z]+)_(?P<yy>\d\d)(?P<per>Q\d|CN)_(?:BCTC|KQKD)_(?P<kind>[A-Z]+)\.")


def parse_name(name: str) -> dict | None:
    m = _NAME.match(name)
    if not m:
        return None
    return {"symbol": m["sym"], "year": 2000 + int(m["yy"]), "period": m["per"],
            "kind": m["kind"]}  # fmt: skip


def _one(key: str) -> dict:
    load_dotenv(["S3_"])
    store = S3RawStore.from_env()
    name = key.rsplit("/", 1)[-1]
    row = {"raw_key": key, **(parse_name(name) or {})}
    body = store.get(key)
    if not body.startswith(b"%PDF"):
        return {**row, "status": "not_pdf"}
    t0 = time.time()
    pages = ocr_pdf(body, workers=2)
    lq = find_loan_quality(pages)
    row.update({"n_pages": len(pages), "ocr_s": round(time.time() - t0, 1)})
    if lq is None:
        return {**row, "status": "no_table"}
    for i, (cur, prev) in enumerate(lq.groups, start=1):
        row[f"g{i}"], row[f"g{i}_prior"] = cur, prev
    row.update({"total": lq.total[0], "total_prior": lq.total[1], "page": lq.page,
                "npl_ratio": lq.npl_ratio, "npl_ratio_prior": lq.npl_ratio_prior,
                "status": "ok"})  # fmt: skip
    return row


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--kinds", default="HN,HNSX,HNKT")
    p.add_argument("--symbols", default="")
    p.add_argument("--limit", type=int, default=0)
    p.add_argument("--processes", type=int, default=6)
    a = p.parse_args(argv)
    load_dotenv(["S3_"])
    keys = S3RawStore.from_env().list_keys("cafef_filings/")
    kinds, syms = set(a.kinds.split(",")), set(filter(None, a.symbols.split(",")))
    todo = []
    for k in sorted(keys):
        meta = parse_name(k.rsplit("/", 1)[-1])
        if meta and meta["kind"] in kinds and (not syms or meta["symbol"] in syms):
            todo.append(k)
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
    df.to_parquet(OUT, index=False)
    print(df.status.value_counts().to_dict(), "->", OUT)
    return 0


if __name__ == "__main__":
    sys.exit(main())
