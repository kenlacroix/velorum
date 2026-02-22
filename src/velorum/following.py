"""Strategic following tracker — manages who we follow on Moltbook."""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class FollowingTracker:
    """Tracks which agents we're following with timestamps."""

    def __init__(self, persist_path: Path = Path("data/following.json")) -> None:
        self._path = persist_path
        self._following: dict[str, float] = {}  # name_lower → timestamp
        self._load()

    def is_following(self, name: str) -> bool:
        return name.lower() in self._following

    def add(self, name: str) -> None:
        self._following[name.lower()] = time.time()

    def remove(self, name: str) -> None:
        self._following.pop(name.lower(), None)

    def names(self) -> list[str]:
        return list(self._following.keys())

    @property
    def count(self) -> int:
        return len(self._following)

    def summary_for_prompt(self) -> str:
        if not self._following:
            return "Not following anyone yet."
        names = ", ".join(self._following.keys())
        return f"Following ({self.count}): {names}"

    def save(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(json.dumps(self._following, indent=2))

    def _load(self) -> None:
        if not self._path.exists():
            return
        try:
            data = json.loads(self._path.read_text())
            if isinstance(data, dict):
                self._following = data
        except (json.JSONDecodeError, OSError) as e:
            logger.warning("Failed to load following data: %s", e)

    def to_dict(self) -> dict[str, Any]:
        return dict(self._following)

    def load_dict(self, data: dict[str, Any]) -> None:
        self._following = {k: float(v) for k, v in data.items()}
