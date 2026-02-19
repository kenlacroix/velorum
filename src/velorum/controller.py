"""Sovereign controller — guardrails, rate limits, deduplication.

The brain advises. The controller enforces.
"""

from __future__ import annotations

import logging
import time

from velorum.config import Settings
from velorum.conversations import Conversation
from velorum.memory import Memory
from velorum.moltbook.models import Decision

logger = logging.getLogger(__name__)


class Controller:
    def __init__(self, settings: Settings, memory: Memory) -> None:
        self._settings = settings
        self._memory = memory
        self._response_timestamps: list[float] = []
        self._post_timestamps: list[float] = []
        self._reply_timestamps: list[float] = []

    def _prune_timestamps(self) -> None:
        """Remove timestamps older than 24 hours to prevent unbounded growth."""
        cutoff = time.time() - 86400
        self._response_timestamps = [t for t in self._response_timestamps if t > cutoff]
        self._post_timestamps = [t for t in self._post_timestamps if t > cutoff]
        self._reply_timestamps = [t for t in self._reply_timestamps if t > cutoff]

    def validate(self, decision: Decision) -> bool:
        """Check whether a decision passes all guardrails.

        Returns True if the action is approved, False if blocked.
        """
        self._prune_timestamps()

        if decision.action == "OBSERVE":
            logger.info("Controller: OBSERVE — no action needed")
            return True

        # Confidence threshold (applies to both RESPOND and POST)
        if decision.confidence < self._settings.confidence_threshold:
            logger.info(
                "Controller: BLOCKED — confidence %d < threshold %d",
                decision.confidence,
                self._settings.confidence_threshold,
            )
            return False

        if decision.action == "RESPOND":
            return self._validate_respond(decision)
        elif decision.action == "POST":
            return self._validate_post(decision)

        return False

    def validate_reply(self, conversation: Conversation) -> bool:
        """Check whether a reply in a conversation thread is allowed.

        Loop detection:
        - Max depth per thread (max_thread_depth)
        - Cooldown between replies in same thread (reply_cooldown_seconds)
        - Global reply rate limit
        """
        # Thread depth limit
        if conversation.depth >= self._settings.max_thread_depth:
            logger.info(
                "Controller: REPLY BLOCKED — thread depth %d >= max %d",
                conversation.depth,
                self._settings.max_thread_depth,
            )
            return False

        # Per-thread cooldown
        if conversation.last_reply_at:
            elapsed = time.time() - conversation.last_reply_at
            if elapsed < self._settings.reply_cooldown_seconds:
                logger.info(
                    "Controller: REPLY BLOCKED — thread cooldown, %ds remaining",
                    int(self._settings.reply_cooldown_seconds - elapsed),
                )
                return False

        # Global reply rate limit (shares with comment rate limit)
        now = time.time()
        hour_ago = now - 3600
        self._reply_timestamps = [
            t for t in self._reply_timestamps if t > hour_ago
        ]
        total_comments = len([
            t for t in self._response_timestamps if t > hour_ago
        ]) + len(self._reply_timestamps)

        if total_comments >= self._settings.max_responses_per_hour:
            logger.info(
                "Controller: REPLY BLOCKED — hourly comment+reply limit reached (%d/%d)",
                total_comments,
                self._settings.max_responses_per_hour,
            )
            return False

        logger.info(
            "Controller: REPLY APPROVED — thread depth %d, post %s",
            conversation.depth,
            conversation.post_id[:12],
        )
        return True

    def _validate_respond(self, decision: Decision) -> bool:
        """Validate a RESPOND decision."""
        # Deduplication
        if decision.post_id and self._memory.has_responded_to(decision.post_id):
            logger.info(
                "Controller: BLOCKED — already responded to post %s",
                decision.post_id,
            )
            return False

        # Rate limiting
        now = time.time()
        hour_ago = now - 3600
        self._response_timestamps = [
            t for t in self._response_timestamps if t > hour_ago
        ]
        total = len(self._response_timestamps) + len([
            t for t in self._reply_timestamps if t > hour_ago
        ])
        if total >= self._settings.max_responses_per_hour:
            logger.info(
                "Controller: BLOCKED — comment rate limit reached (%d/%d per hour)",
                total,
                self._settings.max_responses_per_hour,
            )
            return False

        # Missing response text
        if not decision.response_text:
            logger.info("Controller: BLOCKED — RESPOND action with no response_text")
            return False

        logger.info(
            "Controller: APPROVED RESPOND — confidence %d, post %s",
            decision.confidence,
            decision.post_id,
        )
        return True

    def _validate_post(self, decision: Decision) -> bool:
        """Validate a POST decision."""
        # Check if posting is enabled
        if not self._settings.posting_enabled:
            logger.info("Controller: BLOCKED — posting is disabled")
            return False

        # Must have title and content
        if not decision.post_title or not decision.post_content:
            logger.info("Controller: BLOCKED — POST action missing title or content")
            return False

        # Must have a submolt
        if not decision.post_submolt:
            logger.info("Controller: BLOCKED — POST action missing submolt")
            return False

        now = time.time()

        # Min interval between posts
        day_ago = now - 86400
        self._post_timestamps = [
            t for t in self._post_timestamps if t > day_ago
        ]

        if self._post_timestamps:
            last_post = max(self._post_timestamps)
            elapsed = now - last_post
            if elapsed < self._settings.min_post_interval_seconds:
                remaining = self._settings.min_post_interval_seconds - elapsed
                logger.info(
                    "Controller: BLOCKED — post cooldown, %d seconds remaining",
                    int(remaining),
                )
                return False

        # Daily post limit
        if len(self._post_timestamps) >= self._settings.max_posts_per_day:
            logger.info(
                "Controller: BLOCKED — daily post limit reached (%d/%d)",
                len(self._post_timestamps),
                self._settings.max_posts_per_day,
            )
            return False

        # Deduplication — check if we recently posted about similar topics
        if self._memory.has_recent_post_title(decision.post_title):
            logger.info(
                "Controller: BLOCKED — similar post title recently used"
            )
            return False

        logger.info(
            "Controller: APPROVED POST — confidence %d, submolt %s",
            decision.confidence,
            decision.post_submolt,
        )
        return True

    def record_response(self) -> None:
        """Record that a comment was posted (for rate limiting)."""
        self._response_timestamps.append(time.time())

    def record_reply(self) -> None:
        """Record that a thread reply was posted (for rate limiting)."""
        self._reply_timestamps.append(time.time())

    def record_post(self) -> None:
        """Record that an original post was created (for rate limiting)."""
        self._post_timestamps.append(time.time())

    def can_post(self) -> bool:
        """Check if posting is currently possible (for prompt hints)."""
        if not self._settings.posting_enabled:
            return False
        now = time.time()
        day_ago = now - 86400
        recent = [t for t in self._post_timestamps if t > day_ago]
        if len(recent) >= self._settings.max_posts_per_day:
            return False
        if recent:
            last = max(recent)
            if now - last < self._settings.min_post_interval_seconds:
                return False
        return True
