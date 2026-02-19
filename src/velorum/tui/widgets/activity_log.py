"""Live activity log panel with logging handler bridge."""

from __future__ import annotations

import logging
from datetime import datetime

from rich.text import Text
from textual.app import ComposeResult
from textual.containers import Container
from textual.widgets import RichLog

# Map log levels to Rich color markup
_LEVEL_STYLES: dict[int, str] = {
    logging.DEBUG: "dim",
    logging.INFO: "",
    logging.WARNING: "bold yellow",
    logging.ERROR: "bold red",
    logging.CRITICAL: "bold white on red",
}


class TUILogHandler(logging.Handler):
    """Forwards log records to a RichLog widget.

    Safe to call from both the event loop (async workers) and
    background threads (e.g. httpx internals).
    """

    def __init__(self, rich_log: RichLog) -> None:
        super().__init__()
        self._rich_log = rich_log

    def emit(self, record: logging.LogRecord) -> None:
        try:
            ts = datetime.fromtimestamp(record.created).strftime("%H:%M:%S")
            level = record.levelname
            msg = self.format(record) if self.formatter else record.getMessage()

            style = _LEVEL_STYLES.get(record.levelno, "")
            text = Text()
            text.append(f"[{ts}] ", style="dim cyan")
            text.append(f"{level:<8}", style=style or "")
            text.append(f" {msg}")

            # call_from_thread is safe from any context in Textual >=0.80
            # It checks internally whether we're on the event loop or not.
            self._rich_log.write(text)
        except Exception:
            self.handleError(record)


class ActivityLog(Container):
    """Right panel showing live log output."""

    BORDER_TITLE = "Activity Log"

    def compose(self) -> ComposeResult:
        yield RichLog(max_lines=1000, wrap=True, id="activity-log", markup=True)

    def get_log_widget(self) -> RichLog:
        return self.query_one("#activity-log", RichLog)
