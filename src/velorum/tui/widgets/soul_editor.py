"""In-TUI soul file editor with live reload into brain."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING

from textual.app import ComposeResult
from textual.containers import Container
from textual.widgets import Static, TextArea

if TYPE_CHECKING:
    from velorum.brain import Brain

logger = logging.getLogger(__name__)


class SoulEditor(Container):
    """Bottom panel with a TextArea for editing SOUL.md."""

    BORDER_TITLE = "Soul Editor"

    def __init__(
        self,
        soul_path: Path,
        brain: Brain | None = None,
        **kwargs: object,
    ) -> None:
        super().__init__(**kwargs)
        self._soul_path = soul_path
        self._brain = brain
        self._saved_text: str = ""

    def compose(self) -> ComposeResult:
        yield TextArea(language="markdown", id="soul-textarea", show_line_numbers=True)
        yield Static(
            "\u2714 Saved",
            id="soul-status",
            classes="status-bar status-saved",
        )

    def on_mount(self) -> None:
        self._load()

    def _load(self) -> None:
        """Load soul file into the editor."""
        text = ""
        if self._soul_path.exists():
            text = self._soul_path.read_text()
        textarea = self.query_one("#soul-textarea", TextArea)
        textarea.load_text(text)
        self._saved_text = text
        self._update_status(modified=False)

    def on_text_area_changed(self, _event: TextArea.Changed) -> None:
        current = self.query_one("#soul-textarea", TextArea).text
        self._update_status(modified=current != self._saved_text)

    def save(self) -> bool:
        """Write current content to disk and hot-reload into brain.

        Returns True on success.
        """
        textarea = self.query_one("#soul-textarea", TextArea)
        text = textarea.text
        try:
            self._soul_path.parent.mkdir(parents=True, exist_ok=True)
            self._soul_path.write_text(text)
            self._saved_text = text
            if self._brain is not None:
                self._brain._soul = text
            self._update_status(modified=False)
            logger.info(
                "Soul saved (%d chars) — active next cycle", len(text)
            )
            return True
        except OSError as e:
            logger.error("Failed to save soul: %s", e)
            return False

    def _update_status(self, *, modified: bool) -> None:
        status = self.query_one("#soul-status", Static)
        if modified:
            status.update("\u270e Modified — Ctrl+S to save")
            status.set_classes("status-bar status-modified")
        else:
            status.update("\u2714 Saved")
            status.set_classes("status-bar status-saved")

    @property
    def is_modified(self) -> bool:
        current = self.query_one("#soul-textarea", TextArea).text
        return current != self._saved_text
