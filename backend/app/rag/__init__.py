"""RAG package (Phase 7, docs/decisions.md ADR-006).

- `retriever.py`: business-scoped pgvector similarity search over
  `document_chunks` (FR-21).
- `answer.py`: grounded, cited answers built from retrieved chunks
  wrapped as untrusted data (FR-22/23).

The retrieval flow is documented in docs/architecture.md §4.
"""