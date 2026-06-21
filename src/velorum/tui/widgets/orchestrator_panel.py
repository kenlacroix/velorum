"""Orchestrator panel — live Brain mission control view."""

from __future__ import annotations

from typing import TYPE_CHECKING

from textual.app import ComposeResult
from textual.containers import Container
from textual.widgets import Static

if TYPE_CHECKING:
    from velorum.orchestrator import CycleState


_PHASE_COLORS: dict[str, str] = {
    "Idle": "dim",
    "Conversations": "cyan",
    "Scanning feed": "cyan",
    "Computing heat": "cyan",
    "Deciding": "magenta",
    "Acting": "bold blue",
    "Reflecting": "bold magenta",
}

_TIER_COLORS: dict[str, str] = {
    "elite": "bold yellow",
    "regular": "green",
    "passive": "dim",
    "unknown": "dim",
}


def _entropy_bar(score: float, width: int = 10) -> str:
    """ASCII entropy bar: filled = diverse, empty = concentrated."""
    filled = int(round(score * width))
    bar = "\u2588" * filled + "\u2591" * (width - filled)
    if score > 0.6:
        color = "green"
    elif score > 0.35:
        color = "yellow"
    else:
        color = "bold red"
    return f"[{color}]{bar}[/] {score:.2f}"


class OrchestratorPanel(Container):
    """Brain mission-control panel — polls CycleState every 2 seconds."""

    BORDER_TITLE = "Brain"

    def __init__(self, cycle_state: CycleState | None = None, **kwargs: object) -> None:
        super().__init__(**kwargs)
        self._cycle_state = cycle_state

    def compose(self) -> ComposeResult:
        yield Static("", id="orch-phase")
        yield Static("", id="orch-divider1")
        yield Static("", id="orch-queue-header")
        yield Static("", id="orch-queue-items")
        yield Static("", id="orch-divider2")
        yield Static("", id="orch-hot-header")
        yield Static("", id="orch-hot-items")
        yield Static("", id="orch-divider3")
        yield Static("", id="orch-learn-header")
        yield Static("", id="orch-entropy")
        yield Static("", id="orch-insight")
        yield Static("", id="orch-divider4")
        yield Static("", id="orch-tiers-header")
        yield Static("", id="orch-tiers")
        yield Static("", id="orch-divider5")
        yield Static("", id="orch-countdowns")

    def on_mount(self) -> None:
        self.set_interval(2.0, self._refresh_state)
        self._refresh_state()

    def _refresh_state(self) -> None:
        cs = self._cycle_state
        if cs is None:
            self.query_one("#orch-phase", Static).update("  [dim]No cycle state[/]")
            return

        # Phase
        phase = cs.current_phase
        color = _PHASE_COLORS.get(phase, "white")
        self.query_one("#orch-phase", Static).update(
            f"  Phase: [{color}]{phase}[/]  (cycle {cs.last_cycle})"
        )

        sep = "  " + "\u2500" * 28

        # Queue
        self.query_one("#orch-divider1", Static).update(sep)
        self.query_one("#orch-queue-header", Static).update("  [bold]Action Queue[/]")
        if cs.queued_actions:
            items = "\n".join(f"    \u2022 {a[:50]}" for a in cs.queued_actions[:5])
            self.query_one("#orch-queue-items", Static).update(items)
        else:
            self.query_one("#orch-queue-items", Static).update("    [dim]empty[/]")

        # Hot posts
        self.query_one("#orch-divider2", Static).update(sep)
        self.query_one("#orch-hot-header", Static).update("  [bold]Hot Threads[/]")
        if cs.hot_posts:
            lines: list[str] = []
            for hp in cs.hot_posts[:4]:
                flags: list[str] = []
                if hp.get("reply_to_us"):
                    flags.append("[bold red]REPLY[/]")
                if hp.get("op_active"):
                    flags.append("[yellow]OP[/]")
                title = hp.get("title", "?")[:35]
                count = hp.get("comment_count", 0)
                flag_str = " ".join(flags)
                if flag_str:
                    lines.append(f'    \u2605 "{title}" ({count}c) {flag_str}')
                else:
                    lines.append(f'    \u25cb "{title}" ({count}c)')
            self.query_one("#orch-hot-items", Static).update("\n".join(lines))
        else:
            self.query_one("#orch-hot-items", Static).update("    [dim]none detected[/]")

        # Learning state
        self.query_one("#orch-divider3", Static).update(sep)
        self.query_one("#orch-learn-header", Static).update("  [bold]Learning State[/]")
        self.query_one("#orch-entropy", Static).update(
            f"  Diversity: {_entropy_bar(cs.entropy_score)}"
        )
        insight = cs.top_insight[:60] if cs.top_insight else "[dim]no insights yet[/]"
        self.query_one("#orch-insight", Static).update(f"  Top: [italic]{insight}[/]")

        # Bot tiers
        self.query_one("#orch-divider4", Static).update(sep)
        self.query_one("#orch-tiers-header", Static).update("  [bold]Bot Tiers[/]")
        tier_parts = [
            f"[{_TIER_COLORS['elite']}]elite:{cs.elite_count}[/]",
            f"[{_TIER_COLORS['regular']}]regular:{cs.regular_count}[/]",
            f"[{_TIER_COLORS['passive']}]passive:{cs.passive_count}[/]",
            f"[{_TIER_COLORS['unknown']}]unknown:{cs.unknown_count}[/]",
        ]
        self.query_one("#orch-tiers", Static).update("  " + "  ".join(tier_parts))

        # Countdowns
        self.query_one("#orch-divider5", Static).update(sep)
        countdown_parts: list[str] = []
        if cs.reflect_in > 0:
            countdown_parts.append(f"Reflect in [cyan]{cs.reflect_in}[/]c")
        if cs.soul_in > 0:
            countdown_parts.append(f"Soul in [magenta]{cs.soul_in}[/]c")
        if countdown_parts:
            self.query_one("#orch-countdowns", Static).update(
                "  " + "  |  ".join(countdown_parts)
            )
        else:
            self.query_one("#orch-countdowns", Static).update("")
