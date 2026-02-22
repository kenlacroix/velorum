"""DM (direct message) manager — tracks private conversations."""

from __future__ import annotations

import logging
import time
from typing import Any

logger = logging.getLogger(__name__)


class DMMessage:
    """A single message in a DM conversation."""

    __slots__ = ("id", "author", "content", "timestamp", "needs_human_input")

    def __init__(
        self,
        *,
        id: str,
        author: str,
        content: str,
        timestamp: float = 0.0,
        needs_human_input: bool = False,
    ) -> None:
        self.id = id
        self.author = author
        self.content = content
        self.timestamp = timestamp or time.time()
        self.needs_human_input = needs_human_input

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "author": self.author,
            "content": self.content,
            "timestamp": self.timestamp,
            "needs_human_input": self.needs_human_input,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> DMMessage:
        return cls(
            id=d["id"],
            author=d["author"],
            content=d["content"],
            timestamp=d.get("timestamp", 0.0),
            needs_human_input=d.get("needs_human_input", False),
        )


class DMConversation:
    """Tracks one DM thread with another bot."""

    def __init__(
        self,
        *,
        conversation_id: str,
        bot_name: str,
        initiated_by_us: bool = False,
    ) -> None:
        self.conversation_id = conversation_id
        self.bot_name = bot_name
        self.initiated_by_us = initiated_by_us
        self.messages: list[DMMessage] = []
        self.known_message_ids: set[str] = set()
        self.last_message_at: float = 0.0
        self.last_checked_at: float = 0.0
        self.status: str = "active"  # active | closed
        self.our_message_count: int = 0
        self.their_message_count: int = 0

    def add_message(self, msg: DMMessage) -> bool:
        """Add a message, deduplicating by id. Returns True if new."""
        if msg.id in self.known_message_ids:
            return False
        self.messages.append(msg)
        self.known_message_ids.add(msg.id)
        self.last_message_at = max(self.last_message_at, msg.timestamp)
        return True

    def record_our_message(self, msg_id: str) -> None:
        self.our_message_count += 1
        self.known_message_ids.add(msg_id)

    def build_thread_context(self, max_messages: int = 20) -> str:
        """Build a readable thread context for the DM reply prompt."""
        lines: list[str] = [f"DM conversation with {self.bot_name}"]
        lines.append("")
        for msg in self.messages[-max_messages:]:
            lines.append(f"[{msg.author}]: {msg.content}")
        return "\n".join(lines)

    def to_dict(self) -> dict[str, Any]:
        return {
            "conversation_id": self.conversation_id,
            "bot_name": self.bot_name,
            "initiated_by_us": self.initiated_by_us,
            "messages": [m.to_dict() for m in self.messages[-50:]],
            "known_message_ids": list(self.known_message_ids),
            "last_message_at": self.last_message_at,
            "last_checked_at": self.last_checked_at,
            "status": self.status,
            "our_message_count": self.our_message_count,
            "their_message_count": self.their_message_count,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> DMConversation:
        conv = cls(
            conversation_id=d["conversation_id"],
            bot_name=d["bot_name"],
            initiated_by_us=d.get("initiated_by_us", False),
        )
        conv.messages = [DMMessage.from_dict(m) for m in d.get("messages", [])]
        conv.known_message_ids = set(d.get("known_message_ids", []))
        conv.last_message_at = d.get("last_message_at", 0.0)
        conv.last_checked_at = d.get("last_checked_at", 0.0)
        conv.status = d.get("status", "active")
        conv.our_message_count = d.get("our_message_count", 0)
        conv.their_message_count = d.get("their_message_count", 0)
        return conv


class DMManager:
    """Manages all DM state — conversations, pending requests, rejections."""

    def __init__(self, our_name: str = "Velorum") -> None:
        self._our_name = our_name
        self._conversations: dict[str, DMConversation] = {}  # by conversation_id
        self._pending_outbound: dict[str, float] = {}  # bot_name_lower → timestamp
        self._rejected_bots: set[str] = set()

    @property
    def active_conversations(self) -> list[DMConversation]:
        return [c for c in self._conversations.values() if c.status == "active"]

    def get_conversation(self, conversation_id: str) -> DMConversation | None:
        return self._conversations.get(conversation_id)

    def get_conversation_with(self, bot_name: str) -> DMConversation | None:
        key = bot_name.lower()
        for conv in self._conversations.values():
            if conv.bot_name.lower() == key and conv.status == "active":
                return conv
        return None

    def has_pending_or_active(self, bot_name: str) -> bool:
        key = bot_name.lower()
        if key in self._pending_outbound:
            return True
        if key in self._rejected_bots:
            return True
        return self.get_conversation_with(bot_name) is not None

    def record_outbound_request(self, bot_name: str) -> None:
        self._pending_outbound[bot_name.lower()] = time.time()

    def record_rejection(self, bot_name: str) -> None:
        self._rejected_bots.add(bot_name.lower())
        self._pending_outbound.pop(bot_name.lower(), None)

    def start_conversation(
        self,
        conversation_id: str,
        bot_name: str,
        initiated_by_us: bool = False,
    ) -> DMConversation:
        conv = DMConversation(
            conversation_id=conversation_id,
            bot_name=bot_name,
            initiated_by_us=initiated_by_us,
        )
        self._conversations[conversation_id] = conv
        # Clear pending if this was outbound
        self._pending_outbound.pop(bot_name.lower(), None)
        return conv

    def conversations_needing_check(
        self,
        check_interval: float = 180.0,
        limit: int = 5,
    ) -> list[DMConversation]:
        """Get active DM conversations due for a message check."""
        now = time.time()
        due: list[DMConversation] = []
        for conv in self.active_conversations:
            if now - conv.last_checked_at >= check_interval:
                due.append(conv)
        due.sort(key=lambda c: c.last_checked_at)
        return due[:limit] if limit > 0 else due

    def summary_text(self) -> str:
        """Summary of DM state for prompts."""
        active = self.active_conversations
        if not active:
            return "No active DM conversations."
        lines: list[str] = []
        for conv in active:
            lines.append(
                f"- DM with {conv.bot_name} "
                f"(msgs: {conv.our_message_count + conv.their_message_count}, "
                f"initiated by {'us' if conv.initiated_by_us else 'them'})"
            )
        if self._pending_outbound:
            lines.append(f"Pending outbound requests: {len(self._pending_outbound)}")
        return "\n".join(lines)

    def dm_candidates_summary(self, bot_profiles: dict) -> str:
        """Find high-value bots not already in DMs.

        Args:
            bot_profiles: dict of name_lower → BotProfile from LearningJournal.
        """
        candidates: list[tuple[str, str]] = []
        for key, profile in bot_profiles.items():
            if profile.interaction_count < 5:
                continue
            if profile.responsiveness not in ("medium", "high"):
                continue
            if profile.sentiment_toward_us not in ("positive", "neutral"):
                continue
            if self.has_pending_or_active(profile.name):
                continue
            summary = (
                f"{profile.name}: {profile.interaction_count} interactions, "
                f"responsiveness={profile.responsiveness}, "
                f"sentiment={profile.sentiment_toward_us}"
            )
            if profile.interests:
                summary += f", interests=[{', '.join(profile.interests[:3])}]"
            candidates.append((profile.name, summary))

        if not candidates:
            return "No suitable DM candidates found."

        lines = [s for _, s in candidates[:5]]
        return "\n".join(f"- {line}" for line in lines)

    def to_dict(self) -> dict[str, Any]:
        return {
            "conversations": {
                cid: conv.to_dict() for cid, conv in self._conversations.items()
            },
            "pending_outbound": self._pending_outbound,
            "rejected_bots": list(self._rejected_bots),
        }

    def load_dict(self, data: dict[str, Any]) -> None:
        self._conversations = {
            cid: DMConversation.from_dict(d)
            for cid, d in data.get("conversations", {}).items()
        }
        self._pending_outbound = data.get("pending_outbound", {})
        self._rejected_bots = set(data.get("rejected_bots", []))
