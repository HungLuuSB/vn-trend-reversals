"""Creation dates for block E's publication-time rule (D-023 clarification 3)."""

import io
import shutil
import zipfile
from datetime import date

import pytest

from vnbank.documents.parse.pdfmeta import document_created, docx_created, local_date


def test_local_date_offsets():
    assert local_date("2014-08-13T10:28:38+07") == date(2014, 8, 13)
    assert local_date("2011-08-18T20:15:28Z") == date(2011, 8, 19)  # 03:15 next day in Hanoi
    assert local_date("2015-02-26T10:57:38") == date(2015, 2, 26)  # no offset: local
    assert local_date("garbage") is None


def test_docx_core_created():
    core = (
        b'<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/'
        b'metadata/core-properties" xmlns:dcterms="http://purl.org/dc/terms/">'
        b"<dcterms:created>2013-01-30T17:30:00Z</dcterms:created></cp:coreProperties>"
    )
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("word/document.xml", "<x/>")
        z.writestr("docProps/core.xml", core)
    assert docx_created(buf.getvalue()) == date(2013, 1, 31)
    assert document_created(buf.getvalue()) == date(2013, 1, 31)


def _pdf(created: str) -> bytes:
    objs = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [4 0 R] /Count 1 >>",
        f"<< /CreationDate ({created}) /ModDate (D:20300101000000Z) >>".encode(),
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 10 10] >>",
    ]
    out, offs = b"%PDF-1.4\n", []
    for i, o in enumerate(objs, 1):
        offs.append(len(out))
        out += f"{i} 0 obj\n".encode() + o + b"\nendobj\n"
    x = len(out)
    out += f"xref\n0 {len(objs) + 1}\n0000000000 65535 f \n".encode()
    out += b"".join(f"{o:010d} 00000 n \n".encode() for o in offs)
    trailer = f"trailer\n<< /Size {len(objs) + 1} /Root 1 0 R /Info 3 0 R >>\n"
    out += (trailer + f"startxref\n{x}\n%%EOF\n").encode()
    return out


@pytest.mark.skipif(shutil.which("pdfinfo") is None, reason="needs pdfinfo (poppler)")
def test_pdf_creation_date_not_mod_date():
    assert document_created(_pdf("D:20140813102838+07'00'")) == date(2014, 8, 13)
