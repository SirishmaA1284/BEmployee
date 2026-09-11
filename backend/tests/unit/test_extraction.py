"""Text extraction unit tests (Phase 9): text/PDF/DOCX + error paths.

The PDF and DOCX samples are generated in-memory (pypdf / python-docx are
runtime dependencies, so the tests exercise the real parsers without any
fixture files on disk).
"""

from io import BytesIO

import pytest

from app.services.errors import BusinessRuleError
from app.services.extraction import DOCX_CONTENT_TYPE, PDF_CONTENT_TYPE, extract_text


def _minimal_pdf(text: str) -> bytes:
    """Hand-built single-page PDF with one text line and correct xref offsets
    so pypdf's strict reader accepts it without repair."""
    content = f"BT /F1 12 Tf 72 720 Td ({text}) Tj ET".encode("ascii")
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        (
            b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
            b"/Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>"
        ),
        b"<< /Length " + str(len(content)).encode() + b" >>\nstream\n" + content + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    pdf = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for number, obj in enumerate(objects, start=1):
        offsets.append(len(pdf))
        pdf += f"{number} 0 obj\n".encode() + obj + b"\nendobj\n"
    xref = len(pdf)
    pdf += f"xref\n0 {len(objects) + 1}\n".encode()
    pdf += b"0000000000 65535 f \n"
    for offset in offsets[1:]:
        pdf += f"{offset:010d} 00000 n \n".encode()
    pdf += (
        f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF".encode()
    )
    return bytes(pdf)


def _docx(text: str) -> bytes:
    from docx import Document

    document = Document()
    for paragraph in text.split("\n\n"):
        document.add_paragraph(paragraph)
    buffer = BytesIO()
    document.save(buffer)
    return buffer.getvalue()


def test_extracts_plain_text():
    assert extract_text(content_type="text/plain", content="hello\nworld".encode()) == "hello\nworld"


def test_extracts_markdown_and_json():
    assert extract_text(content_type="text/markdown", content=b"# Title") == "# Title"
    assert extract_text(content_type="application/json", content=b'{"a": 1}') == '{"a": 1}'


def test_extracts_pdf_text():
    text = extract_text(content_type=PDF_CONTENT_TYPE, content=_minimal_pdf("Invoice total 450"))
    assert "Invoice total 450" in text


def test_extracts_docx_paragraphs_and_tables():
    from docx import Document

    document = Document()
    document.add_paragraph("Terms: 30 days")
    table = document.add_table(rows=1, cols=2)
    table.rows[0].cells[0].text = "SKU"
    table.rows[0].cells[1].text = "A-1"
    buffer = BytesIO()
    document.save(buffer)

    text = extract_text(content_type=DOCX_CONTENT_TYPE, content=buffer.getvalue())
    assert "Terms: 30 days" in text
    assert "SKU" in text
    assert "A-1" in text


def test_rejects_unknown_content_type():
    with pytest.raises(BusinessRuleError) as exc:
        extract_text(content_type="application/x-msdownload", content=b"x")
    assert exc.value.status_code == 415


def test_corrupt_pdf_raises_422():
    with pytest.raises(BusinessRuleError) as exc:
        extract_text(content_type=PDF_CONTENT_TYPE, content=b"%PDF-1.4 not really a pdf")
    assert exc.value.status_code == 422


def test_corrupt_docx_raises_422():
    with pytest.raises(BusinessRuleError) as exc:
        extract_text(content_type=DOCX_CONTENT_TYPE, content=b"PK\x03\x04 not a real docx")
    assert exc.value.status_code == 422


def test_pdf_without_text_is_empty():
    from pypdf import PdfWriter

    writer = PdfWriter()
    writer.add_blank_page(width=612, height=792)
    buffer = BytesIO()
    writer.write(buffer)

    text = extract_text(content_type=PDF_CONTENT_TYPE, content=buffer.getvalue())
    assert text == ""