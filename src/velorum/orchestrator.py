"""Orchestrator — action queue and cycle state for structured execution.

Provides structured scan → queue → prioritized execution for the main loop,
plus a CycleState dataclass that the TUI Brain panel polls for live status.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any


@dataclass
class QueuedAction:
    """An action waiting to be executed, with priority (lower = higher priority)."""

    priority: int             # lower = higher priority
    action_type: str          # "reply_to_own_post","reply_thread","hot_comment","like","follow","post"
    description: str          # human-readable for UI
    context: dict[str, Any]   # post_id, author, etc.
    created_at: float = field(default_factory=time.time)

    def __lt__(self, other: QueuedAction) -> bool:
        return self.priority < other.priority


class ActionQueue:
    """Priority queue of actions to execute this cycle."""

    def __init__(self) -> None:
        self._queue: list[QueuedAction] = []

    def push(self, action: QueuedAction) -> None:
        """Add an action to the queue (insertion-sorted by priority)."""
        self._queue.append(action)
        self._queue.sort(key=lambda a: a.priority)

    def pop_batch(self, action_type: str, max_n: int = 5) -> list[QueuedAction]:
        """Remove and return up to max_n actions of the given type."""
        matching = [a for a in self._queue if a.action_type == action_type][:max_n]
        for a in matching:
            self._queue.remove(a)
        return matching

    def pop_all(self, max_priority: int | None = None) -> list[QueuedAction]:
        """Remove and return all actions, optionally filtered by max priority threshold."""
        if max_priority is not None:
            batch = [a for a in self._queue if a.priority <= max_priority]
            self._queue = [a for a in self._queue if a.priority > max_priority]
        else:
            batch = list(self._queue)
            self._queue = []
        return batch

    def peek_summary(self) -> list[str]:
        """Human-readable descriptions of queued actions (for OrchestratorPanel)."""
        return [a.description for a in self._queue]

    def clear(self) -> None:
        self._queue.clear()

    def __len__(self) -> int:
        return len(self._queue)


@dataclass
class CycleState:
    """Shared mutable state updated by the main loop, polled by the TUI panel."""

    current_phase: str = "Idle"
    queued_actions: list[str] = field(default_factory=list)
    hot_posts: list[dict[str, Any]] = field(default_factory=list)
    entropy_score: float = 1.0
    top_insight: str = ""
    reflect_in: int = 0
    soul_in: int = 0
    elite_count: int = 0
    regular_count: int = 0
    passive_count: int = 0
    unknown_count: int = 0
    last_cycle: int = 0
    last_updated: float = 0.0

    def set_phase(self, phase: str) -> None:
        self.current_phase = phase
        self.last_updated = time.time()

    def set_queue(self, summaries: list[str]) -> None:
        self.queued_actions = summaries
        self.last_updated = time.time()

    def set_hot_posts(self, posts: list[dict[str, Any]]) -> None:
        self.hot_posts = posts
        self.last_updated = time.time()

    def update_bot_tiers(self, counts: dict[str, int]) -> None:
        self.elite_count = counts.get("elite", 0)
        self.regular_count = counts.get("regular", 0)
        self.passive_count = counts.get("passive", 0)
        self.unknown_count = counts.get("unknown", 0)
        self.last_updated = time.time()

    def update_learning(self, entropy: float, top_insight: str) -> None:
        self.entropy_score = entropy
        self.top_insight = top_insight
        self.last_updated = time.time()

    def update_countdowns(self, reflect_in: int, soul_in: int, cycle: int) -> None:
        self.reflect_in = reflect_in
        self.soul_in = soul_in
        self.last_cycle = cycle
        self.last_updated = time.time()
