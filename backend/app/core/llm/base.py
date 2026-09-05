"""Provider-neutral LLM interface.

The interface is deliberately small: one `generate` call that may return
text and/or tool calls. Tool schemas are plain JSON-schema dicts
(name/description/input schema), the same provider-neutral shape the MCP
server will re-expose in Phase 7 (docs/decisions.md ADR-010) — the
application never talks provider SDK types.

Nothing here touches the database or business logic; agents layer the
registry on top (docs/decisions.md ADR-003).
"""

from abc import ABC, abstractmethod
from typing import Any

from pydantic import BaseModel, Field


class ToolCallRequest(BaseModel):
    """A tool the model may call, described in provider-neutral JSON schema."""

    name: str
    description: str
    input_schema: dict[str, Any] = Field(default_factory=dict)


class ToolCallResult(BaseModel):
    """One tool call the model produced. Arguments are validated by the tool
    registry (app/tools) before anything executes — never trusted as-is.
    """

    name: str
    arguments: dict[str, Any] = Field(default_factory=dict)


class LLMResponse(BaseModel):
    """A single model response: prose content and/or tool calls.

    `content` is the model's natural-language turn (may be empty when the
    model only emits tool calls). `tool_calls` are ordered; the caller
    executes them one at a time, persisting each as an agent action.
    """

    content: str = ""
    tool_calls: list[ToolCallResult] = Field(default_factory=list)


class LLMProvider(ABC):
    """Async interface every provider (OpenAI, Mock, future Anthropic/
    Gemini) implements. `generate` is the only method agents call.
    """

    name: str = "base"

    @abstractmethod
    async def generate(
        self,
        *,
        system: str,
        messages: list[dict[str, str]],
        tools: list[ToolCallRequest] | None = None,
    ) -> LLMResponse:
        """Complete a chat conversation.

        Args:
            system: system prompt, never includes retrieved document content
                (that lives in `messages` as clearly-delimited untrusted data).
            messages: alternating user/assistant turns.
            tools: optional provider-neutral tool schemas the model may call.

        Returns:
            LLMResponse with prose and/or tool calls. Must never raise for a
            model-level failure (network, timeout, malformed output) — the
            provider maps those to LLMResponse(content="...") so the agent
            loop can surface a structured error instead of crashing.
        """