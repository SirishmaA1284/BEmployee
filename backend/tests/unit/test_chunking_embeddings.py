"""Chunking + mock embedding unit tests (Phase 7) — pure functions, no DB."""

import pytest

from app.core.llm.embeddings import EMBEDDING_DIM, MockEmbeddingProvider
from app.services.chunking import chunk_text


def test_chunk_short_document_is_single_chunk():
    text = "This is a short document.\n\nIt has two paragraphs."
    chunks = chunk_text(text)
    assert len(chunks) == 2
    assert chunks[0].content == "This is a short document."
    assert chunks[1].content == "It has two paragraphs."


def test_chunk_spans_are_accurate():
    text = "First paragraph.\n\nSecond paragraph."
    chunks = chunk_text(text)
    assert text[chunks[0].start_char : chunks[0].end_char] == chunks[0].content
    assert text[chunks[1].start_char : chunks[1].end_char] == chunks[1].content


def test_chunk_hard_splits_long_paragraph():
    long_word = "word " * 400  # 2000 chars, exceeds max 1200
    text = long_word.strip()
    chunks = chunk_text(text, max_chars=300)
    # Every chunk must be within the size limit and reconstructable from spans.
    for chunk in chunks:
        assert len(chunk.content) <= 300
        assert text[chunk.start_char : chunk.end_char] == chunk.content
    assert len(chunks) > 1


def test_chunk_empty_and_whitespace():
    assert chunk_text("") == []
    assert chunk_text("   \n\n  ") == []


def test_chunk_blank_lines_inside_paragraph_are_preserved():
    text = "Line one\n\nLine two"
    chunks = chunk_text(text)
    assert len(chunks) == 2
    assert chunks[0].content == "Line one"
    assert chunks[1].content == "Line two"


@pytest.mark.asyncio
async def test_mock_embedding_is_deterministic_and_fixed_dim():
    provider = MockEmbeddingProvider()
    v1 = await provider.embed("hello world")
    v2 = await provider.embed("hello world")
    assert v1 == v2
    assert len(v1) == EMBEDDING_DIM


@pytest.mark.asyncio
async def test_mock_embedding_differs_for_different_text():
    provider = MockEmbeddingProvider()
    v1 = await provider.embed("return policy is thirty days")
    v2 = await provider.embed("supplier pricing agreement")
    assert v1 != v2


@pytest.mark.asyncio
async def test_mock_embedding_empty_text_returns_zeros():
    provider = MockEmbeddingProvider()
    v = await provider.embed("")
    assert v == [0.0] * EMBEDDING_DIM