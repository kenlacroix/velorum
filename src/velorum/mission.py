"""Mission system — persistent goals that steer the agent's behavior.

Missions inject context into existing prompts, steering the Brain's
decisions without changing the reactive cycle's control flow. The LLM
does all planning; no hardcoded planning logic here.
"""

from __future__ import annotations

import json
import logging
import time
import uuid
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class MissionStep:
    """A single step in a mission plan."""

    def __init__(
        self,
        *,
        id: str = "",
        description: str = "",
        strategy: str = "",
        status: str = "pending",  # pending | active | completed | failed
        success_criteria: str = "",
        depends_on: list[str] | None = None,
        attempts: int = 0,
        max_attempts: int = 10,
        outcome: str = "",
    ) -> None:
        self.id = id or str(uuid.uuid4())[:8]
        self.description = description
        self.strategy = strategy
        self.status = status
        self.success_criteria = success_criteria
        self.depends_on = depends_on or []
        self.attempts = attempts
        self.max_attempts = max_attempts
        self.outcome = outcome

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "description": self.description,
            "strategy": self.strategy,
            "status": self.status,
            "success_criteria": self.success_criteria,
            "depends_on": self.depends_on,
            "attempts": self.attempts,
            "max_attempts": self.max_attempts,
            "outcome": self.outcome,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> MissionStep:
        return cls(
            id=d.get("id", ""),
            description=d.get("description", ""),
            strategy=d.get("strategy", ""),
            status=d.get("status", "pending"),
            success_criteria=d.get("success_criteria", ""),
            depends_on=d.get("depends_on", []),
            attempts=d.get("attempts", 0),
            max_attempts=d.get("max_attempts", 10),
            outcome=d.get("outcome", ""),
        )


class Mission:
    """A mission with a plan decomposed into steps."""

    def __init__(
        self,
        *,
        id: str = "",
        prompt: str = "",
        plan_summary: str = "",
        steps: list[MissionStep] | None = None,
        status: str = "planning",  # planning | active | completed | paused
        progress_notes: list[str] | None = None,
        adaptation_count: int = 0,
        created_at: float = 0.0,
    ) -> None:
        self.id = id or str(uuid.uuid4())[:8]
        self.prompt = prompt
        self.plan_summary = plan_summary
        self.steps = steps or []
        self.status = status
        self.progress_notes = progress_notes or []
        self.adaptation_count = adaptation_count
        self.created_at = created_at or time.time()

    def active_steps(self) -> list[MissionStep]:
        return [s for s in self.steps if s.status == "active"]

    def next_step(self) -> MissionStep | None:
        """Return the next pending step whose dependencies are met."""
        completed_ids = {s.id for s in self.steps if s.status == "completed"}
        for step in self.steps:
            if step.status != "pending":
                continue
            if all(dep in completed_ids for dep in step.depends_on):
                return step
        return None

    def completion_pct(self) -> float:
        if not self.steps:
            return 0.0
        done = sum(1 for s in self.steps if s.status == "completed")
        return done / len(self.steps) * 100

    def add_progress_note(self, note: str) -> None:
        self.progress_notes.append(f"[{time.strftime('%H:%M')}] {note}")
        # Keep last 50
        if len(self.progress_notes) > 50:
            self.progress_notes = self.progress_notes[-50:]

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "prompt": self.prompt,
            "plan_summary": self.plan_summary,
            "steps": [s.to_dict() for s in self.steps],
            "status": self.status,
            "progress_notes": self.progress_notes[-50:],
            "adaptation_count": self.adaptation_count,
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> Mission:
        return cls(
            id=d.get("id", ""),
            prompt=d.get("prompt", ""),
            plan_summary=d.get("plan_summary", ""),
            steps=[MissionStep.from_dict(s) for s in d.get("steps", [])],
            status=d.get("status", "planning"),
            progress_notes=d.get("progress_notes", []),
            adaptation_count=d.get("adaptation_count", 0),
            created_at=d.get("created_at", 0.0),
        )


class MissionManager:
    """Manages mission lifecycle and persistence."""

    def __init__(self, persist_path: Path) -> None:
        self._persist_path = persist_path
        self._mission: Mission | None = None
        self._load()

    @property
    def active_mission(self) -> Mission | None:
        return self._mission

    def set_mission(self, prompt: str) -> Mission:
        """Create a new mission from a prompt. Plan will be filled by LLM."""
        self._mission = Mission(prompt=prompt, status="planning")
        self.save()
        logger.info("New mission set: %s", prompt[:80])
        return self._mission

    def apply_plan(self, plan_data: dict[str, Any]) -> None:
        """Apply LLM-generated plan to the current mission."""
        if not self._mission:
            return

        self._mission.plan_summary = plan_data.get("plan_summary", "")
        steps = []
        for s in plan_data.get("steps", []):
            steps.append(MissionStep(
                description=s.get("description", ""),
                strategy=s.get("strategy", ""),
                success_criteria=s.get("success_criteria", ""),
                depends_on=s.get("depends_on", []),
                max_attempts=s.get("max_attempts", 10),
            ))

        self._mission.steps = steps
        self._mission.status = "active"

        # Activate the first step(s) with no dependencies
        for step in self._mission.steps:
            if not step.depends_on:
                step.status = "active"
                break  # activate one at a time

        self.save()
        logger.info(
            "Mission plan applied: %d steps, summary: %s",
            len(steps),
            self._mission.plan_summary[:80],
        )

    def apply_review(self, review_data: dict[str, Any]) -> None:
        """Apply LLM review results — step updates and plan revisions."""
        if not self._mission:
            return

        # Step status updates
        for update in review_data.get("step_updates", []):
            step_id = update.get("step_id", "")
            for step in self._mission.steps:
                if step.id == step_id:
                    if update.get("status"):
                        step.status = update["status"]
                    if update.get("outcome"):
                        step.outcome = update["outcome"]
                    break

        # Plan revision — add new steps, remove old ones
        revision = review_data.get("plan_revision")
        if revision:
            self._mission.adaptation_count += 1
            reason = revision.get("reason", "")
            self._mission.add_progress_note(f"Plan adapted: {reason}")

            # Remove steps
            removed_ids = set(revision.get("removed_step_ids", []))
            if removed_ids:
                self._mission.steps = [
                    s for s in self._mission.steps if s.id not in removed_ids
                ]

            # Add new steps
            for s in revision.get("new_steps", []):
                self._mission.steps.append(MissionStep(
                    description=s.get("description", ""),
                    strategy=s.get("strategy", ""),
                    success_criteria=s.get("success_criteria", ""),
                    depends_on=s.get("depends_on", []),
                    max_attempts=s.get("max_attempts", 10),
                ))

        # Activate next step if current ones are done
        if not self._mission.active_steps():
            nxt = self._mission.next_step()
            if nxt:
                nxt.status = "active"
                self._mission.add_progress_note(f"Advancing to: {nxt.description[:60]}")
            else:
                # All steps completed or failed
                pending = [s for s in self._mission.steps if s.status == "pending"]
                if not pending:
                    self._mission.status = "completed"
                    self._mission.add_progress_note("Mission completed!")
                    logger.info("Mission completed: %s", self._mission.prompt[:60])

        # Record next action hint
        hint = review_data.get("next_action_hint", "")
        if hint:
            self._mission.add_progress_note(f"Next focus: {hint}")

        self.save()

    def clear_mission(self) -> None:
        """Clear the active mission, reverting to default behavior."""
        if self._mission:
            logger.info("Mission cleared: %s", self._mission.prompt[:60])
        self._mission = None
        self.save()

    def mission_context_for_prompt(self) -> str:
        """Generate the context block injected into all prompts."""
        if not self._mission or self._mission.status == "planning":
            return ""

        m = self._mission
        lines = [
            f"MISSION: {m.prompt}",
            f"Plan: {m.plan_summary}",
            f"Progress: {m.completion_pct():.0f}%",
        ]

        # Show active steps
        active = m.active_steps()
        if active:
            lines.append("")
            lines.append("CURRENT FOCUS:")
            for step in active:
                lines.append(f"  - {step.description}")
                if step.strategy:
                    lines.append(f"    Strategy: {step.strategy}")
                if step.success_criteria:
                    lines.append(f"    Success when: {step.success_criteria}")
                lines.append(f"    Attempts: {step.attempts}/{step.max_attempts}")

        # Show upcoming steps
        upcoming = [s for s in m.steps if s.status == "pending"][:2]
        if upcoming:
            lines.append("")
            lines.append("UPCOMING:")
            for step in upcoming:
                lines.append(f"  - {step.description}")

        # Recent progress notes
        recent_notes = m.progress_notes[-3:]
        if recent_notes:
            lines.append("")
            lines.append("RECENT PROGRESS:")
            for note in recent_notes:
                lines.append(f"  {note}")

        lines.append("")
        lines.append(
            "Align your actions with the current mission focus. "
            "Every RESPOND, POST, or REPLY should advance the mission when possible."
        )

        return "\n".join(lines)

    def record_action(self, action: str, detail: str) -> None:
        """Record a progress note after an action is taken."""
        if not self._mission or self._mission.status != "active":
            return

        self._mission.add_progress_note(f"{action}: {detail[:80]}")

        # Increment attempts on active steps
        for step in self._mission.active_steps():
            step.attempts += 1

        self.save()

    def save(self) -> None:
        self._persist_path.parent.mkdir(parents=True, exist_ok=True)
        data = self._mission.to_dict() if self._mission else None
        self._persist_path.write_text(json.dumps(data, indent=2))

    def _load(self) -> None:
        if not self._persist_path.exists():
            return
        try:
            raw = self._persist_path.read_text()
            data = json.loads(raw)
            if data:
                self._mission = Mission.from_dict(data)
                logger.info("Loaded mission: %s", self._mission.prompt[:60])
        except (json.JSONDecodeError, KeyError):
            logger.warning("Could not load mission file, starting fresh")
