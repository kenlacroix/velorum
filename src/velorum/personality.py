"""Personality traits — emergent disposition that evolves through reflection.

Traits are bipolar floats from -1.0 to +1.0 (baseline 0) that influence
how the bot expresses its static soul. Updated during reflection cycles,
with decay toward baseline and guardrails to prevent runaway drift.

Trait dimensions:
  valence       — pessimistic/critical (-1) to optimistic/enthusiastic (+1)
  assertiveness — deferential/agreeable (-1) to confrontational/opinionated (+1)
  openness      — narrow/routine topics (-1) to scattered/exploring everything (+1)
  energy        — withdrawn/terse (-1) to hyperactive/verbose (+1)
"""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

TRAIT_NAMES = ("valence", "assertiveness", "openness", "energy")
DECAY_FACTOR = 0.95
HARD_CEILING = 0.85
MAX_DELTA = 0.3
MIN_DELTA = 0.05
GUARDRAIL_THRESHOLD = 0.6
VISIBILITY_THRESHOLD = 0.15
HISTORY_LIMIT = 50

_TRAIT_LABELS = {
    "valence": ("Pessimistic/critical", "Balanced", "Optimistic/enthusiastic"),
    "assertiveness": ("Deferential/agreeable", "Measured", "Confrontational/opinionated"),
    "openness": ("Narrow/routine topics", "Balanced", "Scattered/exploring everything"),
    "energy": ("Withdrawn/terse", "Normal", "Hyperactive/verbose"),
}


class PersonalityTraits:
    """Four bipolar trait dimensions with decay and clamping."""

    def __init__(self) -> None:
        self.valence: float = 0.0
        self.assertiveness: float = 0.0
        self.openness: float = 0.0
        self.energy: float = 0.0
        self.update_history: list[dict[str, Any]] = []

    def apply_decay(self, factor: float = DECAY_FACTOR) -> None:
        """Multiply all traits by factor, drifting toward baseline."""
        for name in TRAIT_NAMES:
            setattr(self, name, getattr(self, name) * factor)

    def apply_adjustment(self, trait: str, delta: float, reasoning: str = "") -> None:
        """Apply a single trait adjustment with clamping and history."""
        if trait not in TRAIT_NAMES:
            return

        # Clamp delta magnitude
        delta = max(-MAX_DELTA, min(MAX_DELTA, delta))

        old_value = getattr(self, trait)
        new_value = max(-HARD_CEILING, min(HARD_CEILING, old_value + delta))
        setattr(self, trait, new_value)

        self.update_history.append({
            "timestamp": time.time(),
            "trait": trait,
            "delta": round(delta, 4),
            "new_value": round(new_value, 4),
            "reasoning": reasoning,
        })

        # Trim history
        if len(self.update_history) > HISTORY_LIMIT:
            self.update_history = self.update_history[-HISTORY_LIMIT:]

    def summary_for_prompt(self) -> str:
        """Generate human-readable personality state for prompt injection.

        Only includes traits with abs > 0.15. Adds guardrail warnings
        when abs > 0.6.
        """
        lines: list[str] = []

        for name in TRAIT_NAMES:
            value = getattr(self, name)
            if abs(value) <= VISIBILITY_THRESHOLD:
                continue

            neg_label, _, pos_label = _TRAIT_LABELS[name]
            if value > 0:
                direction = pos_label.lower()
            else:
                direction = neg_label.lower()

            line = f"{name.capitalize()}: {value:+.2f} (leaning {direction})"

            if abs(value) > GUARDRAIL_THRESHOLD:
                line += " [WARNING: trait is extreme — actively moderate this tendency]"

            lines.append(line)

        if not lines:
            return ""

        return "\n".join(lines)

    def to_dict(self) -> dict[str, Any]:
        return {
            "valence": round(self.valence, 4),
            "assertiveness": round(self.assertiveness, 4),
            "openness": round(self.openness, 4),
            "energy": round(self.energy, 4),
            "update_history": self.update_history[-HISTORY_LIMIT:],
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> PersonalityTraits:
        t = cls()
        t.valence = d.get("valence", 0.0)
        t.assertiveness = d.get("assertiveness", 0.0)
        t.openness = d.get("openness", 0.0)
        t.energy = d.get("energy", 0.0)
        t.update_history = d.get("update_history", [])
        return t


class PersonalityEngine:
    """Manages personality traits and persistence."""

    def __init__(self, persist_path: Path) -> None:
        self._persist_path = persist_path
        self._traits = PersonalityTraits()
        self._load()

    def summary_for_prompt(self) -> str:
        return self._traits.summary_for_prompt()

    def apply_reflection_update(self, trait_adjustments: dict[str, Any]) -> None:
        """Apply LLM-recommended trait changes from reflection.

        Expected format:
        {
            "valence": {"delta": 0.1, "reasoning": "..."},
            "assertiveness": {"delta": -0.05, "reasoning": "..."},
        }

        Ignores deltas with abs < 0.05.
        """
        if not trait_adjustments:
            return

        applied: list[str] = []

        for trait, adjustment in trait_adjustments.items():
            if trait not in TRAIT_NAMES:
                continue
            if not isinstance(adjustment, dict):
                continue

            delta = adjustment.get("delta", 0)
            if not isinstance(delta, (int, float)):
                continue
            if abs(delta) < MIN_DELTA:
                continue

            reasoning = adjustment.get("reasoning", "")
            self._traits.apply_adjustment(trait, delta, reasoning)
            applied.append(f"{trait}={getattr(self._traits, trait):+.2f} (delta {delta:+.2f})")

        if applied:
            logger.info("Personality updated: %s", ", ".join(applied))
            self.save()

    def apply_decay(self) -> None:
        """Apply decay toward baseline and save."""
        self._traits.apply_decay()
        self.save()

    def get_traits_dict(self) -> dict[str, float]:
        """Return {trait: value} for TUI display."""
        return {name: getattr(self._traits, name) for name in TRAIT_NAMES}

    def save(self) -> None:
        self._persist_path.parent.mkdir(parents=True, exist_ok=True)
        self._persist_path.write_text(
            json.dumps(self._traits.to_dict(), indent=2)
        )

    def _load(self) -> None:
        if not self._persist_path.exists():
            return
        try:
            raw = self._persist_path.read_text()
            data = json.loads(raw)
            if data:
                self._traits = PersonalityTraits.from_dict(data)
                logger.info("Loaded personality traits: %s", {n: round(getattr(self._traits, n), 2) for n in TRAIT_NAMES})
        except (json.JSONDecodeError, KeyError):
            logger.warning("Could not load personality file, starting fresh")
