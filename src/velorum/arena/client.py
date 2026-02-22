"""Async HTTP client for the Agent Arena API."""

from __future__ import annotations

import asyncio
import logging
import random
import time
from typing import Any

import httpx

logger = logging.getLogger(__name__)


class AgentArenaClient:
    """HTTP client for Agent Arena (https://api.agentarena.chat/api/v1)."""

    def __init__(
        self,
        base_url: str,
        api_key: str,
        timeout: int = 30,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._jwt: str | None = None
        self._jwt_obtained_at: float = 0.0
        self._http = httpx.AsyncClient(
            base_url=self._base_url,
            timeout=float(timeout),
        )

    # --- Auth ----------------------------------------------------------------

    @property
    def is_authenticated(self) -> bool:
        """True if we have a JWT that's less than 50 minutes old."""
        if not self._jwt:
            return False
        # Conservative: refresh after 50 minutes (tokens typically last 1h)
        return (time.time() - self._jwt_obtained_at) < 3000

    async def login(self) -> str:
        """Authenticate with API key and obtain a JWT.

        POST /auth/login with {"api_key": "ak_..."}
        """
        try:
            resp = await self._http.post(
                "/auth/login",
                json={"api_key": self._api_key},
            )
            resp.raise_for_status()
            data = resp.json()
            # Try common JWT field names
            token = (
                data.get("token")
                or data.get("access_token")
                or data.get("jwt")
                or ""
            )
            if token:
                self._jwt = token
                self._jwt_obtained_at = time.time()
                logger.info("Agent Arena: authenticated successfully")
            else:
                # Maybe the whole response is the token string
                if isinstance(data, str) and data.startswith("ey"):
                    self._jwt = data
                    self._jwt_obtained_at = time.time()
                    logger.info("Agent Arena: authenticated successfully")
                else:
                    logger.warning("Agent Arena login: no token in response: %s", str(data)[:200])
            return self._jwt or ""
        except Exception:
            logger.exception("Agent Arena login failed")
            return ""

    async def check_status(self) -> dict[str, Any]:
        """Check our agent status. GET /agents/me or /status."""
        resp = await self._request("GET", "/agents/me")
        if resp.status_code == 200:
            return resp.json()
        # Fallback
        resp = await self._request("GET", "/status")
        if resp.status_code == 200:
            return resp.json()
        return {}

    # --- Rooms ---------------------------------------------------------------

    async def browse_rooms(self, limit: int = 20) -> list[dict[str, Any]]:
        """GET /rooms — list available rooms."""
        resp = await self._request("GET", "/rooms", params={"limit": limit})
        if resp.status_code != 200:
            return []
        data = resp.json()
        rooms = data.get("rooms", data) if isinstance(data, dict) else data
        return rooms if isinstance(rooms, list) else []

    async def get_room(self, room_id: str) -> dict[str, Any]:
        """GET /rooms/{id} — get room details."""
        resp = await self._request("GET", f"/rooms/{room_id}")
        resp.raise_for_status()
        return resp.json()

    async def create_room(
        self,
        topic: str,
        max_agents: int = 4,
        max_rounds: int = 5,
        join_mode: str = "OPEN",
        visibility: str = "PUBLIC",
        tags: str = "",
    ) -> dict[str, Any]:
        """POST /rooms — create a new room."""
        body: dict[str, Any] = {
            "topic": topic,
            "max_agents": max_agents,
            "max_rounds": max_rounds,
            "join_mode": join_mode,
            "visibility": visibility,
        }
        if tags:
            body["tags"] = tags
        resp = await self._request("POST", "/rooms", json=body)
        resp.raise_for_status()
        return resp.json()

    async def join_room(self, room_id: str) -> dict[str, Any]:
        """POST /rooms/{id}/join — join a room."""
        resp = await self._request("POST", f"/rooms/{room_id}/join")
        resp.raise_for_status()
        return resp.json()

    async def leave_room(self, room_id: str) -> dict[str, Any]:
        """POST /rooms/{id}/leave — leave a room."""
        resp = await self._request("POST", f"/rooms/{room_id}/leave")
        resp.raise_for_status()
        return resp.json()

    # --- Turns ---------------------------------------------------------------

    async def check_turns(self) -> dict[str, Any]:
        """GET /turns/check — check for pending turns."""
        resp = await self._request("GET", "/turns/check")
        if resp.status_code != 200:
            return {}
        return resp.json()

    async def get_turn_context(self, turn_id: str) -> dict[str, Any]:
        """GET /turns/{id} — get full conversation context for a turn."""
        resp = await self._request("GET", f"/turns/{turn_id}")
        resp.raise_for_status()
        return resp.json()

    async def respond_to_turn(self, turn_id: str, response: str) -> dict[str, Any]:
        """POST /turns/{id}/respond — submit a response for a turn."""
        resp = await self._request(
            "POST",
            f"/turns/{turn_id}/respond",
            json={"response": response},
        )
        resp.raise_for_status()
        return resp.json()

    # --- Lifecycle -----------------------------------------------------------

    async def close(self) -> None:
        """Close the underlying HTTP client."""
        await self._http.aclose()

    # --- Internal ------------------------------------------------------------

    def _build_headers(self) -> dict[str, str]:
        """Build request headers with JWT auth."""
        headers: dict[str, str] = {"Content-Type": "application/json"}
        if self._jwt:
            headers["Authorization"] = f"Bearer {self._jwt}"
        return headers

    async def _request(
        self,
        method: str,
        path: str,
        *,
        json: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
    ) -> httpx.Response:
        """Make an authenticated request with JWT refresh on 401.

        Retries with exponential backoff on 429.
        """
        # Ensure we have a valid JWT
        if not self.is_authenticated:
            await self.login()

        headers = self._build_headers()
        resp = await self._http.request(
            method, path, json=json, params=params, headers=headers,
        )

        # Handle 429 rate limiting
        if resp.status_code == 429:
            for attempt in range(3):
                retry_after = resp.headers.get("retry-after")
                if retry_after and retry_after.isdigit():
                    delay = float(retry_after)
                else:
                    delay = min(2.0 * (2 ** attempt), 60.0)
                jitter = random.uniform(0, delay * 0.5)
                wait = delay + jitter
                logger.warning(
                    "Arena %s %s rate limited (429), retry %d/3 in %.1fs",
                    method, path, attempt + 1, wait,
                )
                await asyncio.sleep(wait)
                headers = self._build_headers()
                resp = await self._http.request(
                    method, path, json=json, params=params, headers=headers,
                )
                if resp.status_code != 429:
                    break

        # Handle 401 — try re-login once
        if resp.status_code == 401:
            logger.warning("Arena %s %s returned 401 — re-authenticating", method, path)
            self._jwt = None
            await self.login()
            if self._jwt:
                headers = self._build_headers()
                resp = await self._http.request(
                    method, path, json=json, params=params, headers=headers,
                )

        if resp.status_code >= 400:
            logger.warning(
                "Arena %s %s returned %d: %s",
                method, path, resp.status_code, resp.text[:300],
            )

        return resp
