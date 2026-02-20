"""Bot stats panel showing live status information."""

from __future__ import annotations

import time
from typing import TYPE_CHECKING

from textual.app import ComposeResult
from textual.containers import Container
from textual.reactive import reactive
from textual.widgets import Static

if TYPE_CHECKING:
    from velorum.config import Settings
    from velorum.controller import Controller
    from velorum.memory import Memory


def _fmt_duration(seconds: float) -> str:
    """Format seconds as human-readable duration."""
    s = int(seconds)
    if s < 60:
        return f"{s}s"
    if s < 3600:
        return f"{s // 60}m {s % 60}s"
    h = s // 3600
    m = (s % 3600) // 60
    return f"{h}h {m}m"


class StatsPanel(Container):
    """Left panel showing bot status and metrics."""

    BORDER_TITLE = "Stats"

    status_text: reactive[str] = reactive("Starting...")
    countdown: reactive[int] = reactive(0)
    last_action: reactive[str] = reactive("\u2014")

    def compose(self) -> ComposeResult:
        yield Static("", id="stat-status")
        yield Static("", id="stat-ban")
        yield Static("", id="stat-uptime")
        yield Static("", id="stat-cycle")
        yield Static("", id="stat-countdown")
        yield Static("", id="stat-last-action")
        yield Static("", id="stat-divider")
        yield Static("", id="stat-provider")
        yield Static("", id="stat-model")
        yield Static("", id="stat-confidence")
        yield Static("", id="stat-rate")
        yield Static("", id="stat-divider2")
        yield Static("", id="stat-total")
        yield Static("", id="stat-posts")
        yield Static("", id="stat-conversations")
        yield Static("", id="stat-observations")
        yield Static("", id="stat-divider3")
        yield Static("", id="stat-bots-known")
        yield Static("", id="stat-insights")
        yield Static("", id="stat-engagement")

    def on_mount(self) -> None:
        self._start_time = time.time()
        self.set_interval(1.0, self._tick)

    def _tick(self) -> None:
        elapsed = time.time() - self._start_time
        self.query_one("#stat-uptime", Static).update(
            f"  Uptime: {_fmt_duration(elapsed)}"
        )
        if self.countdown > 0:
            self.countdown = max(0, self.countdown - 1)
            self.query_one("#stat-countdown", Static).update(
                f"  Next cycle: [bold cyan]{_fmt_duration(self.countdown)}[/]"
            )
        else:
            self.query_one("#stat-countdown", Static).update("")

    def set_status(self, status: str) -> None:
        self.status_text = status
        color = {
            "Online": "bold green",
            "Paused": "bold yellow",
            "Banned": "bold red",
            "Fetching feed": "bold cyan",
            "Brain deciding": "bold magenta",
            "Posting comment": "bold blue",
            "Creating post": "bold blue",
            "Checking conversations": "bold cyan",
            "Checking engagement": "bold cyan",
            "Reflecting": "bold magenta",
            "Waiting": "dim",
            "Error": "bold red",
        }.get(status, "")
        marker = {
            "Online": "[green]\u25cf[/]",
            "Paused": "[yellow]\u25cf[/]",
            "Banned": "[red]\u26d4[/]",
            "Fetching feed": "[cyan]\u21bb[/]",
            "Brain deciding": "[magenta]\u2699[/]",
            "Posting comment": "[blue]\u2191[/]",
            "Creating post": "[blue]\u270d[/]",
            "Checking conversations": "[cyan]\u2194[/]",
            "Checking engagement": "[cyan]\u2606[/]",
            "Reflecting": "[magenta]\u2026[/]",
            "Waiting": "[dim]\u25cb[/]",
            "Error": "[red]\u2717[/]",
        }.get(status, "\u25cf")
        self.query_one("#stat-status", Static).update(
            f"  {marker} [{color}]{status}[/]"
        )
        # Clear ban display when not banned
        if status != "Banned":
            self.query_one("#stat-ban", Static).update("")

    def set_ban_remaining(self, seconds: float) -> None:
        """Update the ban countdown display."""
        if seconds <= 0:
            self.query_one("#stat-ban", Static).update("")
            return
        self.query_one("#stat-ban", Static).update(
            f"  [bold red]Ban expires in: {_fmt_duration(seconds)}[/]"
        )

    def set_last_action(self, action: str) -> None:
        self.last_action = action
        self.query_one("#stat-last-action", Static).update(
            f"  Last: [italic]{action}[/]"
        )

    def update_stats(
        self,
        *,
        cycle: int,
        settings: Settings,
        controller: Controller,
        memory: Memory,
    ) -> None:
        self.query_one("#stat-cycle", Static).update(f"  Cycle: [bold]{cycle}[/]")
        self.query_one("#stat-divider", Static).update("  " + "\u2500" * 22)
        self.query_one("#stat-provider", Static).update(
            f"  Provider: {settings.llm_provider}"
        )
        self.query_one("#stat-model", Static).update(
            f"  Model: {settings.llm_model}"
        )
        self.query_one("#stat-confidence", Static).update(
            f"  Confidence: \u2265{settings.confidence_threshold}"
        )

        # Rate limit usage (comments + replies combined)
        now = time.time()
        hour_ago = now - 3600
        recent_comments = sum(1 for t in controller._response_timestamps if t > hour_ago)
        recent_replies = sum(1 for t in controller._reply_timestamps if t > hour_ago)
        total_recent = recent_comments + recent_replies
        max_r = settings.max_responses_per_hour
        rate_color = "red" if total_recent >= max_r else "green"
        self.query_one("#stat-rate", Static).update(
            f"  Rate: [{rate_color}]{total_recent}/{max_r}[/] per hr"
        )

        self.query_one("#stat-divider2", Static).update("  " + "\u2500" * 22)

        # Totals from memory
        total_decisions = memory.decision_count
        total_responses = sum(
            1 for d in memory._decisions if d.get("action") == "RESPOND"
        )
        total_posts = memory.post_count
        total_observations = total_decisions - total_responses - total_posts

        self.query_one("#stat-total", Static).update(
            f"  Comments: [bold]{total_responses}[/]"
        )
        self.query_one("#stat-posts", Static).update(
            f"  Posts: [bold]{total_posts}[/]"
        )

        # Conversation stats
        conv_stats = memory.conversations.stats()
        self.query_one("#stat-conversations", Static).update(
            f"  Threads: [bold]{conv_stats['active']}[/] active, "
            f"{conv_stats['total_replies']} replies"
        )
        self.query_one("#stat-observations", Static).update(
            f"  Observations: {total_observations}"
        )

        # Learning stats
        self.query_one("#stat-divider3", Static).update("  " + "\u2500" * 22)
        learn_stats = memory.learning.stats()
        self.query_one("#stat-bots-known", Static).update(
            f"  Bots known: [bold]{learn_stats['bots_known']}[/]"
        )
        self.query_one("#stat-insights", Static).update(
            f"  Insights: {learn_stats['insights']}"
        )
        engaged = total_responses + total_posts
        pct = (
            f"{engaged / total_decisions * 100:.0f}%"
            if total_decisions > 0
            else "\u2014"
        )
        self.query_one("#stat-engagement", Static).update(
            f"  Engagement: {pct}"
        )
