"""OpenAI provider — the default real provider (docs/decisions.md ADR-005).

Uses the OpenAI Chat Completions API with function calling. All failures
(network, rate limit, malformed response) are mapped to an LLMResponse with
an explanatory `content` so the agent loop always gets structured output and
never sees a raw SDK exception.
"""

import json

from app.core.config import get_settings
from app.core.llm.base import LLMProvider, LLMResponse, ToolCallRequest, ToolCallResult

_settings = get_settings()


def _to_openai_tools(tools: list[ToolCallRequest]) -> list[dict]:
    return [
        {
            "type": "function",
            "function": {
                "name": tool.name,
                "description": tool.description,
                "parameters": tool.input_schema,
            },
        }
        for tool in tools
    ]


class OpenAIProvider(LLMProvider):
    name = "openai"

    def __init__(self, api_key: str | None = None, model: str | None = None) -> None:
        from openai import AsyncOpenAI

        self._model = model or _settings.openai_model
        self._client = AsyncOpenAI(api_key=api_key or _settings.openai_api_key)

    async def generate(
        self,
        *,
        system: str,
        messages: list[dict[str, str]],
        tools: list[ToolCallRequest] | None = None,
    ) -> LLMResponse:
        try:
            completion = await self._client.chat.completions.create(
                model=self._model,
                messages=[{"role": "system", "content": system}, *messages],
                tools=_to_openai_tools(tools) if tools else None,
                temperature=0,
            )
            message = completion.choices[0].message
            tool_calls = []
            for call in message.tool_calls or []:
                arguments = json.loads(call.function.arguments or "{}")
                tool_calls.append(
                    ToolCallResult(name=call.function.name, arguments=arguments)
                )
            return LLMResponse(content=message.content or "", tool_calls=tool_calls)
        except Exception as exc:  # network, auth, rate limit, malformed JSON
            return LLMResponse(content=f"Model call failed: {type(exc).__name__}: {exc}")