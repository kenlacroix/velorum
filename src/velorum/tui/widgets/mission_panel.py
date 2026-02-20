"""Mission panel — displays and controls the active mission."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from textual.app import ComposeResult
from textual.containers import Container, Horizontal
from textual.widgets import Button, Input, Static

if TYPE_CHECKING:
    from velorum.mission import MissionManager

logger = logging.getLogger(__name__)

_STATUS_ICON = {
    "pending": "[dim]\u25cb[/]",
    "active": "[bold cyan]\u25b6[/]",
    "completed": "[green]\u2713[/]",
    "failed": "[red]\u2717[/]",
}


class MissionPanel(Container):
    """TUI widget for viewing and controlling missions."""

    BORDER_TITLE = "Mission"

    def __init__(
        self,
        mission_manager: MissionManager,
        **kwargs: object,
    ) -> None:
        super().__init__(**kwargs)
        self._manager = mission_manager

    def compose(self) -> ComposeResult:
        yield Static("", id="mission-status")
        yield Static("", id="mission-prompt")
        yield Static("", id="mission-plan")
        yield Static("", id="mission-steps")
        yield Static("", id="mission-progress")
        yield Static("", id="mission-notes")
        with Horizontal(id="mission-controls"):
            yield Input(
                placeholder="Enter mission prompt...",
                id="mission-input",
            )
            yield Button("Set Mission", id="btn-set-mission", variant="primary")
            yield Button("Clear", id="btn-clear-mission", variant="error")

    def on_mount(self) -> None:
        self.refresh_display()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-set-mission":
            self._on_set_mission()
        elif event.button.id == "btn-clear-mission":
            self._on_clear_mission()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.input.id == "mission-input":
            self._on_set_mission()

    def _on_set_mission(self) -> None:
        inp = self.query_one("#mission-input", Input)
        prompt = inp.value.strip()
        if not prompt:
            self.app.notify("Enter a mission prompt first", severity="warning")
            return
        self._manager.set_mission(prompt)
        inp.value = ""
        self.app.notify(f"Mission set: {prompt[:50]}...")
        logger.info("Mission set via TUI: %s", prompt[:80])
        self.refresh_display()

    def _on_clear_mission(self) -> None:
        if not self._manager.active_mission:
            self.app.notify("No active mission", severity="warning")
            return
        self._manager.clear_mission()
        self.app.notify("Mission cleared")
        logger.info("Mission cleared via TUI")
        self.refresh_display()

    def refresh_display(self) -> None:
        mission = self._manager.active_mission

        if not mission:
            self.query_one("#mission-status", Static).update(
                "  [dim]No active mission[/]"
            )
            self.query_one("#mission-prompt", Static).update("")
            self.query_one("#mission-plan", Static).update("")
            self.query_one("#mission-steps", Static).update("")
            self.query_one("#mission-progress", Static).update("")
            self.query_one("#mission-notes", Static).update("")
            return

        # Status
        status_color = {
            "planning": "yellow",
            "active": "green",
            "completed": "bold green",
            "paused": "yellow",
        }.get(mission.status, "")
        self.query_one("#mission-status", Static).update(
            f"  Status: [{status_color}]{mission.status.upper()}[/]"
            f"  |  Progress: [bold]{mission.completion_pct():.0f}%[/]"
            f"  |  Adaptations: {mission.adaptation_count}"
        )

        # Prompt
        self.query_one("#mission-prompt", Static).update(
            f"  [bold]Mission:[/] {mission.prompt}"
        )

        # Plan summary
        if mission.plan_summary:
            self.query_one("#mission-plan", Static).update(
                f"  [italic]Plan: {mission.plan_summary}[/]"
            )
        else:
            self.query_one("#mission-plan", Static).update(
                "  [dim italic]Awaiting plan from LLM...[/]"
            )

        # Steps
        if mission.steps:
            step_lines = ["  Steps:"]
            for step in mission.steps:
                icon = _STATUS_ICON.get(step.status, "\u25cb")
                attempts = f" ({step.attempts}/{step.max_attempts})" if step.status == "active" else ""
                step_lines.append(
                    f"    {icon} {step.description[:70]}{attempts}"
                )
                if step.outcome:
                    step_lines.append(f"       [dim]{step.outcome[:60]}[/]")
            self.query_one("#mission-steps", Static).update("\n".join(step_lines))
        else:
            self.query_one("#mission-steps", Static).update("")

        # Progress notes
        notes = mission.progress_notes[-5:]
        if notes:
            note_lines = ["  Recent progress:"]
            for note in notes:
                note_lines.append(f"    [dim]{note}[/]")
            self.query_one("#mission-notes", Static).update("\n".join(note_lines))
        else:
            self.query_one("#mission-notes", Static).update("")
