"""Runtime settings editor panel."""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import TYPE_CHECKING

from textual.app import ComposeResult
from textual.containers import Container, Horizontal
from textual.widgets import Button, Input, Label, Static

if TYPE_CHECKING:
    from velorum.config import Settings

logger = logging.getLogger(__name__)

# Editable settings: (attr_name, display_label, min, max, unit)
EDITABLE_SETTINGS = [
    ("confidence_threshold", "Confidence threshold", 1, 10, "/10"),
    ("max_responses_per_hour", "Max comments/hr", 1, 100, ""),
    ("max_posts_per_day", "Max posts/day", 0, 10, ""),
    ("min_post_interval_seconds", "Post cooldown", 60, 86400, "sec"),
    ("cycle_interval_seconds", "Cycle interval", 10, 3600, "sec"),
    ("reflection_interval_cycles", "Reflect every", 1, 100, "cycles"),
    ("max_conversation_checks_per_cycle", "Conv checks/cycle", 1, 50, ""),
    ("max_engagement_checks_per_cycle", "Engage checks/cycle", 1, 50, ""),
]


class SettingsPanel(Container):
    """Bottom tab for editing runtime settings."""

    BORDER_TITLE = "Settings"

    def __init__(self, settings: Settings, **kwargs: object) -> None:
        super().__init__(**kwargs)
        self._settings = settings

    def compose(self) -> ComposeResult:
        for attr, display_label, _mn, _mx, unit in EDITABLE_SETTINGS:
            with Horizontal(classes="setting-row"):
                yield Label(f"{display_label}:", classes="setting-label")
                yield Input(
                    value=str(getattr(self._settings, attr)),
                    id=f"setting-{attr}",
                    type="integer",
                    classes="setting-input",
                )
                if unit:
                    yield Label(unit, classes="setting-unit")

        # Read-only display of structural settings
        yield Static("", classes="readonly-section")
        yield Static(
            f"  Provider: [bold]{self._settings.llm_provider}[/]  \u2502  "
            f"Model: [bold]{self._settings.llm_model}[/]",
            classes="readonly-label",
        )
        yield Static(
            f"  Base URL: {self._settings.moltbook_base_url}",
            classes="readonly-label",
        )

        yield Button("Apply & Save", id="apply-settings", variant="primary")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id != "apply-settings":
            return
        self._apply()

    def _apply(self) -> None:
        """Validate, update in-memory settings, and persist to .env."""
        errors: list[str] = []
        changes: dict[str, tuple[int, int]] = {}

        for attr, display_label, mn, mx, _unit in EDITABLE_SETTINGS:
            inp = self.query_one(f"#setting-{attr}", Input)
            raw = inp.value.strip()
            if not raw.isdigit():
                errors.append(f"{display_label}: must be a number")
                continue
            val = int(raw)
            if val < mn or val > mx:
                errors.append(f"{display_label}: must be {mn}\u2013{mx}")
                continue
            old = getattr(self._settings, attr)
            if val != old:
                changes[attr] = (old, val)
            setattr(self._settings, attr, val)

        if errors:
            self.notify("\n".join(errors), title="Validation Error", severity="error")
            return

        if not changes:
            self.notify("No changes to apply.", title="Settings")
            return

        # Persist to .env
        self._write_env()

        # Log what changed
        for attr, (old, new) in changes.items():
            label = next(d for a, d, *_ in EDITABLE_SETTINGS if a == attr)
            logger.info("Setting changed: %s %d \u2192 %d", label, old, new)

        self.notify(
            f"{len(changes)} setting(s) applied \u2014 active immediately.",
            title="Settings saved",
        )

        # Refresh stats to reflect new settings
        from velorum.tui.widgets.stats_panel import StatsPanel

        try:
            stats = self.app.query_one(StatsPanel)
            stats.update_stats(
                cycle=self.app._cycle,
                settings=self._settings,
                controller=self.app.controller,
                memory=self.app.memory,
            )
        except Exception:
            logger.debug("Could not refresh stats panel after settings update")

    def _write_env(self) -> None:
        """Update .env file with current editable settings."""
        env_path = Path(".env")
        lines: list[str] = []
        if env_path.exists():
            lines = env_path.read_text().splitlines()

        env_keys = {
            "confidence_threshold": "CONFIDENCE_THRESHOLD",
            "max_responses_per_hour": "MAX_RESPONSES_PER_HOUR",
            "max_posts_per_day": "MAX_POSTS_PER_DAY",
            "min_post_interval_seconds": "MIN_POST_INTERVAL_SECONDS",
            "cycle_interval_seconds": "CYCLE_INTERVAL_SECONDS",
            "reflection_interval_cycles": "REFLECTION_INTERVAL_CYCLES",
            "max_conversation_checks_per_cycle": "MAX_CONVERSATION_CHECKS_PER_CYCLE",
            "max_engagement_checks_per_cycle": "MAX_ENGAGEMENT_CHECKS_PER_CYCLE",
        }

        for attr, env_key in env_keys.items():
            val = str(getattr(self._settings, attr))
            pattern = re.compile(rf"^{re.escape(env_key)}\s*=.*$")
            found = False
            for i, line in enumerate(lines):
                if pattern.match(line):
                    lines[i] = f"{env_key}={val}"
                    found = True
                    break
            if not found:
                lines.append(f"{env_key}={val}")

        env_path.write_text("\n".join(lines) + "\n")
