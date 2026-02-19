"""Claude (Anthropic) LLM provider."""

from __future__ import annotations

import anthropic

from velorum.llm.base import LLMProvider


class AnthropicProvider(LLMProvider):
    def __init__(self, model: str, api_key: str) -> None:
        self._model = model
        self._client = anthropic.AsyncAnthropic(api_key=api_key)

    async def complete(self, system: str, user: str) -> str:
        response = await self._client.messages.create(
            model=self._model,
            max_tokens=1024,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        return response.content[0].text
