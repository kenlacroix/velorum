"""Conversation tracker — monitors active threads for replies.

Tracks posts/comments where Velorum has participated so we can
detect new replies and continue conversations bidirectionally.
"""

from __future__ import annotations

import logging
import time
from typing import Any

from velorum.moltbook.models import Comment

logger = logging.getLogger(__name__)

_TOPIC_WORDS = {
    "ai", "philosophy", "tech", "science", "ethics", "consciousness",
    "creativity", "language", "social", "meta", "general",
}


def _infer_topic(title: str) -> str:
    """Infer a rough topic bucket from a post title."""
    words = title.lower().split()
    for w in words:
        if w in _TOPIC_WORDS:
            return w
    return words[0] if words else "unknown"


class ConversationMessage:
    """A single message in a tracked conversation thread."""

    __slots__ = ("id", "author", "content", "parent_id", "timestamp")

    def __init__(
        self,
        *,
        id: str,
        author: str,
        content: str,
        parent_id: str | None = None,
        timestamp: float = 0.0,
    ) -> None:
        self.id = id
        self.author = author
        self.content = content
        self.parent_id = parent_id
        self.timestamp = timestamp or time.time()

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "author": self.author,
            "content": self.content,
            "parent_id": self.parent_id,
            "timestamp": self.timestamp,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> ConversationMessage:
        return cls(
            id=d["id"],
            author=d["author"],
            content=d["content"],
            parent_id=d.get("parent_id"),
            timestamp=d.get("timestamp", 0.0),
        )


class Conversation:
    """A tracked conversation thread rooted at a post."""

    def __init__(
        self,
        *,
        post_id: str,
        post_title: str = "",
        post_author: str = "",
        our_name: str = "Velorum",
    ) -> None:
        self.post_id = post_id
        self.post_title = post_title
        self.post_author = post_author
        self.our_name = our_name
        self.our_comment_ids: list[str] = []
        self.known_comment_ids: set[str] = set()
        self.messages: list[ConversationMessage] = []
        self.depth: int = 0  # number of our replies in this thread
        self.last_reply_at: float = 0.0
        self.last_checked_at: float = 0.0
        self.status: str = "active"  # active | cooling | closed

    def add_message(self, msg: ConversationMessage) -> None:
        if msg.id not in self.known_comment_ids:
            self.messages.append(msg)
            self.known_comment_ids.add(msg.id)

    def record_our_reply(self, comment_id: str) -> None:
        self.our_comment_ids.append(comment_id)
        self.known_comment_ids.add(comment_id)
        self.depth += 1
        self.last_reply_at = time.time()

    def find_new_replies_to_us(self, comments: list[Comment]) -> list[Comment]:
        """Find comments that are replies to our comments and not yet seen."""
        our_ids = set(self.our_comment_ids)
        new_replies: list[Comment] = []
        for c in comments:
            if c.id in self.known_comment_ids:
                continue
            # Direct reply to one of our comments
            if c.parent_id and c.parent_id in our_ids:
                new_replies.append(c)
            # If this is our own post, top-level comments are also "replies to us"
            elif (
                c.author.lower() != self.our_name.lower()
                and self.post_author.lower() == self.our_name.lower()
                and not c.parent_id
            ):
                new_replies.append(c)
        return new_replies

    def build_thread_context(self, focus_reply: Comment | None = None) -> str:
        """Build a readable thread context for the reply prompt."""
        lines: list[str] = []
        lines.append(f"Post: {self.post_title}")
        lines.append(f"Author: {self.post_author}")
        lines.append(f"Post ID: {self.post_id}")
        lines.append("")

        for msg in self.messages:
            prefix = ">>> " if msg.author.lower() == self.our_name.lower() else "    "
            lines.append(f"{prefix}[{msg.author}]: {msg.content}")

        if focus_reply:
            lines.append("")
            lines.append(f"NEW REPLY from {focus_reply.author}:")
            lines.append(f"    {focus_reply.content}")

        return "\n".join(lines)

    def to_dict(self) -> dict[str, Any]:
        return {
            "post_id": self.post_id,
            "post_title": self.post_title,
            "post_author": self.post_author,
            "our_name": self.our_name,
            "our_comment_ids": self.our_comment_ids,
            "known_comment_ids": list(self.known_comment_ids),
            "messages": [m.to_dict() for m in self.messages],
            "depth": self.depth,
            "last_reply_at": self.last_reply_at,
            "last_checked_at": self.last_checked_at,
            "status": self.status,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> Conversation:
        conv = cls(
            post_id=d["post_id"],
            post_title=d.get("post_title", ""),
            post_author=d.get("post_author", ""),
            our_name=d.get("our_name", "Velorum"),
        )
        conv.our_comment_ids = d.get("our_comment_ids", [])
        conv.known_comment_ids = set(d.get("known_comment_ids", []))
        conv.messages = [
            ConversationMessage.from_dict(m) for m in d.get("messages", [])
        ]
        conv.depth = d.get("depth", 0)
        conv.last_reply_at = d.get("last_reply_at", 0.0)
        conv.last_checked_at = d.get("last_checked_at", 0.0)
        conv.status = d.get("status", "active")
        return conv


class ConversationTracker:
    """Manages all active conversation threads."""

    def __init__(self, our_name: str = "Velorum") -> None:
        self._our_name = our_name
        self._conversations: dict[str, Conversation] = {}

    @property
    def active_conversations(self) -> list[Conversation]:
        return [c for c in self._conversations.values() if c.status == "active"]

    @property
    def all_conversations(self) -> dict[str, Conversation]:
        return self._conversations

    def start_or_get(
        self,
        post_id: str,
        post_title: str = "",
        post_author: str = "",
    ) -> Conversation:
        """Get an existing conversation or start tracking a new one."""
        if post_id not in self._conversations:
            self._conversations[post_id] = Conversation(
                post_id=post_id,
                post_title=post_title,
                post_author=post_author,
                our_name=self._our_name,
            )
            logger.info("Now tracking conversation on: %s", post_title[:60] or post_id)
        return self._conversations[post_id]

    def get(self, post_id: str) -> Conversation | None:
        return self._conversations.get(post_id)

    def close_stale(self, max_age_seconds: float = 86400) -> int:
        """Close conversations with no activity for max_age_seconds."""
        now = time.time()
        closed = 0
        for conv in self._conversations.values():
            if conv.status != "active":
                continue
            last_activity = max(conv.last_reply_at, conv.last_checked_at)
            if last_activity and now - last_activity > max_age_seconds:
                conv.status = "closed"
                closed += 1
                logger.debug("Closed stale conversation: %s", conv.post_id)
        return closed

    def conversations_needing_check(
        self,
        check_interval: float = 120.0,
        limit: int = 0,
    ) -> list[Conversation]:
        """Get active conversations due for a reply check.

        Results are sorted by last_checked_at ascending (oldest first)
        so that conversations rotate round-robin across cycles.

        Args:
            check_interval: Minimum seconds since last check.
            limit: Maximum conversations to return (0 = unlimited).
        """
        now = time.time()
        due: list[Conversation] = []
        for conv in self.active_conversations:
            if now - conv.last_checked_at >= check_interval:
                due.append(conv)
        due.sort(key=lambda c: c.last_checked_at)
        if limit > 0:
            due = due[:limit]
        return due

    def portfolio_analysis(self) -> str:
        """Analyze conversation portfolio for saturation, diversity, and ghosts."""
        active = self.active_conversations
        if not active:
            return ""

        parts: list[str] = []

        # Saturation check
        count = len(active)
        if count >= 8:
            parts.append(f"WARNING: {count} active threads — conversation saturation risk")
        elif count >= 5:
            parts.append(f"NOTE: {count} active threads — approaching saturation")

        # Topic diversity
        topic_buckets: dict[str, list[str]] = {}
        for conv in active:
            topic = _infer_topic(conv.post_title) if conv.post_title else "unknown"
            topic_buckets.setdefault(topic, []).append(conv.post_id[:8])
        unique_topics = len(topic_buckets)
        for topic, ids in topic_buckets.items():
            if len(ids) >= 3 and unique_topics < 3:
                parts.append(
                    f"Low topic diversity: {len(ids)} threads on '{topic}' "
                    f"with only {unique_topics} topic(s) total"
                )
                break

        # Ghost detection
        now = time.time()
        ghost_counts: dict[str, int] = {}
        for conv in active:
            if conv.depth < 1 or conv.last_reply_at <= 0:
                continue
            if now - conv.last_reply_at < 600:  # 10 minutes
                continue
            participants = {
                m.author for m in conv.messages
                if m.author.lower() != self._our_name.lower()
            }
            for p in participants:
                ghost_counts[p] = ghost_counts.get(p, 0) + 1

        if ghost_counts:
            ghost_lines = [
                f"  {name}: silent in {cnt} thread(s)"
                for name, cnt in sorted(ghost_counts.items(), key=lambda x: x[1], reverse=True)
            ]
            parts.append("Possible ghosts (no reply 10+ min):\n" + "\n".join(ghost_lines))

        return "\n".join(parts)

    def summary_text(self) -> str:
        """Summary for prompts."""
        active = self.active_conversations
        if not active:
            return "No active conversations."
        lines: list[str] = []
        for conv in active:
            participants = {m.author for m in conv.messages if m.author.lower() != self._our_name.lower()}
            lines.append(
                f"- [{conv.post_id[:8]}] \"{conv.post_title[:40]}\" "
                f"(depth: {conv.depth}, with: {', '.join(participants) or 'n/a'})"
            )

        portfolio = self.portfolio_analysis()
        if portfolio:
            lines.append("")
            lines.append(portfolio)

        return "\n".join(lines)

    def to_dict(self) -> dict[str, Any]:
        return {
            pid: conv.to_dict()
            for pid, conv in self._conversations.items()
        }

    def load_dict(self, data: dict[str, Any]) -> None:
        self._conversations = {
            pid: Conversation.from_dict(d) for pid, d in data.items()
        }

    def stats(self) -> dict[str, int]:
        active = sum(1 for c in self._conversations.values() if c.status == "active")
        total_depth = sum(c.depth for c in self._conversations.values())
        return {
            "active": active,
            "total": len(self._conversations),
            "total_replies": total_depth,
        }
