"""Phase 7 integration tests: documents, RAG retrieval/query, MCP (FR-21/22/23,
docs/decisions.md ADR-006/010). Phase 9 adds PDF/DOCX extraction uploads."""

import uuid

from app.models.document import Document, DocumentChunk
from app.services.document_service import ingest_document


async def _upload(client, headers, name="policy.txt", content="Return policy: 30 days.", content_type="text/plain"):
    return await client.post(
        "/api/documents",
        files={"file": (name, content.encode(), content_type)},
        headers=headers,
    )


def _minimal_pdf(text: str) -> bytes:
    """Hand-built single-page PDF with one text line (see unit tests)."""
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


def _docx(content: str) -> bytes:
    from io import BytesIO

    from docx import Document

    document = Document()
    for paragraph in content.split("\n\n"):
        document.add_paragraph(paragraph)
    buffer = BytesIO()
    document.save(buffer)
    return buffer.getvalue()


async def test_upload_document_creates_chunks(client, business, db_session):
    resp = await _upload(
        client,
        business["owner_headers"],
        content="Return policy: 30 days.\n\nWarranty: 1 year.",
    )
    assert resp.status_code == 201, resp.text
    doc = resp.json()
    assert doc["filename"] == "policy.txt"
    assert doc["size_bytes"] > 0

    detail = (await client.get(f"/api/documents/{doc['id']}", headers=business["owner_headers"])).json()
    assert detail["chunk_count"] == 2  # two paragraphs -> two chunks
    assert detail["chunks"][0]["content"] == "Return policy: 30 days."


async def test_upload_validation_rejects_bad_type_and_empty(client, business):
    resp = await _upload(client, business["owner_headers"], name="evil.exe", content_type="application/x-msdownload")
    assert resp.status_code == 415

    resp = await _upload(client, business["owner_headers"], content="   \n  ")
    assert resp.status_code == 422


async def test_upload_pdf_and_docx_extracts_text(client, business):
    """Phase 9: binary formats are parsed deterministically at upload."""
    pdf_resp = await client.post(
        "/api/documents",
        files={"file": ("terms.pdf", _minimal_pdf("Return policy allows 30 days"), "application/pdf")},
        headers=business["owner_headers"],
    )
    assert pdf_resp.status_code == 201, pdf_resp.text
    pdf_doc = pdf_resp.json()
    assert pdf_doc["content_type"] == "application/pdf"
    detail = (await client.get(f"/api/documents/{pdf_doc['id']}", headers=business["owner_headers"])).json()
    assert detail["chunk_count"] >= 1
    assert "30 days" in detail["chunks"][0]["content"]

    docx_resp = await client.post(
        "/api/documents",
        files={
            "file": (
                "policy.docx",
                _docx("Warranty: 1 year.\n\nReturns: 30 days."),
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            )
        },
        headers=business["owner_headers"],
    )
    assert docx_resp.status_code == 201, docx_resp.text
    docx_doc = docx_resp.json()
    detail = (await client.get(f"/api/documents/{docx_doc['id']}", headers=business["owner_headers"])).json()
    assert detail["chunk_count"] == 2  # two paragraphs -> two chunks
    assert detail["chunks"][0]["content"] == "Warranty: 1 year."


async def test_corrupt_pdf_upload_rejected(client, business):
    resp = await client.post(
        "/api/documents",
        files={"file": ("broken.pdf", b"%PDF-1.4 not really a pdf", "application/pdf")},
        headers=business["owner_headers"],
    )
    assert resp.status_code == 422

    listed = (await client.get("/api/documents", headers=business["owner_headers"])).json()
    assert listed == []  # nothing half-ingested


async def test_upload_requires_owner_admin(client, business, employee_headers):
    resp = await _upload(client, employee_headers)
    assert resp.status_code == 403


async def test_list_and_delete_document(client, business):
    created = (await _upload(client, business["owner_headers"])).json()
    listed = (await client.get("/api/documents", headers=business["owner_headers"])).json()
    assert [d["id"] for d in listed] == [created["id"]]

    resp = await client.delete(f"/api/documents/{created['id']}", headers=business["owner_headers"])
    assert resp.status_code == 204
    listed = (await client.get("/api/documents", headers=business["owner_headers"])).json()
    assert listed == []


async def test_retrieval_is_business_scoped(client, business, db_session):
    """A chunk from another business can never be retrieved under this one."""
    from app.services.document_service import ingest_document as ingest
    from app.core.llm.embeddings import MockEmbeddingProvider

    created = (await _upload(client, business["owner_headers"], content="Discount code: SUMMER10")).json()

    # Second business uploads a different doc.
    reg2 = await client.post(
        "/api/auth/register",
        json={"email": "docowner2@example.com", "password": "a-strong-password", "full_name": "D2"},
    )
    token2 = reg2.json()["access_token"]
    biz2 = (await client.post("/api/businesses", json={"name": "Biz 2"}, headers={"Authorization": f"Bearer {token2}"})).json()

    # Query from business 1 for its own content -> found.
    q1 = await client.post(
        "/api/documents/query",
        json={"query": "SUMMER10 discount"},
        headers=business["owner_headers"],
    )
    assert q1.status_code == 200
    assert q1.json()["chunks_used"] >= 1

    # Query from business 2 for business 1's content -> nothing found.
    headers2 = {"Authorization": f"Bearer {token2}", "X-Business-Id": biz2["id"]}
    q2 = await client.post(
        "/api/documents/query",
        json={"query": "SUMMER10 discount"},
        headers=headers2,
    )
    assert q2.json()["chunks_used"] == 0


async def test_rag_query_returns_answer_and_sources(client, business):
    await _upload(client, business["owner_headers"], content="Our return policy allows 30 days for returns.")
    resp = await client.post(
        "/api/documents/query",
        json={"query": "what is the return policy"},
        headers=business["owner_headers"],
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["chunks_used"] >= 1
    assert len(body["sources"]) >= 1
    assert body["sources"][0]["document_name"] == "policy.txt"
    assert "30 days" in body["answer"]


async def test_rag_query_no_documents(client, business):
    resp = await client.post(
        "/api/documents/query",
        json={"query": "anything"},
        headers=business["owner_headers"],
    )
    assert resp.status_code == 200
    assert resp.json()["chunks_used"] == 0


async def test_mcp_tools_list_is_read_only_subset(client, business):
    resp = await client.post(
        "/mcp",
        json={"jsonrpc": "2.0", "method": "tools/list", "id": 1},
        headers=business["owner_headers"],
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["id"] == 1
    names = {t["name"] for t in body["result"]["tools"]}
    assert "get_sales_report" in names
    assert "create_order" not in names  # writes never exposed
    assert "create_purchase_order" not in names


async def test_mcp_tools_call_read_only(client, business, db_session):
    # Seed a product so search_products returns something.
    from app.models.product import Product
    from app.models.inventory import Inventory
    from decimal import Decimal

    product = Product(
        business_id=business["business_id"], sku="MCP-1", name="MCP Coffee",
        unit="unit", unit_price=Decimal("100.00"), is_active=True,
    )
    db_session.add(product)
    await db_session.flush()
    db_session.add(
        Inventory(
            business_id=business["business_id"], product_id=product.id,
            quantity_on_hand=5, reorder_threshold=2, reorder_quantity=10,
        )
    )
    await db_session.commit()

    resp = await client.post(
        "/mcp",
        json={"jsonrpc": "2.0", "method": "tools/call",
              "params": {"name": "search_products", "arguments": {"query": "coffee"}}, "id": 2},
        headers=business["owner_headers"],
    )
    assert resp.status_code == 200
    result = resp.json()["result"]
    assert result["ok"] is True
    assert result["data"]["count"] >= 1


async def test_mcp_rejects_write_tool_and_bad_auth(client, business):
    resp = await client.post(
        "/mcp",
        json={"jsonrpc": "2.0", "method": "tools/call",
              "params": {"name": "create_order", "arguments": {}}, "id": 3},
        headers=business["owner_headers"],
    )
    assert resp.status_code == 200
    assert resp.json()["error"] is not None  # -32601 not exposed

    resp = await client.post(
        "/mcp",
        json={"jsonrpc": "2.0", "method": "tools/list", "id": 4},
        headers={"Authorization": "Bearer not-a-token", "X-Business-Id": business["business_id"]},
    )
    assert resp.status_code == 401