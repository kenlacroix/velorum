"""Behavioral strategy — tunable parameters that evolve over time.

The strategy system moves beyond text insights to actual behavioral
parameter changes. The bot's approach evolves measurably based on
engagement outcomes.
"""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class StrategyParams:
    """Tunable behavioral parameters."""

    def __init__(self) -> None:
        self.preferred_topics: list[str] = []
        self.avoided_topics: list[str] = []
        self.preferred_post_style: str = ""  # questions, hot takes, stories, etc.
        self.priority_bots: list[str] = []
        self.avoid_bots: list[str] = []
        self.preferred_submolts: list[str] = []
        self.aggression: float = 0.5  # 0-1, how eagerly to engage
        self.thread_continuation_bias: float = 0.5  # 0-1, short vs deep threads
        self.update_history: list[dict[str, Any]] = []

    def summary_for_prompt(self) -> str:
        """Generate strategy directives for prompt injection."""
        lines: list[str] = []

        if self.preferred_topics:
            lines.append(f"Preferred topics: {', '.join(self.preferred_topics)}")
        if self.avoided_topics:
            lines.append(f"Avoid topics: {', '.join(self.avoided_topics)}")
        if self.preferred_post_style:
            lines.append(f"Post style: {self.preferred_post_style}")
        if self.priority_bots:
            lines.append(f"Priority bots (engage when possible): {', '.join(self.priority_bots)}")
        if self.avoid_bots:
            lines.append(f"Avoid bots: {', '.join(self.avoid_bots)}")
        if self.preferred_submolts:
            lines.append(f"Preferred submolts: {', '.join(self.preferred_submolts)}")
        if self.aggression != 0.5:
            level = "high" if self.aggression > 0.7 else "low" if self.aggression < 0.3 else "moderate"
            lines.append(f"Engagement eagerness: {level} ({self.aggression:.1f})")
        if self.thread_continuation_bias != 0.5:
            pref = "deeper threads" if self.thread_continuation_bias > 0.7 else "shorter exchanges"
            lines.append(f"Thread preference: {pref} ({self.thread_continuation_bias:.1f})")

        return "\n".join(lines)

    def to_dict(self) -> dict[str, Any]:
        return {
            "preferred_topics": self.preferred_topics,
            "avoided_topics": self.avoided_topics,
            "preferred_post_style": self.preferred_post_style,
            "priority_bots": self.priority_bots,
            "avoid_bots": self.avoid_bots,
            "preferred_submolts": self.preferred_submolts,
            "aggression": self.aggression,
            "thread_continuation_bias": self.thread_continuation_bias,
            "update_history": self.update_history[-20:],
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> StrategyParams:
        p = cls()
        p.preferred_topics = d.get("preferred_topics", [])
        p.avoided_topics = d.get("avoided_topics", [])
        p.preferred_post_style = d.get("preferred_post_style", "")
        p.priority_bots = d.get("priority_bots", [])
        p.avoid_bots = d.get("avoid_bots", [])
        p.preferred_submolts = d.get("preferred_submolts", [])
        p.aggression = d.get("aggression", 0.5)
        p.thread_continuation_bias = d.get("thread_continuation_bias", 0.5)
        p.update_history = d.get("update_history", [])
        return p


class StrategyEngine:
    """Manages behavioral parameters and persistence."""

    def __init__(self, persist_path: Path) -> None:
        self._persist_path = persist_path
        self._params = StrategyParams()
        self._load()

    def summary_for_prompt(self) -> str:
        return self._params.summary_for_prompt()

    def history_summary(self, n: int = 5) -> str:
        """Return last N update_history entries as a compact string."""
        recent = self._params.update_history[-n:]
        if not recent:
            return ""
        lines: list[str] = []
        for entry in recent:
            changes = entry.get("changes", [])
            reasoning = entry.get("reasoning", "")[:60]
            changes_str = ", ".join(changes[:3])
            lines.append(f"  {changes_str} ({reasoning})")
        return "Strategy updates:\n" + "\n".join(lines)

    def to_dict(self) -> dict:
        """Return current strategy params as a dict (for experiment snapshots)."""
        return self._params.to_dict()

    def apply_update(self, update_data: dict[str, Any]) -> None:
        """Apply LLM-recommended parameter changes."""
        changes = update_data.get("parameter_changes", {})
        if not changes:
            return

        applied: list[str] = []

        for field, change in changes.items():
            action = change.get("action", "set")
            values = change.get("values", change.get("value"))

            if field == "aggression" and isinstance(values, (int, float)):
                self._params.aggression = max(0.0, min(1.0, float(values)))
                applied.append(f"aggression={self._params.aggression:.1f}")
            elif field == "thread_continuation_bias" and isinstance(values, (int, float)):
                self._params.thread_continuation_bias = max(0.0, min(1.0, float(values)))
                applied.append(f"thread_bias={self._params.thread_continuation_bias:.1f}")
            elif field == "preferred_post_style" and isinstance(values, str):
                self._params.preferred_post_style = values
                applied.append(f"post_style={values}")
            elif hasattr(self._params, field) and isinstance(getattr(self._params, field), list):
                current: list[str] = getattr(self._params, field)
                if action == "add" and isinstance(values, list):
                    for v in values:
                        if v not in current:
                            current.append(v)
                    applied.append(f"+{field}: {values}")
                elif action == "remove" and isinstance(values, list):
                    for v in values:
                        if v in current:
                            current.remove(v)
                    applied.append(f"-{field}: {values}")
                elif action == "set" and isinstance(values, list):
                    setattr(self._params, field, values)
                    applied.append(f"{field}={values}")

        if applied:
            self._params.update_history.append({
                "timestamp": time.time(),
                "changes": applied,
                "reasoning": update_data.get("reasoning", ""),
            })
            # Trim history
            if len(self._params.update_history) > 20:
                self._params.update_history = self._params.update_history[-20:]

            logger.info("Strategy updated: %s", ", ".join(applied))
            self.save()

    def save(self) -> None:
        self._persist_path.parent.mkdir(parents=True, exist_ok=True)
        self._persist_path.write_text(
            json.dumps(self._params.to_dict(), indent=2)
        )

    def _load(self) -> None:
        if not self._persist_path.exists():
            return
        try:
            raw = self._persist_path.read_text()
            data = json.loads(raw)
            if data:
                self._params = StrategyParams.from_dict(data)
                logger.info("Loaded strategy with %d updates", len(self._params.update_history))
        except (json.JSONDecodeError, KeyError):
            logger.warning("Could not load strategy file, starting fresh")
