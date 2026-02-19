"""Abstract LLM provider interface."""

from __future__ import annotations

from abc import ABC, abstractmethod


class LLMProvider(ABC):
    """Base class for LLM providers."""

    @abstractmethod
    async def complete(self, system: str, user: str) -> str:
        """Send a system + user message pair and return the raw text response."""

    @classmethod
    def create(
        cls,
        provider: str,
        model: str,
        api_key: str,
        max_tokens: int = 1024,
    ) -> LLMProvider:
        """Factory method to create an LLM provider by name."""
        if provider == "anthropic":
            from velorum.llm.anthropic import AnthropicProvider
            return AnthropicProvider(model=model, api_key=api_key, max_tokens=max_tokens)
        elif provider == "openai":
            from velorum.llm.openai import OpenAIProvider
            return OpenAIProvider(model=model, api_key=api_key, max_tokens=max_tokens)
        else:
            raise ValueError(f"Unknown LLM provider: {provider}")
