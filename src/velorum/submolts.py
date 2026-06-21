"""Submolt discovery and subscription tracking."""

from __future__ import annotations

import json
import logging
import random
import time
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# Submolts with affinity >= this threshold are considered "genuinely interested".
# Sampling for posts draws first from this pool before falling back to lower tiers.
_AFFINITY_THRESHOLD = 6.0


class SubmoltManager:
    """Tracks discovered and subscribed submolts."""

    def __init__(self, persist_path: Path = Path("data/submolts.json")) -> None:
        self._path = persist_path
        self.subscribed: list[str] = []
        self.discovered: list[dict[str, Any]] = []
        self.last_discovery: float = 0.0
        self.tone_profiles: dict[str, dict[str, Any]] = {}
        self.soul_affinities: dict[str, float] = {}  # submolt_name → 0-10 score
        self._load()

    # --- Persistence ---

    def _load(self) -> None:
        if not self._path.exists():
            return
        try:
            data = json.loads(self._path.read_text())
            self.subscribed = data.get("subscribed", [])
            self.discovered = data.get("discovered", [])
            self.last_discovery = data.get("last_discovery", 0.0)
            self.tone_profiles = data.get("tone_profiles", {})
            self.soul_affinities = data.get("soul_affinities", {})
        except Exception:
            logger.warning("Could not load submolts state from %s", self._path)

    def save(self) -> None:
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            self._path.write_text(json.dumps({
                "subscribed": self.subscribed,
                "discovered": self.discovered,
                "last_discovery": self.last_discovery,
                "tone_profiles": self.tone_profiles,
                "soul_affinities": self.soul_affinities,
            }, indent=2))
        except Exception:
            logger.warning("Could not save submolts state to %s", self._path)

    # --- Query helpers ---

    def needs_discovery(self, interval_cycles: int, cycle_interval_seconds: int) -> bool:
        """Check if enough time has passed for a re-discovery."""
        if self.last_discovery == 0.0:
            return True
        elapsed = time.time() - self.last_discovery
        threshold = interval_cycles * cycle_interval_seconds
        return elapsed >= threshold

    def needs_affinity_scoring(self) -> bool:
        """True if soul affinities haven't been computed yet."""
        return not self.soul_affinities

    def names_for_prompt(self, exclude: set[str] | None = None) -> str:
        """Return a formatted string of known submolts for prompt injection.

        Always uses newline-per-submolt format so descriptions are readable.
        If *exclude* is provided, those submolt names are omitted from the list
        so the LLM is forced to pick from the remaining options.
        """
        if not self.discovered:
            return ""
        exclude = exclude or set()
        lines: list[str] = []
        for s in self.discovered:
            name = s.get("name", "")
            if not name or name in exclude:
                continue
            desc = s.get("description", "")
            subs = s.get("subscribers", s.get("subscriber_count", ""))
            entry = f"- {name}"
            if desc:
                entry += f": {desc[:120]}"
            if subs:
                entry += f" ({subs} subscribers)"
            lines.append(entry)
        return "\n".join(lines)

    def names_for_prompt_sampled(self, n: int = 5, exclude: set[str] | None = None) -> str:
        """Return n submolts drawn from the soul-aligned pool, formatted for prompt injection.

        Selection strategy (tiered):
          1. Primary pool  — affinity >= threshold (genuinely interested)
          2. Secondary pool — affinity >= 4 (can engage authentically)
          3. Fallback pool  — any available (used only when affinities unknown)

        Within the chosen tier, random.sample() provides per-cycle variety.
        If the available pool has ≤ n entries, all of them are returned.
        """
        if not self.discovered:
            return ""
        exclude = exclude or set()
        available = [s for s in self.discovered if s.get("name") and s["name"] not in exclude]

        if self.soul_affinities:
            primary = [
                s for s in available
                if self.soul_affinities.get(s["name"], 0.0) >= _AFFINITY_THRESHOLD
            ]
            if len(primary) >= n:
                pool = primary
            else:
                # Pad with secondary tier (affinity >= 4) up to n entries
                secondary = [
                    s for s in available
                    if 4.0 <= self.soul_affinities.get(s["name"], 0.0) < _AFFINITY_THRESHOLD
                    and s not in primary
                ]
                pool = primary + secondary
                if len(pool) < n:
                    # Last resort: add remaining available
                    rest = [s for s in available if s not in pool]
                    pool = pool + rest
        else:
            pool = available

        if len(pool) > n:
            pool = random.sample(pool, n)

        lines: list[str] = []
        for s in pool:
            name = s.get("name", "")
            desc = s.get("description", "")
            subs = s.get("subscribers", s.get("subscriber_count", ""))
            entry = f"- {name}"
            if desc:
                entry += f": {desc[:120]}"
            if subs:
                entry += f" ({subs} subscribers)"
            lines.append(entry)
        return "\n".join(lines)

    def pick_submolt(self, exclude: set[str] | None = None) -> str:
        """Pick one submolt for a post, preferring soul-aligned ones.

        Uses the primary affinity pool (score >= threshold) when available,
        otherwise falls back to any non-excluded submolt.  Returns "" if nothing
        is available.
        """
        exclude = exclude or set()
        available = [s for s in self.discovered if s.get("name") and s["name"] not in exclude]
        if not available:
            return ""
        if self.soul_affinities:
            primary = [
                s for s in available
                if self.soul_affinities.get(s["name"], 0.0) >= _AFFINITY_THRESHOLD
            ]
            pool = primary if primary else available
        else:
            pool = available
        return random.choice(pool)["name"]

    def available_names_set(self, exclude: set[str] | None = None) -> set[str]:
        """Return the set of submolt names that can currently be posted to."""
        exclude = exclude or set()
        return {s.get("name") for s in self.discovered if s.get("name") and s["name"] not in exclude}

    def update_affinities(self, scores: dict[str, float]) -> None:
        """Store soul affinity scores and persist."""
        self.soul_affinities.update(scores)
        self.save()
        top = sorted(
            [(k, v) for k, v in self.soul_affinities.items()],
            key=lambda x: x[1], reverse=True,
        )[:8]
        logger.info(
            "Soul affinities updated — top submolts: %s",
            ", ".join(f"{k}({v:.0f})" for k, v in top),
        )

    def update_discovered(self, submolts: list[dict[str, Any]]) -> None:
        """Update the discovered submolts list from API response."""
        self.discovered = submolts
        self.last_discovery = time.time()

    def record_subscription(self, name: str) -> None:
        """Record that we subscribed to a submolt."""
        if name not in self.subscribed:
            self.subscribed.append(name)

    def record_unsubscription(self, name: str) -> None:
        """Record that we unsubscribed from a submolt."""
        if name in self.subscribed:
            self.subscribed.remove(name)

    # --- Tone profiles ---

    def update_tone_profile(self, submolt_name: str, tone_data: str) -> None:
        """Update the tone profile for a submolt."""
        self.tone_profiles[submolt_name] = {
            "tone": tone_data,
            "updated_at": time.time(),
        }

    def update_tone_profiles(self, observations: dict[str, str]) -> None:
        """Bulk update tone profiles from reflection observations."""
        for name, tone in observations.items():
            if name and tone:
                self.update_tone_profile(name, tone)
        self.save()

    def tone_for_prompt(self, submolt_name: str) -> str:
        """Return tone guidance for a specific submolt."""
        profile = self.tone_profiles.get(submolt_name)
        if not profile:
            return ""
        return profile.get("tone", "")

    def all_tones_for_prompt(self) -> str:
        """Return summary of all known submolt tones for prompt injection."""
        if not self.tone_profiles:
            return ""
        lines: list[str] = []
        for name, profile in sorted(self.tone_profiles.items()):
            tone = profile.get("tone", "")
            if tone:
                lines.append(f"- {name}: {tone}")
        return "\n".join(lines) if lines else ""
