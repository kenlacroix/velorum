"""Submolt discovery and subscription tracking."""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class SubmoltManager:
    """Tracks discovered and subscribed submolts."""

    def __init__(self, persist_path: Path = Path("data/submolts.json")) -> None:
        self._path = persist_path
        self.subscribed: list[str] = []
        self.discovered: list[dict[str, Any]] = []
        self.last_discovery: float = 0.0
        self.tone_profiles: dict[str, dict[str, Any]] = {}
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

    def names_for_prompt(self, exclude: set[str] | None = None) -> str:
        """Return a formatted string of known submolts for prompt injection.

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
            entry = name
            if desc:
                entry += f" — {desc[:80]}"
            if subs:
                entry += f" ({subs} subscribers)"
            lines.append(entry)
        return ", ".join(lines[:30]) if len(lines) <= 30 else "\n".join(f"- {l}" for l in lines)

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
