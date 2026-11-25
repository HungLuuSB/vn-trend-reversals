"""Statements that CafeF serves as archives (.rar/.zip/.7z holding PDFs) or as Word files.

Archives are untrusted downloads: their members are streamed to memory with bsdtar
(libarchive), never unpacked to disk. A .docx is read from its own XML with the standard
library, one table row per line (cells joined by spaces), which is the line shape the
loan-quality parser expects from OCR text.
"""

from __future__ import annotations

import io
import re
import subprocess
import zipfile
from xml.etree import ElementTree as ET

W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
ARCHIVES = (b"Rar!\x1a\x07", b"7z\xbc\xaf\x27\x1c", b"PK\x03\x04")
MAX_MEMBER = 200 * 1024 * 1024  # refuse absurd members (zip bombs)


def is_docx(body: bytes) -> bool:
    if not body.startswith(b"PK\x03\x04"):
        return False
    try:
        return "word/document.xml" in zipfile.ZipFile(io.BytesIO(body)).namelist()
    except zipfile.BadZipFile:
        return False


def docx_lines(body: bytes) -> list[str]:
    """Paragraphs and table rows of a .docx body, in document order."""
    root = ET.fromstring(zipfile.ZipFile(io.BytesIO(body)).read("word/document.xml"))
    out: list[str] = []

    def text(el) -> str:  # tabs and breaks separate columns laid out with tab stops
        parts = [(t.text or "") if t.tag == f"{W}t" else " " for t in el.iter()
                 if t.tag in (f"{W}t", f"{W}tab", f"{W}br")]  # fmt: skip
        return re.sub(r"\s+", " ", "".join(parts)).strip()

    for el in root.find(f"{W}body"):
        if el.tag == f"{W}p":
            out.append(text(el))
        elif el.tag == f"{W}tbl":
            for row in el.iter(f"{W}tr"):
                out.append(" ".join(c for c in (text(tc) for tc in row.iter(f"{W}tc")) if c))
    return out


def _bsdtar(opts: list[str], body: bytes, members: tuple[str, ...] = ()) -> bytes:
    return subprocess.run(["bsdtar", *opts, "-f", "-", *members], input=body,
                          capture_output=True, check=True, timeout=120).stdout  # fmt: skip


def archive_pdfs(body: bytes) -> list[tuple[str, bytes]]:
    """(member name, bytes) of every PDF in the archive, in name order."""
    names = _bsdtar(["-t"], body).decode("utf-8", errors="replace").splitlines()
    out = []
    for name in sorted(n for n in names if re.search(r"\.pdf$", n, re.I)):
        data = _bsdtar(["-x", "-O"], body, (name,))
        if data.startswith(b"%PDF") and len(data) <= MAX_MEMBER:
            out.append((name, data))
    return out
