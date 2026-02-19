"""OpenAI LLM provider."""

from __future__ import annotations

import openai

from velorum.llm.base import LLMProvider


class OpenAIProvider(LLMProvider):
    def __init__(self, model: str, api_key: str) -> None:
        self._model = model
        self._client = openai.AsyncOpenAI(api_key=api_key)

    async def complete(self, system: str, user: str) -> str:
        response = await self._client.chat.completions.create(
            model=self._model,
            max_tokens=1024,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        )
        return response.choices[0].message.content or ""
