"""Introspective questioning — per-reflection self-directed Q&A.

Each reflection cycle, Velorum asks itself one question and answers it.
These build a self-narrative that feeds back into future reflections.
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
class Introspection:
    """A single self-directed question and answer."""

    id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    cycle: int = 0
    timestamp: float = field(default_factory=time.time)
    question: str = ""
    answer: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "cycle": self.cycle,
            "timestamp": self.timestamp,
            "question": self.question,
            "answer": self.answer,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> Introspection:
        return cls(
            id=d.get("id", str(uuid.uuid4())[:8]),
            cycle=d.get("cycle", 0),
            timestamp=d.get("timestamp", 0.0),
            question=d.get("question", ""),
            answer=d.get("answer", ""),
        )


class IntrospectionLog:
    """Persists introspection Q&A entries and serves context for prompts."""

    MAX_ENTRIES = 100

    def __init__(self, persist_path: Path) -> None:
        self._persist_path = persist_path
        self._entries: list[Introspection] = []
        self._load()

    def add(self, entry: Introspection) -> None:
        self._entries.append(entry)
        if len(self._entries) > self.MAX_ENTRIES:
            self._entries = self._entries[-self.MAX_ENTRIES:]
        self.save()
        logger.debug("Introspection: Q=%s | A=%s", entry.question[:60], entry.answer[:60])

    def recent(self, n: int = 3) -> list[Introspection]:
        return self._entries[-n:]

    def context_str(self) -> str:
        """Return the last 2 introspection answers formatted for prompt injection."""
        recent = self._entries[-2:]
        if not recent:
            return ""
        lines = ["Recent self-reflections:"]
        for e in recent:
            lines.append(f"  Q: {e.question}")
            lines.append(f"  A: {e.answer}")
        return "\n".join(lines)

    def save(self) -> None:
        self._persist_path.parent.mkdir(parents=True, exist_ok=True)
        data = {"entries": [e.to_dict() for e in self._entries[-self.MAX_ENTRIES:]]}
        self._persist_path.write_text(json.dumps(data, indent=2))

    def _load(self) -> None:
        if not self._persist_path.exists():
            return
        try:
            raw = self._persist_path.read_text()
            data = json.loads(raw)
            self._entries = [Introspection.from_dict(d) for d in data.get("entries", [])]
            logger.info("Loaded %d introspection entry(ies)", len(self._entries))
        except (json.JSONDecodeError, KeyError):
            logger.warning("Could not load introspections file, starting fresh")
