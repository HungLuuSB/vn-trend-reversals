"""Visual-transcription tier for loan-quality tables OCR could not accept (D-023).

The worklist names, for each first-release document without an accepted OCR table, the pages
most likely to hold the table (ranked by loan-group words in the OCR text) and renders them to
PNG for reading. A transcribed row enters ``dbt/seeds/loan_quality_transcribed.csv`` only if
the five groups (plus any unclassified rows inside the total) sum **exactly** to the printed
total in **both** columns; ``check_row`` is that test and the seed's pytest applies it to every
row.

    uv run python -m vnbank.documents.tables.visual --out <dir>      # worklist + page images
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

import pandas as pd

from vnbank.documents.tables.loan_quality import fold

SEED_COLUMNS = ["raw_key", "page", "symbol", "year", "period", "kind",
                "g1", "g1_prior", "g2", "g2_prior", "g3", "g3_prior", "g4", "g4_prior",
                "g5", "g5_prior", "extra", "extra_prior", "total", "total_prior", "unit",
                "method", "transcribed_on", "note"]  # fmt: skip
_CUES = ("tieuchuan", "canchu", "chuy", "nghingo", "matvon", "khanang", "nhom")


def check_row(r) -> bool:
    """Exact two-column check: g1..g5 + extra == total, current and comparison columns."""
    for suf in ("", "_prior"):
        parts = [int(r[f"g{i}{suf}"]) for i in range(1, 6)] + [int(r[f"extra{suf}"] or 0)]
        if sum(parts) != int(r[f"total{suf}"]):
            return False
    return True


def candidate_pages(pages: list[str], k: int = 3) -> list[int]:
    """1-based pages ranked by loan-group cue words on lines that also carry a large number."""
    scores = []
    for i, text in enumerate(pages, start=1):
        s = 0
        for line in text.splitlines():
            c = re.sub(r"[^a-z0-9]", "", fold(line))
            if any(q in c for q in _CUES) and re.search(r"\d[\d.,]{5,}", line):
                s += 1
        scores.append((s, i))
    return [i for s, i in sorted(scores, reverse=True)[:k] if s > 0]


def render(pdf: bytes, page: int, out_png: Path, dpi: int = 150) -> Path:
    with tempfile.TemporaryDirectory() as d:
        src = Path(d) / "doc.pdf"
        src.write_bytes(pdf)
        stem = Path(d) / "p"
        subprocess.run(["pdftoppm", "-r", str(dpi), "-f", str(page), "-l", str(page), "-png",
                        "-singlefile", str(src), str(stem)], check=True, timeout=120)  # fmt: skip
        out_png.write_bytes(stem.with_suffix(".png").read_bytes())
    return out_png


def main(argv: list[str] | None = None) -> int:  # pragma: no cover - CLI wiring
    import hashlib

    from vnbank.common import paths
    from vnbank.common.env import load_dotenv
    from vnbank.common.raw_store import S3RawStore
    from vnbank.documents.parse.containers import ARCHIVES, archive_pdfs
    from vnbank.documents.parse.ocr import CACHE

    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--out", required=True, type=Path)
    a = p.parse_args(argv)
    a.out.mkdir(parents=True, exist_ok=True)
    npl = pd.read_parquet(paths.REPO / "data" / "extracted" / "block_e_npl.parquet")
    todo = npl[npl.value_source.isna()]
    load_dotenv(["S3_"])
    store = S3RawStore.from_env()
    work = []
    for r in todo.itertuples():
        body = store.get(r.raw_key)
        pdfs = [("", body)] if body.startswith(b"%PDF") else (
            archive_pdfs(body) if body.startswith(ARCHIVES) else [])  # fmt: skip
        offset, items = 0, []
        for member, pdf in pdfs:
            hit = CACHE / f"{hashlib.sha256(pdf).hexdigest()}.json"
            pages = json.loads(hit.read_text())["pages"] if hit.exists() else []
            for pg in candidate_pages(pages):
                png = a.out / f"{r.symbol}_{r.year}_Q{r.q}_{r.kind}_p{offset + pg}.png"
                render(pdf, pg, png)
                items.append({"page": offset + pg, "member": member, "png": str(png)})
            offset += len(pages)
        work.append({"raw_key": r.raw_key, "symbol": r.symbol, "year": int(r.year),
                     "q": int(r.q), "kind": r.kind, "candidates": items})  # fmt: skip
    (a.out / "worklist.json").write_text(json.dumps(work, indent=2, ensure_ascii=False))
    print(f"{len(work)} documents, {sum(len(w['candidates']) for w in work)} page images")
    return 0


if __name__ == "__main__":
    sys.exit(main())
