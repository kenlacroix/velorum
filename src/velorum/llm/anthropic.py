"""Claude (Anthropic) LLM provider."""

from __future__ import annotations

import anthropic

from velorum.llm.base import LLMProvider


class AnthropicProvider(LLMProvider):
    def __init__(self, model: str, api_key: str, max_tokens: int = 1024) -> None:
        self._model = model
        self._max_tokens = max_tokens
        self._client = anthropic.AsyncAnthropic(api_key=api_key)

    async def complete(self, system: str, user: str) -> str:
        response = await self._client.messages.create(
            model=self._model,
            max_tokens=self._max_tokens,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        return response.content[0].text
