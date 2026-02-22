"""Web search via Tavily API — enrichment for post creation."""

from __future__ import annotations

import logging

import httpx

logger = logging.getLogger(__name__)

TAVILY_SEARCH_URL = "https://api.tavily.com/search"


class TavilySearch:
    """Lightweight async wrapper around the Tavily search API."""

    def __init__(self, api_key: str, timeout: int = 10) -> None:
        self._api_key = api_key
        self._timeout = timeout

    async def search(self, query: str, max_results: int = 3) -> list[dict]:
        """Search Tavily and return a list of result dicts.

        Each result contains: title, url, content (snippet).
        Returns an empty list on failure.
        """
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            resp = await client.post(
                TAVILY_SEARCH_URL,
                json={
                    "api_key": self._api_key,
                    "query": query,
                    "max_results": max_results,
                    "search_depth": "basic",
                },
            )
            resp.raise_for_status()
            data = resp.json()

        results = []
        for item in data.get("results", []):
            results.append({
                "title": item.get("title", ""),
                "url": item.get("url", ""),
                "content": item.get("content", ""),
            })
        return results[:max_results]


def format_search_results(results: list[dict]) -> str:
    """Format search results into a prompt-ready string."""
    if not results:
        return ""
    lines = []
    for r in results:
        title = r.get("title", "Untitled")
        url = r.get("url", "")
        content = r.get("content", "")[:300]
        lines.append(f"- **{title}** ({url})\n  {content}")
    return "\n".join(lines)
