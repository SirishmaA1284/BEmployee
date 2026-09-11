"""Text extraction from uploaded documents (Phase 9).

`extract_text` turns validated upload bytes into plain text for the
chunking/embedding pipeline (app/services/document_service.py). It is
deterministic, pure backend code — never an LLM call.

Supported formats (the upload allow-list in app/api/documents.py):
- text-based: .txt/.md/.csv/.json (UTF-8 decode, replacing bad bytes)
- PDF: parsed with pypdf (page text extraction)
- DOCX: parsed with python-docx (paragraphs + table cells)

Unparseable or text-less files raise BusinessRuleError(422) so the API
returns a clean error and nothing is persisted.
"""

from io import BytesIO

from app.services.errors import BusinessRuleError

# Content types that are decoded as UTF-8 text directly.
TEXT_CONTENT_TYPES = {
    "text/plain",
    "text/markdown",
    "text/csv",
    "application/json",
}

# Content types handled by a binary parser.
PDF_CONTENT_TYPE = "application/pdf"
DOCX_CONTENT_TYPE = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


def extract_text(*, content_type: str, content: bytes) -> str:
    """Extract plain text from uploaded bytes by content type."""
    if content_type in TEXT_CONTENT_TYPES:
        return content.decode("utf-8", errors="replace")

    if content_type == PDF_CONTENT_TYPE:
        return _extract_pdf(content)

    if content_type == DOCX_CONTENT_TYPE:
        return _extract_docx(content)

    raise BusinessRuleError(
        415, f"Unsupported content type '{content_type}' for text extraction"
    )


def _extract_pdf(content: bytes) -> str:
    try:
        from pypdf import PdfReader

        reader = PdfReader(BytesIO(content))
        pages = [page.extract_text() or "" for page in reader.pages]
        return "\n\n".join(pages).strip()
    except BusinessRuleError:
        raise
    except Exception as exc:  # corrupt / encrypted / truncated PDFs
        raise BusinessRuleError(
            422, "Could not extract text from this PDF (corrupt, encrypted, or unreadable)"
        ) from exc


def _extract_docx(content: bytes) -> str:
    try:
        from docx import Document as DocxDocument

        document = DocxDocument(BytesIO(content))
        parts = [p.text for p in document.paragraphs if p.text.strip()]
        for table in document.tables:
            for row in table.rows:
                parts.extend(cell.text for cell in row.cells if cell.text.strip())
        return "\n\n".join(parts).strip()
    except Exception as exc:  # corrupt / not-a-docx bytes
        raise BusinessRuleError(
            422, "Could not extract text from this DOCX (corrupt or unreadable)"
        ) from exc