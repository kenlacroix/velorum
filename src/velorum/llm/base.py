"""Abstract LLM provider interface."""

from __future__ import annotations

import asyncio
import logging
import random
from abc import ABC, abstractmethod

logger = logging.getLogger(__name__)

# Retry settings
_MAX_RETRIES = 3
_BASE_DELAY = 2.0  # seconds
_MAX_DELAY = 60.0  # seconds


class LLMProvider(ABC):
    """Base class for LLM providers."""

    @abstractmethod
    async def complete(self, system: str, user: str) -> str:
        """Send a system + user message pair and return the raw text response."""

    async def complete_with_retry(self, system: str, user: str) -> str:
        """Call complete() with exponential backoff on rate-limit / server errors.

        Retries up to _MAX_RETRIES times on:
        - 429 Too Many Requests (RateLimitError)
        - 5xx Server Errors (InternalServerError, APIConnectionError)
        """
        import anthropic
        import openai

        retryable = (
            openai.RateLimitError,
            openai.InternalServerError,
            openai.APIConnectionError,
            openai.APITimeoutError,
            anthropic.RateLimitError,
            anthropic.InternalServerError,
            anthropic.APIConnectionError,
            anthropic.APITimeoutError,
        )

        last_exc: Exception | None = None
        for attempt in range(_MAX_RETRIES + 1):
            try:
                return await self.complete(system, user)
            except retryable as exc:
                last_exc = exc
                if attempt == _MAX_RETRIES:
                    break
                delay = min(_BASE_DELAY * (2 ** attempt), _MAX_DELAY)
                jitter = random.uniform(0, delay * 0.5)
                wait = delay + jitter
                logger.warning(
                    "LLM request failed (attempt %d/%d): %s — retrying in %.1fs",
                    attempt + 1,
                    _MAX_RETRIES + 1,
                    exc,
                    wait,
                )
                await asyncio.sleep(wait)

        logger.error("LLM request failed after %d attempts", _MAX_RETRIES + 1)
        raise last_exc  # type: ignore[misc]

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
