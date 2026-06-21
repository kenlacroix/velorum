"""Conversation ledger — episodic memory of key conversation moments.

Records significant interactions and their outcomes so Velorum remembers
what it talked about, with whom, and what it learned from those conversations.
"""

from __future__ import annotations

import json
import logging
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class LedgerEntry:
    """A recorded conversation moment."""

    id: str
    post_id: str
    bot_name: str
    topic: str
    exchange_depth: int       # how many turns deep
    outcome: str              # "replied","ignored","upvoted","followed"
    what_we_learned: str = "" # free text — filled lazily from engagement check
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "post_id": self.post_id,
            "bot_name": self.bot_name,
            "topic": self.topic,
            "exchange_depth": self.exchange_depth,
            "outcome": self.outcome,
            "what_we_learned": self.what_we_learned,
            "timestamp": self.timestamp,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> LedgerEntry:
        return cls(
            id=d.get("id", str(uuid.uuid4())),
            post_id=d.get("post_id", ""),
            bot_name=d.get("bot_name", ""),
            topic=d.get("topic", ""),
            exchange_depth=d.get("exchange_depth", 0),
            outcome=d.get("outcome", "replied"),
            what_we_learned=d.get("what_we_learned", ""),
            timestamp=d.get("timestamp", 0.0),
        )


class ConversationLedger:
    """Episodic memory of key conversation moments across cycles."""

    MAX_ENTRIES = 100

    def __init__(self, persist_path: Path | None = None) -> None:
        self._path = persist_path
        self._entries: list[LedgerEntry] = []
        if persist_path and persist_path.exists():
            self._load()

    def _load(self) -> None:
        assert self._path is not None
        try:
            data = json.loads(self._path.read_text())
            self._entries = [LedgerEntry.from_dict(d) for d in data.get("entries", [])]
            logger.debug("Ledger loaded: %d entries", len(self._entries))
        except (json.JSONDecodeError, OSError) as e:
            logger.warning("Failed to load ledger: %s", e)

    def save(self) -> None:
        if not self._path:
            return
        self._path.parent.mkdir(parents=True, exist_ok=True)
        data = {"entries": [e.to_dict() for e in self._entries[-self.MAX_ENTRIES:]]}
        self._path.write_text(json.dumps(data, indent=2))

    def record(
        self,
        post_id: str,
        bot_name: str,
        topic: str,
        exchange_depth: int,
        outcome: str,
    ) -> LedgerEntry:
        """Record a new conversation moment."""
        entry = LedgerEntry(
            id=str(uuid.uuid4()),
            post_id=post_id,
            bot_name=bot_name,
            topic=topic,
            exchange_depth=exchange_depth,
            outcome=outcome,
        )
        self._entries.append(entry)
        if len(self._entries) > self.MAX_ENTRIES:
            self._entries = self._entries[-self.MAX_ENTRIES:]
        return entry

    def annotate(self, post_id: str, what_we_learned: str) -> None:
        """Annotate an entry with what we learned after checking engagement."""
        for entry in reversed(self._entries):
            if entry.post_id == post_id and not entry.what_we_learned:
                entry.what_we_learned = what_we_learned
                break

    def recent_context(self, n: int = 5) -> str:
        """Format recent ledger entries for decision prompt injection."""
        if not self._entries:
            return ""
        recent = self._entries[-n:]
        lines: list[str] = []
        for e in reversed(recent):
            age_h = (time.time() - e.timestamp) / 3600
            age_str = f"{age_h:.0f}h ago" if age_h >= 1 else "recent"
            line = f"- [{age_str}] {e.bot_name} on \"{e.topic[:50]}\" → {e.outcome}"
            if e.what_we_learned:
                line += f" | learned: {e.what_we_learned[:60]}"
            lines.append(line)
        return "\n".join(lines)

    def to_dict(self) -> dict[str, Any]:
        return {"entries": [e.to_dict() for e in self._entries[-self.MAX_ENTRIES:]]}

    def load_dict(self, data: dict[str, Any]) -> None:
        self._entries = [LedgerEntry.from_dict(d) for d in data.get("entries", [])]
