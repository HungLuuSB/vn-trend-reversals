"""Creation date of a stored statement, for block E's publication-time rule (D-023, clar. 3).

* PDF: ``CreationDate`` from ``pdfinfo -isodates`` (poppler), converted to its
  Asia/Ho_Chi_Minh date; a date without an offset is taken as local time. ``ModDate`` is never
  used.
* Archive: the latest creation date among its PDFs.
* .docx: ``dcterms:created`` in docProps/core.xml.

Returns None when the document carries no creation date (the filing deadline then applies).
"""

from __future__ import annotations

import io
import re
import subprocess
import tempfile
import zipfile
from datetime import date, datetime
from xml.etree import ElementTree as ET
from zoneinfo import ZoneInfo

from vnbank.documents.parse.containers import ARCHIVES, archive_pdfs, is_docx

VN = ZoneInfo("Asia/Ho_Chi_Minh")
_ISO = re.compile(r"^CreationDate:\s+(\S+)", re.M)


def local_date(stamp: str) -> date | None:
    """'2014-08-13T10:28:38+07', '2011-08-18T09:15:28Z' or without offset -> local date."""
    s = stamp.strip().replace("Z", "+00:00")
    s = re.sub(r"([+-]\d\d)$", r"\1:00", s)  # "+07" -> "+07:00"
    try:
        t = datetime.fromisoformat(s)
    except ValueError:
        return None
    return (t.astimezone(VN) if t.tzinfo else t).date()


def pdf_created(pdf: bytes) -> date | None:
    with tempfile.NamedTemporaryFile(suffix=".pdf") as f:
        f.write(pdf)
        f.flush()
        out = subprocess.run(["pdfinfo", "-isodates", f.name], capture_output=True, text=True,
                             timeout=60).stdout  # fmt: skip
    m = _ISO.search(out)
    return local_date(m[1]) if m else None


def docx_created(body: bytes) -> date | None:
    try:
        xml = zipfile.ZipFile(io.BytesIO(body)).read("docProps/core.xml")
    except KeyError:
        return None
    el = ET.fromstring(xml).find("{http://purl.org/dc/terms/}created")
    return local_date(el.text) if el is not None and el.text else None


def document_created(body: bytes) -> date | None:
    if body.startswith(b"%PDF"):
        return pdf_created(body)
    if is_docx(body):
        return docx_created(body)
    if body.startswith(ARCHIVES):
        dates = [d for _, b in archive_pdfs(body) if (d := pdf_created(b))]
        return max(dates) if dates else None
    return None
