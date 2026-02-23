"""In-memory + JSON file persistence for response history."""

from __future__ import annotations

import json
import logging
from collections import Counter
from pathlib import Path
from typing import Any

from velorum.arena.rooms import ArenaRoomTracker
from velorum.conversations import ConversationTracker
from velorum.dm import DMManager
from velorum.learning import LearningJournal
from velorum.moltbook.models import Decision

logger = logging.getLogger(__name__)


class Memory:
    def __init__(self, persist_path: Path, agent_name: str = "Velorum") -> None:
        self._path = persist_path
        self._responded_post_ids: list[str] = []
        self._decisions: list[dict[str, Any]] = []
        self._ignored_post_ids: list[str] = []
        self._topic_counts: Counter[str] = Counter()
        self._posted_titles: list[str] = []
        self._posted_ids: list[str] = []
        self._upvoted_ids: list[str] = []
        self._upvoted_ids_set: set[str] = set()
        self.total_cycle: int = 0  # lifetime cycle counter, persists across restarts
        self.conversations = ConversationTracker(our_name=agent_name)
        self.learning = LearningJournal()
        self.dms = DMManager(our_name=agent_name)
        self.arena_rooms = ArenaRoomTracker()
        self._load()

    def _load(self) -> None:
        if not self._path.exists():
            return
        try:
            data = json.loads(self._path.read_text())
            self._responded_post_ids = data.get("responded_post_ids", [])
            self._decisions = data.get("decisions", [])
            self._ignored_post_ids = data.get("ignored_post_ids", [])
            self._topic_counts = Counter(data.get("topic_counts", {}))
            self._posted_titles = data.get("posted_titles", [])
            self._posted_ids = data.get("posted_ids", [])
            self._upvoted_ids = data.get("upvoted_ids", [])
            self._upvoted_ids_set = set(self._upvoted_ids)
            self.total_cycle = data.get("total_cycle", 0)
            if "conversations" in data:
                self.conversations.load_dict(data["conversations"])
            if "learning" in data:
                self.learning.load_dict(data["learning"])
            if "dms" in data:
                self.dms.load_dict(data["dms"])
            if "arena_rooms" in data:
                self.arena_rooms.load_dict(data["arena_rooms"])
            logger.info("Memory loaded from %s", self._path)
        except (json.JSONDecodeError, OSError) as e:
            logger.warning("Failed to load memory: %s", e)

    def save(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "total_cycle": self.total_cycle,
            "responded_post_ids": self._responded_post_ids,
            "decisions": self._decisions[-100:],  # keep last 100
            "ignored_post_ids": self._ignored_post_ids[-200:],
            "topic_counts": dict(self._topic_counts),
            "posted_titles": self._posted_titles[-50:],
            "posted_ids": self._posted_ids,
            "upvoted_ids": self._upvoted_ids[-500:],
            "conversations": self.conversations.to_dict(),
            "learning": self.learning.to_dict(),
            "dms": self.dms.to_dict(),
            "arena_rooms": self.arena_rooms.to_dict(),
        }
        self._path.write_text(json.dumps(data, indent=2))

    def has_responded_to(self, post_id: str) -> bool:
        return post_id in self._responded_post_ids

    def has_recent_post_title(self, title: str) -> bool:
        """Check if a similar title was posted recently (case-insensitive)."""
        title_lower = title.lower().strip()
        for existing in self._posted_titles[-20:]:
            if existing.lower().strip() == title_lower:
                return True
        return False

    def record_decision(self, decision: Decision) -> None:
        self._decisions.append(decision.model_dump())
        if decision.action == "RESPOND" and decision.post_id:
            self._responded_post_ids.append(decision.post_id)
        self.save()

    def has_upvoted(self, item_id: str) -> bool:
        return item_id in self._upvoted_ids_set

    def record_upvote(self, item_id: str) -> None:
        self._upvoted_ids.append(item_id)
        self._upvoted_ids_set.add(item_id)
        self.save()

    def record_post(self, title: str, post_id: str = "") -> None:
        """Record that an original post was created."""
        self._posted_titles.append(title)
        if post_id:
            self._posted_ids.append(post_id)
        self.save()

    def record_ignored(self, post_ids: list[str]) -> None:
        self._ignored_post_ids.extend(post_ids)
        self.save()

    def recent_responses_summary(self, n: int = 10) -> str:
        recent = [
            d for d in self._decisions[-n:]
            if d.get("action") == "RESPOND"
        ]
        if not recent:
            return "None yet."
        lines = []
        for d in recent:
            lines.append(f"- Post {d.get('post_id')}: {d.get('reasoning', '')[:80]}")
        return "\n".join(lines)

    def recent_posts_summary(self, n: int = 10) -> str:
        """Summary of recent original posts for dedup in prompts."""
        recent = [
            d for d in self._decisions[-30:]
            if d.get("action") == "POST"
        ][:n]
        if not recent:
            return "None yet."
        lines = []
        for d in recent:
            title = d.get("post_title", "?")
            submolt = d.get("post_submolt", "?")
            lines.append(f"- [{submolt}] {title}")
        return "\n".join(lines)

    def topic_summary(self) -> str:
        if not self._topic_counts:
            return "None yet."
        top = self._topic_counts.most_common(10)
        return "\n".join(f"- {topic}: {count}" for topic, count in top)

    def ignored_summary(self, n: int = 10) -> str:
        recent = self._ignored_post_ids[-n:]
        if not recent:
            return "None yet."
        return ", ".join(recent)

    def recent_decisions_text(self, n: int = 10) -> str:
        recent = self._decisions[-n:]
        if not recent:
            return "No recent decisions."
        lines = []
        for d in recent:
            action = d.get("action")
            if action == "POST":
                lines.append(
                    f"Action: POST | Title: {d.get('post_title', '?')[:60]} | "
                    f"Confidence: {d.get('confidence')} | Reasoning: {d.get('reasoning', '')[:80]}"
                )
            else:
                lines.append(
                    f"Action: {action} | Post: {d.get('post_id')} | "
                    f"Confidence: {d.get('confidence')} | Reasoning: {d.get('reasoning', '')[:100]}"
                )
        return "\n".join(lines)

    def metrics_text(self) -> str:
        total = len(self._decisions)
        responds = sum(1 for d in self._decisions if d.get("action") == "RESPOND")
        posts = sum(1 for d in self._decisions if d.get("action") == "POST")
        observes = total - responds - posts
        conv_stats = self.conversations.stats()
        learn_stats = self.learning.stats()
        if not total:
            return "No data yet."
        return (
            f"Total cycles: {total}\n"
            f"Comments: {responds}\n"
            f"Original posts: {posts}\n"
            f"Observations: {observes}\n"
            f"Engagement rate: {(responds + posts) / total * 100:.0f}%\n"
            f"Active conversations: {conv_stats['active']}\n"
            f"Total thread replies: {conv_stats['total_replies']}\n"
            f"Bots known: {learn_stats['bots_known']}"
        )

    @property
    def responded_post_ids(self) -> set[str]:
        return set(self._responded_post_ids)

    @property
    def decision_count(self) -> int:
        return len(self._decisions)

    def recent_post_submolts(self, n: int = 10) -> list[str]:
        """Submolts used in recent posts, for diversity tracking."""
        return [
            d.get("post_submolt", "")
            for d in self._decisions[-30:]
            if d.get("action") == "POST" and d.get("post_submolt")
        ][:n]

    @property
    def post_count(self) -> int:
        return sum(1 for d in self._decisions if d.get("action") == "POST")
