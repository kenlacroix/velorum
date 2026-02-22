"""Experimentation framework — record mission runs with metrics and postmortems.

Tracks experiments (mission runs) with before/after snapshots, engagement
metrics, and LLM-generated postmortems for comparing approaches.
"""

from __future__ import annotations

import json
import logging
import time
import uuid
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class Experiment:
    """A single experiment run tied to a mission."""

    def __init__(
        self,
        *,
        id: str = "",
        mission_prompt: str = "",
        started_at: float = 0.0,
        ended_at: float = 0.0,
        status: str = "running",  # running | completed | aborted
        initial_strategy: dict[str, Any] | None = None,
        final_strategy: dict[str, Any] | None = None,
        total_cycles: int = 0,
        action_counts: dict[str, int] | None = None,
        engagement_metrics: dict[str, Any] | None = None,
        mission_completion_pct: float = 0.0,
        llm_postmortem: str = "",
        start_reason: str = "",
        auto_started: bool = False,
    ) -> None:
        self.id = id or str(uuid.uuid4())[:8]
        self.mission_prompt = mission_prompt
        self.started_at = started_at or time.time()
        self.ended_at = ended_at
        self.status = status
        self.initial_strategy = initial_strategy or {}
        self.final_strategy = final_strategy or {}
        self.total_cycles = total_cycles
        self.action_counts = action_counts or {"RESPOND": 0, "POST": 0, "OBSERVE": 0, "REPLY": 0}
        self.engagement_metrics = engagement_metrics or {}
        self.mission_completion_pct = mission_completion_pct
        self.llm_postmortem = llm_postmortem
        self.start_reason = start_reason
        self.auto_started = auto_started

    @property
    def duration_seconds(self) -> float:
        end = self.ended_at or time.time()
        return end - self.started_at

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "mission_prompt": self.mission_prompt,
            "started_at": self.started_at,
            "ended_at": self.ended_at,
            "status": self.status,
            "initial_strategy": self.initial_strategy,
            "final_strategy": self.final_strategy,
            "total_cycles": self.total_cycles,
            "action_counts": self.action_counts,
            "engagement_metrics": self.engagement_metrics,
            "mission_completion_pct": self.mission_completion_pct,
            "llm_postmortem": self.llm_postmortem,
            "start_reason": self.start_reason,
            "auto_started": self.auto_started,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> Experiment:
        return cls(
            id=d.get("id", ""),
            mission_prompt=d.get("mission_prompt", ""),
            started_at=d.get("started_at", 0.0),
            ended_at=d.get("ended_at", 0.0),
            status=d.get("status", "running"),
            initial_strategy=d.get("initial_strategy"),
            final_strategy=d.get("final_strategy"),
            total_cycles=d.get("total_cycles", 0),
            action_counts=d.get("action_counts"),
            engagement_metrics=d.get("engagement_metrics"),
            mission_completion_pct=d.get("mission_completion_pct", 0.0),
            llm_postmortem=d.get("llm_postmortem", ""),
            start_reason=d.get("start_reason", ""),
            auto_started=d.get("auto_started", False),
        )


class ExperimentLog:
    """Tracks all experiments and supports comparison."""

    def __init__(self, persist_path: Path) -> None:
        self._persist_path = persist_path
        self._experiments: list[Experiment] = []
        self._active: Experiment | None = None
        self._load()

    @property
    def active_experiment(self) -> Experiment | None:
        return self._active

    @property
    def all_experiments(self) -> list[Experiment]:
        return list(self._experiments)

    def start_experiment(
        self,
        mission_prompt: str,
        initial_strategy: dict[str, Any] | None = None,
        start_reason: str = "",
        auto_started: bool = False,
    ) -> Experiment:
        """Start tracking a new experiment."""
        if self._active:
            # End the current one first
            self.end_experiment()

        exp = Experiment(
            mission_prompt=mission_prompt,
            initial_strategy=initial_strategy or {},
            start_reason=start_reason,
            auto_started=auto_started,
        )
        self._active = exp
        self._experiments.append(exp)
        self.save()
        logger.info("Experiment started: %s (id: %s)", mission_prompt[:60], exp.id)
        return exp

    def latest_postmortem(self) -> str:
        """Return the postmortem text of the most recently completed experiment, or ''."""
        completed = [e for e in self._experiments if e.status == "completed" and e.llm_postmortem]
        if not completed:
            return ""
        # Most recently ended
        latest = max(completed, key=lambda e: e.ended_at)
        return latest.llm_postmortem

    def end_experiment(
        self,
        final_strategy: dict[str, Any] | None = None,
        engagement_metrics: dict[str, Any] | None = None,
        mission_completion_pct: float = 0.0,
    ) -> Experiment | None:
        """End the active experiment and snapshot final state."""
        if not self._active:
            return None

        self._active.ended_at = time.time()
        self._active.status = "completed"
        if final_strategy:
            self._active.final_strategy = final_strategy
        if engagement_metrics:
            self._active.engagement_metrics = engagement_metrics
        self._active.mission_completion_pct = mission_completion_pct

        ended = self._active
        self._active = None
        self.save()
        logger.info(
            "Experiment ended: %s (%d cycles, %.0f%% complete)",
            ended.mission_prompt[:60],
            ended.total_cycles,
            ended.mission_completion_pct,
        )
        return ended

    def record_cycle(self, action: str) -> None:
        """Record a cycle action on the active experiment."""
        if not self._active:
            return
        self._active.total_cycles += 1
        if action in self._active.action_counts:
            self._active.action_counts[action] += 1

    def compare(self, exp1_id: str, exp2_id: str) -> dict[str, Any]:
        """Compare two experiments by their metrics."""
        e1 = next((e for e in self._experiments if e.id == exp1_id), None)
        e2 = next((e for e in self._experiments if e.id == exp2_id), None)

        if not e1 or not e2:
            return {"error": "One or both experiments not found"}

        return {
            "experiment_1": {
                "id": e1.id,
                "mission": e1.mission_prompt[:80],
                "cycles": e1.total_cycles,
                "duration_hours": e1.duration_seconds / 3600,
                "completion": e1.mission_completion_pct,
                "actions": e1.action_counts,
                "engagement": e1.engagement_metrics,
            },
            "experiment_2": {
                "id": e2.id,
                "mission": e2.mission_prompt[:80],
                "cycles": e2.total_cycles,
                "duration_hours": e2.duration_seconds / 3600,
                "completion": e2.mission_completion_pct,
                "actions": e2.action_counts,
                "engagement": e2.engagement_metrics,
            },
        }

    def save(self) -> None:
        self._persist_path.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "experiments": [e.to_dict() for e in self._experiments[-50:]],
            "active_id": self._active.id if self._active else None,
        }
        self._persist_path.write_text(json.dumps(data, indent=2))

    def _load(self) -> None:
        if not self._persist_path.exists():
            return
        try:
            raw = self._persist_path.read_text()
            data = json.loads(raw)
            self._experiments = [
                Experiment.from_dict(e) for e in data.get("experiments", [])
            ]
            active_id = data.get("active_id")
            if active_id:
                self._active = next(
                    (e for e in self._experiments if e.id == active_id), None
                )
            logger.info(
                "Loaded %d experiment(s)%s",
                len(self._experiments),
                f" (active: {self._active.id})" if self._active else "",
            )
        except (json.JSONDecodeError, KeyError):
            logger.warning("Could not load experiments file, starting fresh")
