"""Archive and .docx readers on small archives built in memory."""

import io
import shutil
import zipfile

import pytest

from vnbank.documents.parse.containers import archive_pdfs, docx_lines, is_docx

W = 'xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"'
DOC = f"""<w:document {W}><w:body>
<w:p><w:r><w:t>Phân tích theo nhóm</w:t></w:r></w:p>
<w:p><w:r><w:t>Nợ đủ tiêu chuẩn</w:t></w:r><w:r><w:tab/><w:t>95.663.399</w:t></w:r>
<w:r><w:tab/><w:t>101.564.431</w:t></w:r></w:p>
<w:tbl><w:tr><w:tc><w:p><w:r><w:t>Nợ cần chú ý</w:t></w:r></w:p></w:tc>
<w:tc><w:p><w:r><w:t>4.567.430</w:t></w:r></w:p></w:tc></w:tr></w:tbl>
</w:body></w:document>"""


def _zip(files: dict[str, bytes]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        for name, data in files.items():
            z.writestr(name, data)
    return buf.getvalue()


def test_docx_tab_stops_and_table_cells_become_spaced_lines():
    body = _zip({"word/document.xml": DOC.encode()})
    assert is_docx(body)
    assert docx_lines(body) == ["Phân tích theo nhóm", "Nợ đủ tiêu chuẩn 95.663.399 101.564.431",
                                "Nợ cần chú ý 4.567.430"]  # fmt: skip


@pytest.mark.skipif(shutil.which("bsdtar") is None, reason="needs bsdtar (libarchive)")
def test_archive_pdfs_in_name_order_non_pdfs_skipped():
    body = _zip({"b/notes.pdf": b"%PDF-1.4 notes", "a/balance.PDF": b"%PDF-1.4 bs",
                 "readme.txt": b"x", "fake.pdf": b"not a pdf"})  # fmt: skip
    assert not is_docx(body)
    assert archive_pdfs(body) == [("a/balance.PDF", b"%PDF-1.4 bs"),
                                  ("b/notes.pdf", b"%PDF-1.4 notes")]  # fmt: skip
