"""Embedding provider abstraction (Phase 7, FR-21, docs/decisions.md ADR-006).

Mirrors the chat LLM abstraction (docs/decisions.md ADR-005): a tiny
`embed` interface so swapping embedding backends never touches retrieval
code. `OpenAIEmbeddingProvider` is the real default; `MockEmbeddingProvider`
emits deterministic, fixed-length vectors (hash-based) so tests and the
no-key demo run without network access — the same mock-fallback pattern the
chat provider uses.

The schema stores 1536-dim vectors (text-embedding-3-small). The mock
produces 1536-dim vectors too so retrieval always compares like-for-like.
"""

from abc import ABC, abstractmethod
import hashlib
import math

from app.core.config import get_settings

EMBEDDING_DIM = 1536
EMBEDDING_MODEL = "text-embedding-3-small"


def _settings() -> str:
    return get_settings().embedding_model or EMBEDDING_MODEL


class EmbeddingProvider(ABC):
    """Async interface every embedding backend implements."""

    name: str = "base"

    @abstractmethod
    async def embed(self, text: str) -> list[float]:
        """Return a fixed-dimension embedding vector for `text`."""


class MockEmbeddingProvider(EmbeddingProvider):
    """Deterministic, keyless embeddings for tests/CI/demo.

    Each token hashes to a stable 0..1 value; the vector is the sum of token
    hashes renormalized to unit length. Same text -> same vector (that's all
    tests need); different texts almost always differ.
    """

    name = "mock"

    def _token_values(self, text: str) -> list[float]:
        lowered = " ".join(text.lower().split())
        return [
            int.from_bytes(hashlib.blake2b(token.encode(), digest_size=8).digest(), "big")
            / (2**64 - 1)
            for token in lowered.split()
        ]

    async def embed(self, text: str) -> list[float]:
        values = self._token_values(text)
        if not values:
            return [0.0] * EMBEDDING_DIM
        # Spread token values across the dimension space deterministically.
        vec = [0.0] * EMBEDDING_DIM
        for i, value in enumerate(values):
            idx = (i * 7) % EMBEDDING_DIM
            vec[idx] += value
        # Unit-normalize (skip the all-zero edge).
        norm = math.sqrt(sum(v * v for v in vec))
        if norm == 0:
            return vec
        return [v / norm for v in vec]


class OpenAIEmbeddingProvider(EmbeddingProvider):
    name = "openai"

    def __init__(self, api_key: str | None = None, model: str | None = None) -> None:
        from openai import AsyncOpenAI

        settings = get_settings()
        self._model = model or _settings()
        self._client = AsyncOpenAI(api_key=api_key or settings.openai_api_key)

    async def embed(self, text: str) -> list[float]:
        response = await self._client.embeddings.create(
            model=self._model,
            input=text,
        )
        return response.data[0].embedding


def get_embedding_provider() -> EmbeddingProvider:
    """Factory mirroring get_llm_provider: openai-without-key falls back to
    the deterministic mock so the app never crashes on a missing key.
    """
    settings = get_settings()
    provider_name = settings.llm_provider.strip().lower()
    if provider_name == "openai":
        if not settings.openai_api_key:
            return MockEmbeddingProvider()
        return OpenAIEmbeddingProvider()
    if provider_name == "mock":
        return MockEmbeddingProvider()
    # Unknown/invalid provider: deterministic mock is the safe default.
    return MockEmbeddingProvider()