"""Live activity log: prominent narrator space above a compact scrollable history."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime

from rich.text import Text
from textual.app import ComposeResult
from textual.containers import Container
from textual.widgets import RichLog, Static


class TUILogHandler(logging.Handler):
    """Routes log records to the ActivityLog widget.

    - ``velorum.activity`` INFO  → live narrator area (set_status)
    - WARNING                    → yellow entry in history log
    - ERROR / CRITICAL           → red entry in history log
    - Everything else below WARNING is silenced in the TUI.
    """

    def __init__(self, activity_log: "ActivityLog") -> None:
        super().__init__()
        self._activity_log = activity_log

    def emit(self, record: logging.LogRecord) -> None:
        try:
            msg = self.format(record) if self.formatter else record.getMessage()
            if record.name == "velorum.activity" and record.levelno == logging.INFO:
                self._activity_log.set_status(msg)
            elif record.levelno >= logging.ERROR:
                self._activity_log.log_error(msg)
            elif record.levelno >= logging.WARNING:
                self._activity_log.log_warning(msg)
            # INFO and below from non-activity loggers: silenced
        except Exception:
            self.handleError(record)


class ActivityLog(Container):
    """Two-zone activity display.

    **Narrator** (top, large): streams the bot's current thought word-by-word,
    then holds the completed text until the next cycle begins — giving the user
    a persistent window into what the bot just did or is doing.

    **History log** (bottom, compact): a scrollable record of committed cycle
    narratives, warnings, and errors.
    """

    BORDER_TITLE = "Activity"

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._streaming = False

    def compose(self) -> ComposeResult:
        yield Static("", id="narrator", markup=True)
        yield RichLog(max_lines=500, wrap=True, id="activity-log", markup=True)

    def get_log_widget(self) -> RichLog:
        return self.query_one("#activity-log", RichLog)

    # ------------------------------------------------------------------
    # Live narrator — status updates during cycle (no delay)
    # ------------------------------------------------------------------

    def set_status(self, text: str) -> None:
        """Show current action in the narrator. No-ops while streaming."""
        if self._streaming:
            return
        try:
            self.query_one("#narrator", Static).update(
                f"[italic dim]{text}[/italic dim]"
            )
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Narrative streaming — post-cycle, word-by-word animation
    # ------------------------------------------------------------------

    async def stream_narrative(self, text: str, delay: float = 0.03) -> None:
        """Stream *text* word-by-word in the narrator, then commit to the log.

        Uses the plain-text version for streaming (so Rich markup isn't broken
        mid-word), then renders the fully-marked-up version on completion.
        The completed text stays in the narrator until the next status or
        narrative replaces it.
        """
        self._streaming = True
        try:
            narrator = self.query_one("#narrator", Static)
            log = self.query_one("#activity-log", RichLog)

            # Build plain version for streaming animation
            plain = Text.from_markup(text).plain
            words = plain.split()
            current = ""
            for word in words:
                current = (current + " " + word).lstrip()
                narrator.update(f"{current}[dim]▌[/dim]")
                await asyncio.sleep(delay)

            # Render final version WITH markup; keep it in narrator
            narrator.update(text)

            # Commit to scrollable history log
            ts = datetime.now().strftime("%H:%M:%S")
            log.write(Text.from_markup(f"[dim cyan][{ts}][/dim cyan] {text}"))
        except Exception:
            pass
        finally:
            self._streaming = False

    # ------------------------------------------------------------------
    # Direct log writes — startup info, warnings, errors
    # ------------------------------------------------------------------

    def log_info(self, text: str) -> None:
        """Write an info line directly to the history log (not the narrator)."""
        try:
            log = self.query_one("#activity-log", RichLog)
            ts = datetime.now().strftime("%H:%M:%S")
            t = Text()
            t.append(f"[{ts}] ", style="dim cyan")
            t.append(text)
            log.write(t)
        except Exception:
            pass

    def log_warning(self, text: str) -> None:
        try:
            log = self.query_one("#activity-log", RichLog)
            ts = datetime.now().strftime("%H:%M:%S")
            t = Text()
            t.append(f"[{ts}] ", style="dim cyan")
            t.append(f"⚠ {text}", style="bold yellow")
            log.write(t)
        except Exception:
            pass

    def log_error(self, text: str) -> None:
        try:
            log = self.query_one("#activity-log", RichLog)
            ts = datetime.now().strftime("%H:%M:%S")
            t = Text()
            t.append(f"[{ts}] ", style="dim cyan")
            t.append(f"✗ {text}", style="bold red")
            log.write(t)
        except Exception:
            pass
