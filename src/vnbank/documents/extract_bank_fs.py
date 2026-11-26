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


def _one(key: str, meta: dict | None = None) -> dict:
    load_dotenv(["S3_"])
    store = S3RawStore.from_env()
    name = key.rsplit("/", 1)[-1]
    row = {"raw_key": key, **(meta or parse_name(name) or {})}
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
    period_end = None
    if row.get("period") and row.get("year"):
        from vnbank.research.survival.features.fundamentals import QUARTER, quarter_end

        if row["period"] in QUARTER:
            period_end = quarter_end(int(row["year"]), QUARTER[row["period"]])
    lq = find_loan_quality(pages, period_end)
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


_TIME = re.compile(r"^(?P<per>Q[1-4]|CN)/(?P<year>\d{4})$")
_SHA = re.compile(r"\.[0-9a-f]{8}(?=\.|$)")


def original_name(stored: str, listed=()) -> str | None:
    """Invert raw_key's ``<stem>.<sha8><suffix>``: remove one ``.xxxxxxxx`` hex segment that is
    followed by a dot or the end. Several candidates (a stem may contain dots or hex): the one
    CafeF listed wins, else the last."""
    cands = [stored[: m.start()] + stored[m.end() :] for m in _SHA.finditer(stored)]
    if not cands:
        return None
    return next((c for c in cands if c in listed), cands[-1])


_LIST = re.compile(r"/list_(?P<sym>[A-Z]+)_(?P<year>\d{4})\.")


def kind_from_description(name: str) -> str:
    """CafeF's description of a filing -> statement kind (D-023 clarification 5)."""
    n = name.lower()
    base = "HN" if "hợp nhất" in n else "M" if "mẹ" in n else ""
    if "soát xét" in n:
        return base + "SX" if base else "SX"
    if "kiểm toán" in n:
        return base + "KT" if base else "KT"
    return base or "Q"


def filing_index(store) -> pd.DataFrame:
    """Every stored filing file with symbol, year, period, kind and suffix: from the file name
    where it follows CafeF's old pattern, otherwise from the stored list replies' Time and Name
    (kind_source says which). Files found in neither are left out."""
    import json

    prefix = "cafef_filings/"
    keys = sorted(store.list_keys(prefix) if hasattr(store, "list_keys")
                  else [k for k in store.keys() if k.startswith(prefix)])  # fmt: skip
    listed = {}
    for k in keys:
        m = _LIST.search(k)
        if not m:
            continue
        for r in json.loads(store.get(k)).get("Data") or []:
            listed[str(r["Link"]).rsplit("/", 1)[-1]] = (m["sym"], str(r["Time"]), str(r["Name"]))
    rows = []
    for k in keys:
        if _LIST.search(k):
            continue
        fname = k.rsplit("/", 1)[-1]
        original = original_name(fname, listed)
        if original is None:
            continue
        stem = original.rsplit(".", 1)[0] if "." in original else original
        if meta := parse_name(fname):
            rows.append({**meta, "raw_key": k, "name": stem, "kind_source": "filename"})
            continue
        hit = listed.get(original) or next((v for f, v in listed.items()
                                            if f.lower() == original.lower()), None)  # fmt: skip
        t = _TIME.match(hit[1]) if hit else None
        if hit and t:
            rows.append({"symbol": hit[0], "year": int(t["year"]), "period": t["per"],
                         "kind": kind_from_description(hit[2]), "suffix": stem,
                         "raw_key": k, "name": stem, "kind_source": "list_name"})  # fmt: skip
    return pd.DataFrame(rows)


def candidate_keys(index: pd.DataFrame) -> list[str]:
    """Every file of the kind that wins the D-023 precedence for its bank-quarter (all versions
    of it, so the creation-date rule can choose later), earliest stored copy per file name."""
    from vnbank.research.survival.features.fundamentals import QUARTER, kind_rank

    d = index[index.period.isin(list(QUARTER))].copy()
    d["q"] = d.period.map(QUARTER)
    d["rank"] = [kind_rank(k, q) for k, q in zip(d.kind, d.q, strict=True)]
    d = d.dropna(subset=["rank"]).sort_values("raw_key").drop_duplicates("name")
    best = d.groupby(["symbol", "year", "q"])["rank"].transform("min")
    return sorted(d[d["rank"] == best].raw_key)


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
    index = filing_index(S3RawStore.from_env())
    kinds, syms = set(a.kinds.split(",")), set(filter(None, a.symbols.split(",")))
    if a.first_release_only:
        sel = index[index.raw_key.isin(candidate_keys(index))]
    else:
        sel = index[index.kind.isin(kinds)]
    if syms:
        sel = sel[sel.symbol.isin(syms)]
    if a.years:
        y0, y1 = map(int, a.years.split("-"))
        sel = sel[sel.year.between(y0, y1)]
    meta = sel.set_index("raw_key")[["symbol", "year", "period", "kind"]].to_dict("index")
    todo = sorted(meta)
    if a.limit:
        todo = todo[: a.limit]
    print(f"{len(todo)} documents", flush=True)
    rows = []
    with ProcessPoolExecutor(max_workers=a.processes) as ex:
        for r in ex.map(_one, todo, [meta[k] for k in todo]):
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
