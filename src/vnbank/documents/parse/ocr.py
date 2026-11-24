"""OCR of financial-statement PDFs (block E): pdftoppm + tesseract (vie+eng), cached by hash.

Every 2012-2016 bank statement checked was scanned or carried unusable scanner OCR
(docs/blockE-data-feasibility.md), so all pages are re-OCRed at 300 dpi. Results are cached in
data/ocr/<sha256>.json (git-ignored) keyed by the PDF's content hash, with the tool versions.
Needs the system packages tesseract, tesseract-data-vie, tesseract-data-eng and poppler.
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from vnbank.common import paths

CACHE = paths.REPO / "data" / "ocr"
DPI = 300
LANGS = "vie+eng"
PSM = "6"  # assume a uniform block of text: keeps table rows on one line


def tesseract_version() -> str:
    out = subprocess.run(["tesseract", "--version"], capture_output=True, text=True, check=True)
    return out.stdout.splitlines()[0].strip()


def _ocr_page(png: Path) -> str:
    env = {**os.environ, "OMP_THREAD_LIMIT": "1"}
    out = subprocess.run(["tesseract", str(png), "-", "-l", LANGS, "--psm", PSM],
                         capture_output=True, text=True, check=True, env=env)  # fmt: skip
    return out.stdout


def ocr_pdf(pdf: bytes, workers: int = 4, cache: Path = CACHE) -> list[str]:
    """Text of each page (1-based order). Cached by the PDF's SHA-256."""
    sha = hashlib.sha256(pdf).hexdigest()
    hit = cache / f"{sha}.json"
    if hit.is_file():
        return json.loads(hit.read_text())["pages"]
    with tempfile.TemporaryDirectory() as tmp:
        src = Path(tmp) / "in.pdf"
        src.write_bytes(pdf)
        subprocess.run(["pdftoppm", "-r", str(DPI), "-gray", "-png", str(src),
                        str(Path(tmp) / "p")], check=True, capture_output=True)  # fmt: skip
        pngs = sorted(Path(tmp).glob("p-*.png"), key=lambda p: int(p.stem.split("-")[-1]))
        with ThreadPoolExecutor(max_workers=workers) as ex:
            pages = list(ex.map(_ocr_page, pngs))
    cache.mkdir(parents=True, exist_ok=True)
    hit.write_text(json.dumps({"sha256": sha, "dpi": DPI, "langs": LANGS, "psm": PSM,
                               "tesseract": tesseract_version(), "pages": pages},
                              ensure_ascii=False))  # fmt: skip
    return pages
