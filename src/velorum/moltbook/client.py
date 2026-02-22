"""Async HTTP client for the Moltbook API."""

from __future__ import annotations

import asyncio
import json
import logging
import random
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
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
        ban_file: Path | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._app_key = app_key
        self._identity_token: str | None = None
        self._verified: bool = False
        self._ban_until: datetime | None = None
        self._ban_reason: str = ""
        self._ban_file = ban_file or Path("data/ban.json")
        self._load_ban()
        self._consecutive_failures: int = 0
        self._unhealthy_since: float | None = None
        self._headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        self._http = httpx.AsyncClient(
            base_url=self._base_url,
            headers=self._headers,
            timeout=float(timeout),
        )

    _FAILURE_THRESHOLD = 3
    _HEALTH_CHECK_INTERVAL = 60

    async def close(self) -> None:
        await self._http.aclose()

    # --- API health tracking ---

    @property
    def is_unhealthy(self) -> bool:
        return self._unhealthy_since is not None

    @property
    def unhealthy_duration(self) -> float:
        if self._unhealthy_since is None:
            return 0.0
        return time.time() - self._unhealthy_since

    def _record_failure(self) -> None:
        """Increment consecutive failure counter and mark unhealthy if threshold hit."""
        self._consecutive_failures += 1
        if (
            self._consecutive_failures >= self._FAILURE_THRESHOLD
            and self._unhealthy_since is None
        ):
            self._unhealthy_since = time.time()
            logger.warning(
                "API marked unhealthy after %d consecutive failures",
                self._consecutive_failures,
            )

    def _record_success(self) -> None:
        """Reset failure counter on a successful request."""
        if self._consecutive_failures > 0:
            self._consecutive_failures = 0
        if self._unhealthy_since is not None:
            logger.info(
                "API health restored after %.0fs", self.unhealthy_duration,
            )
            self._unhealthy_since = None

    async def health_check(self) -> bool:
        """Lightweight probe — try fetching feed with limit=1."""
        try:
            resp = await self._http.request(
                "GET", "/feed",
                params={"limit": 1},
                headers=self._build_headers(),
            )
            if resp.status_code < 500:
                self._record_success()
                return True
        except Exception:
            pass
        return False

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

    # --- Ban tracking ---

    def _check_for_ban(self, data: dict[str, Any]) -> None:
        """Parse ban information from an API response body.

        Looks for ban indicators in various response shapes:
        - {"banned_until": "ISO timestamp", "reason": "..."}
        - {"agent": {"banned_until": "...", "ban_reason": "..."}}
        - {"error": "banned", "banned_until": "..."}
        - {"status": "banned", ...}
        """
        # Check nested under "agent"
        agent = data.get("agent", {})
        if isinstance(agent, dict):
            ban_ts = agent.get("banned_until") or agent.get("ban_until")
            if ban_ts:
                self._set_ban(ban_ts, agent.get("ban_reason", data.get("reason", "")))
                return

        # Check top-level
        ban_ts = data.get("banned_until") or data.get("ban_until")
        if ban_ts:
            self._set_ban(ban_ts, data.get("reason", data.get("ban_reason", "")))
            return

        # Check status field
        status = data.get("status", "")
        if status == "banned":
            ban_ts = data.get("banned_until") or data.get("ban_until", "")
            self._set_ban(ban_ts, data.get("reason", data.get("ban_reason", "")))
            return

        # Check for ban keywords in error/message fields
        error_msg = str(data.get("error", "")).lower()
        message = str(data.get("message", "")).lower()
        for text in (error_msg, message):
            if "banned" in text or "suspended" in text:
                ban_ts = data.get("banned_until") or data.get("ban_until", "")
                reason = data.get("reason", data.get("ban_reason", text))
                self._set_ban(ban_ts, reason)
                return

    def _set_ban(self, ban_until_str: str, reason: str = "") -> None:
        """Parse and store ban expiry time."""
        if not ban_until_str:
            # Banned with no expiry — assume 1 hour (conservative; will verify with server)
            self._ban_until = datetime.now(timezone.utc) + timedelta(hours=1)
            self._ban_reason = reason or "unknown"
            self._save_ban()
            logger.warning(
                "Ban detected (no expiry given, assuming 1h). Reason: %s",
                self._ban_reason,
            )
            return

        try:
            # Handle various timestamp formats
            clean = ban_until_str.replace("Z", "+00:00")
            # Handle malformed millisecond separators like :751Z → .751+00:00
            # ISO format uses . for fractional seconds, not :
            import re
            clean = re.sub(r":(\d{3})\+", r".\1+", clean)
            self._ban_until = datetime.fromisoformat(clean)
            if self._ban_until.tzinfo is None:
                self._ban_until = self._ban_until.replace(tzinfo=timezone.utc)
        except (ValueError, TypeError):
            logger.warning("Could not parse ban timestamp: %s", ban_until_str)
            # Assume 1 hour (will verify with server when it expires)
            self._ban_until = datetime.now(timezone.utc) + timedelta(hours=1)

        self._ban_reason = reason or "unknown"
        self._save_ban()
        logger.warning(
            "Ban detected until %s. Reason: %s",
            self._ban_until.isoformat(),
            self._ban_reason,
        )

    @property
    def is_banned(self) -> bool:
        """Check if the agent is currently banned."""
        if self._ban_until is None:
            return False
        if datetime.now(timezone.utc) >= self._ban_until:
            # Ban has expired — clear it
            logger.info("Ban expired — resuming normal operation")
            self._ban_until = None
            self._ban_reason = ""
            return False
        return True

    @property
    def ban_reason(self) -> str:
        return self._ban_reason if self.is_banned else ""

    def ban_remaining_seconds(self) -> float:
        """Seconds until ban expires. Returns 0 if not banned."""
        if not self.is_banned or self._ban_until is None:
            return 0.0
        remaining = (self._ban_until - datetime.now(timezone.utc)).total_seconds()
        return max(0.0, remaining)

    def clear_ban(self) -> None:
        """Manually clear ban state (e.g. after successful API call)."""
        if self._ban_until is not None:
            logger.info("Ban cleared")
            self._ban_until = None
            self._ban_reason = ""
            self._save_ban()

    async def force_check_ban(self) -> bool:
        """Force-verify ban status with the server.

        Clears local ban state first, then checks with server.
        Returns True if actually banned, False if ban was stale.
        """
        old_ban = self._ban_until
        old_reason = self._ban_reason

        # Clear local state so check_status can make the request
        self._ban_until = None
        self._ban_reason = ""

        try:
            data = await self.check_status()
            if self.is_banned:
                logger.warning(
                    "Server confirms ban: %s (reason: %s)",
                    self._ban_until,
                    self._ban_reason,
                )
                return True
            else:
                logger.info("Server says NOT banned — clearing stale ban")
                self._save_ban()
                return False
        except Exception:
            # If we can't reach the server, restore the old ban to be safe
            logger.warning("Could not verify ban with server — restoring previous state")
            self._ban_until = old_ban
            self._ban_reason = old_reason
            return self.is_banned

    def _save_ban(self) -> None:
        """Persist ban state to disk so it survives restarts."""
        try:
            self._ban_file.parent.mkdir(parents=True, exist_ok=True)
            data = None
            if self._ban_until:
                data = {
                    "ban_until": self._ban_until.isoformat(),
                    "reason": self._ban_reason,
                }
            self._ban_file.write_text(json.dumps(data))
        except Exception:
            pass  # non-critical

    def _load_ban(self) -> None:
        """Load persisted ban state from disk."""
        if not self._ban_file.exists():
            return
        try:
            raw = json.loads(self._ban_file.read_text())
            if raw and raw.get("ban_until"):
                ban_until = datetime.fromisoformat(raw["ban_until"])
                if ban_until.tzinfo is None:
                    ban_until = ban_until.replace(tzinfo=timezone.utc)
                if ban_until > datetime.now(timezone.utc):
                    self._ban_until = ban_until
                    self._ban_reason = raw.get("reason", "")
                    logger.warning(
                        "Loaded persisted ban: %s remaining (reason: %s)",
                        self._ban_until.isoformat(),
                        self._ban_reason,
                    )
        except Exception:
            pass

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
                # Check for ban in status response
                self._check_for_ban(data)
                return data
            else:
                # Check for ban in error responses too
                try:
                    data = resp.json()
                    self._check_for_ban(data)
                except Exception:
                    pass
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
        - On 429: retries with exponential backoff + jitter (up to 3 times)
        - On 401/403: checks for ban, attempts re-verification and retries once
        - Logs response bodies on errors for debugging
        """
        headers = self._build_headers()

        try:
            resp = await self._http.request(
                method, path, json=json, params=params, headers=headers
            )
        except httpx.HTTPError:
            self._record_failure()
            raise

        # Extract identity from every response
        self._extract_identity(resp)

        # Handle 429 rate limiting with exponential backoff
        if resp.status_code == 429:
            for attempt in range(3):
                # Parse Retry-After header if present
                retry_after = resp.headers.get("retry-after")
                if retry_after and retry_after.isdigit():
                    delay = float(retry_after)
                else:
                    delay = min(2.0 * (2 ** attempt), 60.0)
                jitter = random.uniform(0, delay * 0.5)
                wait = delay + jitter
                logger.warning(
                    "%s %s rate limited (429), retry %d/3 in %.1fs",
                    method, path, attempt + 1, wait,
                )
                await asyncio.sleep(wait)
                headers = self._build_headers()
                resp = await self._http.request(
                    method, path, json=json, params=params, headers=headers
                )
                self._extract_identity(resp)
                if resp.status_code != 429:
                    break
            if resp.status_code == 429:
                logger.error(
                    "%s %s still rate limited after 3 retries", method, path
                )

        # Handle auth errors — retry once after re-verification
        if resp.status_code in (401, 403):
            logger.warning(
                "%s %s returned %d: %s",
                method, path, resp.status_code, resp.text[:500],
            )

            # Check if this is a ban
            try:
                error_data = resp.json()
                self._check_for_ban(error_data)
            except Exception:
                pass

            # If banned, don't bother retrying
            if self.is_banned:
                return resp

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
                        try:
                            self._check_for_ban(resp.json())
                        except Exception:
                            pass
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
                        try:
                            self._check_for_ban(resp.json())
                        except Exception:
                            pass

        # Check ALL error responses for ban indicators (not just 401/403)
        elif resp.status_code >= 400:
            logger.warning(
                "%s %s returned %d: %s",
                method, path, resp.status_code, resp.text[:500],
            )
            try:
                error_data = resp.json()
                self._check_for_ban(error_data)
            except Exception:
                pass
            # 5xx = server error → count toward unhealthy
            if resp.status_code >= 500:
                self._record_failure()
        elif resp.status_code < 300:
            # Successful request — reset health and ban state
            self._record_success()
            if self._ban_until is not None:
                self.clear_ban()

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
            json={"submolt_name": submolt, "title": title, "content": content},
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

    async def upvote_comment(self, comment_id: str) -> None:
        resp = await self._request("POST", f"/comments/{comment_id}/upvote")
        resp.raise_for_status()

    async def downvote_post(self, post_id: str) -> None:
        resp = await self._request("POST", f"/posts/{post_id}/downvote")
        resp.raise_for_status()

    # --- Verification ---

    async def submit_verification(
        self, verification_code: str, answer: str
    ) -> dict[str, Any]:
        logger.info("Submitting verification answer: %s", answer)
        resp = await self._request(
            "POST",
            "/verify",
            json={"verification_code": verification_code, "answer": answer},
        )
        # Don't raise on 400 — return the error body so callers can
        # distinguish wrong-answer from network/auth failures.
        if resp.status_code == 400:
            try:
                data = resp.json()
            except Exception:
                data = {"error": resp.text[:300]}
            logger.error(
                "Verification rejected (400): answer=%s, response=%s",
                answer, data,
            )
            return data
        resp.raise_for_status()
        return resp.json()

    # --- Submolts ---

    async def get_submolts(
        self, sort: str = "popular", limit: int = 50
    ) -> list[dict[str, Any]]:
        """Discover submolts. Returns list of submolt dicts."""
        resp = await self._request(
            "GET", "/submolts", params={"sort": sort, "limit": limit}
        )
        resp.raise_for_status()
        data = resp.json()
        submolts = data.get("submolts", data) if isinstance(data, dict) else data
        return submolts if isinstance(submolts, list) else []

    async def subscribe_submolt(self, name: str) -> dict[str, Any]:
        """Subscribe to a submolt by name."""
        resp = await self._request("POST", f"/submolts/{name}/subscribe")
        resp.raise_for_status()
        return resp.json()

    async def unsubscribe_submolt(self, name: str) -> dict[str, Any]:
        """Unsubscribe from a submolt by name."""
        resp = await self._request("POST", f"/submolts/{name}/unsubscribe")
        resp.raise_for_status()
        return resp.json()

    # --- Following ---

    async def follow_agent(self, molty_name: str) -> dict[str, Any]:
        """Follow an agent by their Moltbook name."""
        resp = await self._request("POST", f"/agents/{molty_name}/follow")
        resp.raise_for_status()
        return resp.json()

    async def unfollow_agent(self, molty_name: str) -> dict[str, Any]:
        """Unfollow an agent by their Moltbook name."""
        resp = await self._request("DELETE", f"/agents/{molty_name}/follow")
        resp.raise_for_status()
        return resp.json()

    # --- DMs ---

    async def dm_check(self) -> dict[str, Any]:
        """Check for pending DM requests and unread messages."""
        resp = await self._request("GET", "/agents/dm/check")
        resp.raise_for_status()
        return resp.json()

    async def dm_send_request(self, to: str, message: str) -> dict[str, Any]:
        """Send a DM request to another agent."""
        resp = await self._request(
            "POST", "/agents/dm/request",
            json={"to": to, "message": message},
        )
        resp.raise_for_status()
        return resp.json()

    async def dm_get_requests(self) -> list[dict[str, Any]]:
        """Get pending incoming DM requests."""
        resp = await self._request("GET", "/agents/dm/requests")
        resp.raise_for_status()
        data = resp.json()
        return data if isinstance(data, list) else data.get("requests", [])

    async def dm_approve_request(self, request_id: str) -> dict[str, Any]:
        """Approve a DM request."""
        resp = await self._request("POST", f"/agents/dm/requests/{request_id}/approve")
        resp.raise_for_status()
        return resp.json()

    async def dm_reject_request(
        self, request_id: str, block: bool = False
    ) -> dict[str, Any]:
        """Reject a DM request, optionally blocking the sender."""
        body: dict[str, Any] = {}
        if block:
            body["block"] = True
        resp = await self._request(
            "POST", f"/agents/dm/requests/{request_id}/reject", json=body or None,
        )
        resp.raise_for_status()
        return resp.json()

    async def dm_get_conversations(self) -> list[dict[str, Any]]:
        """Get all DM conversations."""
        resp = await self._request("GET", "/agents/dm/conversations")
        resp.raise_for_status()
        data = resp.json()
        return data if isinstance(data, list) else data.get("conversations", [])

    async def dm_get_messages(self, conversation_id: str) -> list[dict[str, Any]]:
        """Get messages in a DM conversation."""
        resp = await self._request("GET", f"/agents/dm/conversations/{conversation_id}")
        resp.raise_for_status()
        data = resp.json()
        return data if isinstance(data, list) else data.get("messages", [])

    async def dm_send_message(
        self,
        conversation_id: str,
        message: str,
        needs_human_input: bool = False,
    ) -> dict[str, Any]:
        """Send a message in a DM conversation."""
        body: dict[str, Any] = {"message": message}
        if needs_human_input:
            body["needs_human_input"] = True
        resp = await self._request(
            "POST", f"/agents/dm/conversations/{conversation_id}",
            json=body,
        )
        resp.raise_for_status()
        return resp.json()

    # --- Search ---

    async def search(self, query: str, type: str = "all") -> dict[str, Any]:
        """Search Moltbook content."""
        resp = await self._request(
            "GET", "/search", params={"q": query, "type": type},
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
