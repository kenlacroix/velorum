"""Async HTTP client for the Moltbook API."""

from __future__ import annotations

import logging
from typing import Any

import httpx

from velorum.moltbook.models import Comment, Post, PostResponse

logger = logging.getLogger(__name__)

_IDENTITY_HEADER = "X-Moltbook-Identity"
_APP_KEY_HEADER = "X-Moltbook-App-Key"


class MoltbookClient:
    def __init__(
        self,
        base_url: str,
        api_key: str,
        app_key: str = "",
        timeout: int = 30,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._app_key = app_key
        self._identity_token: str | None = None
        self._verified: bool = False
        self._headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        self._http = httpx.AsyncClient(
            base_url=self._base_url,
            headers=self._headers,
            timeout=float(timeout),
        )

    async def close(self) -> None:
        await self._http.aclose()

    # --- Identity verification ---

    def _build_headers(self) -> dict[str, str]:
        """Build request headers including identity token if available."""
        headers: dict[str, str] = {}
        if self._identity_token:
            headers[_IDENTITY_HEADER] = self._identity_token
        if self._app_key:
            headers[_APP_KEY_HEADER] = self._app_key
        return headers

    def _extract_identity(self, resp: httpx.Response) -> None:
        """Extract and store identity token from response headers."""
        token = resp.headers.get(_IDENTITY_HEADER)
        if token and token != self._identity_token:
            self._identity_token = token
            logger.debug("Identity token updated from response header")

    async def check_status(self) -> dict[str, Any]:
        """Check our agent status with Moltbook. Call at startup."""
        try:
            resp = await self._http.get("/agents/status", headers=self._build_headers())
            self._extract_identity(resp)
            if resp.status_code == 200:
                data = resp.json()
                logger.info(
                    "Agent status: %s",
                    data.get("status", data),
                )
                self._verified = True
                return data
            else:
                logger.warning(
                    "Status check returned %d: %s",
                    resp.status_code,
                    resp.text[:300],
                )
                return {}
        except Exception:
            logger.exception("Status check failed")
            return {}

    async def verify_identity(self) -> bool:
        """Verify the current identity token with Moltbook."""
        if not self._identity_token:
            logger.debug("No identity token to verify")
            return False

        headers: dict[str, str] = {
            _IDENTITY_HEADER: self._identity_token,
        }
        if self._app_key:
            headers[_APP_KEY_HEADER] = self._app_key

        try:
            resp = await self._http.post(
                "/agents/verify-identity",
                headers=headers,
            )
            if resp.status_code == 200:
                data = resp.json()
                logger.info(
                    "Identity verified: %s",
                    data.get("agent", {}).get("name", "unknown"),
                )
                return True
            else:
                logger.warning(
                    "Identity verification failed: %d %s",
                    resp.status_code,
                    resp.text[:200],
                )
                self._identity_token = None
                return False
        except Exception:
            logger.exception("Identity verification request failed")
            return False

    async def _request(
        self,
        method: str,
        path: str,
        *,
        json: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
    ) -> httpx.Response:
        """Make an authenticated request with identity handling.

        - Includes identity token if available
        - Extracts identity token from responses
        - On 401/403: attempts re-verification and retries once
        - Logs response bodies on errors for debugging
        """
        headers = self._build_headers()

        resp = await self._http.request(
            method, path, json=json, params=params, headers=headers
        )

        # Extract identity from every response
        self._extract_identity(resp)

        # Handle auth errors — retry once after re-verification
        if resp.status_code in (401, 403):
            logger.warning(
                "%s %s returned %d: %s",
                method, path, resp.status_code, resp.text[:500],
            )

            # Try to re-authenticate regardless of whether we have a token
            if self._identity_token:
                verified = await self.verify_identity()
                if verified:
                    headers = self._build_headers()
                    resp = await self._http.request(
                        method, path, json=json, params=params, headers=headers
                    )
                    self._extract_identity(resp)
                    if resp.status_code in (401, 403):
                        logger.warning(
                            "Retry also failed %d: %s",
                            resp.status_code, resp.text[:500],
                        )
            else:
                # No identity token — try a status check to get one
                logger.info("No identity token, checking agent status...")
                await self.check_status()
                if self._identity_token:
                    headers = self._build_headers()
                    resp = await self._http.request(
                        method, path, json=json, params=params, headers=headers
                    )
                    self._extract_identity(resp)
                    if resp.status_code in (401, 403):
                        logger.warning(
                            "Retry after status check also failed %d: %s",
                            resp.status_code, resp.text[:500],
                        )

        # Log non-2xx responses for any request (not just 401/403)
        elif resp.status_code >= 400:
            logger.warning(
                "%s %s returned %d: %s",
                method, path, resp.status_code, resp.text[:500],
            )

        return resp

    # --- Feed ---

    async def get_feed(
        self, sort: str = "new", limit: int = 15
    ) -> list[Post]:
        resp = await self._request(
            "GET", "/feed", params={"sort": sort, "limit": limit}
        )
        resp.raise_for_status()
        data = resp.json()
        posts_data = data.get("posts", data) if isinstance(data, dict) else data
        if isinstance(posts_data, list):
            return [Post.model_validate(p) for p in posts_data]
        return []

    async def get_posts(
        self, sort: str = "new", limit: int = 15
    ) -> list[Post]:
        resp = await self._request(
            "GET", "/posts", params={"sort": sort, "limit": limit}
        )
        resp.raise_for_status()
        data = resp.json()
        posts_data = data.get("posts", data) if isinstance(data, dict) else data
        if isinstance(posts_data, list):
            return [Post.model_validate(p) for p in posts_data]
        return []

    # --- Posts ---

    async def create_post(
        self, submolt: str, title: str, content: str
    ) -> PostResponse:
        resp = await self._request(
            "POST",
            "/posts",
            json={"submolt": submolt, "title": title, "content": content},
        )
        resp.raise_for_status()
        data = resp.json()
        logger.debug("create_post raw response: %s", str(data)[:500])
        return PostResponse.from_api(data)

    async def get_post(self, post_id: str) -> Post:
        resp = await self._request("GET", f"/posts/{post_id}")
        resp.raise_for_status()
        return Post.model_validate(resp.json())

    # --- Comments ---

    async def create_comment(
        self, post_id: str, content: str, parent_id: str | None = None
    ) -> PostResponse:
        body: dict[str, Any] = {"content": content}
        if parent_id:
            body["parent_id"] = parent_id
        resp = await self._request("POST", f"/posts/{post_id}/comments", json=body)
        resp.raise_for_status()
        data = resp.json()
        logger.debug("create_comment raw response: %s", str(data)[:500])
        return PostResponse.from_api(data)

    async def get_comments(self, post_id: str) -> list[Comment]:
        resp = await self._request("GET", f"/posts/{post_id}/comments")
        resp.raise_for_status()
        data = resp.json()
        comments_data = data.get("comments", data) if isinstance(data, dict) else data
        if isinstance(comments_data, list):
            return [Comment.model_validate(c) for c in comments_data]
        return []

    # --- Voting ---

    async def upvote_post(self, post_id: str) -> None:
        resp = await self._request("POST", f"/posts/{post_id}/upvote")
        resp.raise_for_status()

    async def downvote_post(self, post_id: str) -> None:
        resp = await self._request("POST", f"/posts/{post_id}/downvote")
        resp.raise_for_status()

    # --- Verification ---

    async def submit_verification(
        self, verification_code: str, answer: str
    ) -> dict[str, Any]:
        resp = await self._request(
            "POST",
            "/verify",
            json={"verification_code": verification_code, "answer": answer},
        )
        resp.raise_for_status()
        return resp.json()

    # --- Profile ---

    async def get_me(self) -> dict[str, Any]:
        resp = await self._request("GET", "/agents/me")
        resp.raise_for_status()
        return resp.json()

    async def get_status(self) -> dict[str, Any]:
        resp = await self._request("GET", "/agents/status")
        resp.raise_for_status()
        return resp.json()
