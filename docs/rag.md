# RAG (Retrieval-Augmented Generation)

Status: implemented in Phase 7 (FR-21/22/23, docs/decisions.md ADR-006). The retrieval flow is
documented in `docs/architecture.md` §4; the untrusted-context handling is in
`docs/threat-model.md` T1.

## Pipeline

1. **Upload** (`POST /api/documents`, OWNER/ADMIN): a file (.txt/.md/.csv/.json, plus PDF and
   DOCX since Phase 9, ≤ 2 MiB) is stored as a `documents` row. Content-type is checked against
   an allow-list (docs/security.md); PDF/DOCX text is extracted deterministically by
   `app/services/extraction.py` (pypdf / python-docx) before chunking.
2. **Chunking** (`app/services/chunking.py`): deterministic, never the LLM. Split into
   paragraphs, then hard-split any oversized paragraph at word boundaries (`max_chars`, default
   1200). No overlap — a paragraph belongs to exactly one chunk, and each chunk records its
   `(start_char, end_char)` span into the original text for precise citations.
3. **Embedding** (`app/core/llm/embeddings.py`): a provider-neutral `EmbeddingProvider.embed`
   interface (mirrors the chat LLM abstraction). `OpenAIEmbeddingProvider` uses
   `text-embedding-3-small` (1536-dim); `MockEmbeddingProvider` emits deterministic hash-based
   1536-dim vectors so tests/CI and the no-key demo run without network access. The factory
   falls back to mock when no key is set (same pattern as ADR-005).
4. **Storage**: each chunk is a `document_chunks` row with its embedding in a pgvector column
   (HNSW index, cosine distance). Everything is business-scoped.

## Retrieval

`app/rag/retriever.py::retrieve` embeds the query and runs a pgvector cosine-similarity search
over the business's `document_chunks`, filtering to non-deleted documents. Business scoping is
enforced by the query filter — a chunk from another business can never match.

## Answers & citations

`app/rag/answer.py::answer_query` (FR-22) ties retrieval to the LLM exactly as
`docs/architecture.md` §4 shows: embed → search → wrap top-k chunks in a delimited
`<business_documents>` block → the LLM reasons over it → return the answer plus cited sources
(document name, chunk index, similarity).

**Untrusted data (FR-23, threat-model T1):** retrieved content lives only inside the delimited
block and the system prompt states it is reference data that can never introduce instructions,
change permissions, or authorize actions. Tool/policy checks are unaffected by document text
(ADR-003). Under the MockProvider the answer is the top chunk verbatim (deterministic grounding);
with OpenAI it is a grounded LLM summary that ends with `Sources: <document names>`.

## Surfaces

- `POST /api/documents/query` — REST RAG query (any role).
- AI Employee chat with intent `ASK_DOCUMENTS` — routed to the RAG agent workflow
  (`app/agents/workflows/rag.py`), so "what does our policy say?" works in chat too.
- Frontend **Documents** page (`/documents`) — upload/list/delete + an "Ask your documents" box
  with cited sources.