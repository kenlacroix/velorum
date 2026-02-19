"""Moltbook agent registration flow."""

from __future__ import annotations

import logging
from typing import Any

import httpx

logger = logging.getLogger(__name__)


async def register_agent(
    base_url: str, name: str, description: str
) -> dict[str, Any]:
    """Register a new agent on Moltbook.

    Returns the registration response containing api_key, claim_url,
    and verification_code.
    """
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(
            f"{base_url}/agents/register",
            json={"name": name, "description": description},
        )
        resp.raise_for_status()
        data = resp.json()
        logger.info("Agent registered: %s", name)
        return data
