"""Modal for reviewing and applying a soul amendment proposal."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Container, Horizontal
from textual.screen import ModalScreen
from textual.widgets import Button, Label, Static, TextArea

from velorum.soul import SoulProposal


class SoulProposalModal(ModalScreen[str | None]):
    """Modal screen for reviewing a soul amendment proposal.

    Dismissed with the (possibly edited) amendment text to apply,
    or None if dismissed without applying.
    """

    BINDINGS = [
        Binding("escape", "dismiss_modal", "Dismiss", show=True),
    ]

    DEFAULT_CSS = """
    SoulProposalModal {
        align: center middle;
    }

    #modal-container {
        width: 80;
        height: auto;
        max-height: 40;
        border: thick $primary;
        background: $surface;
        padding: 1 2;
    }

    #modal-title {
        text-style: bold;
        margin-bottom: 1;
    }

    #modal-meta {
        color: $text-muted;
        margin-bottom: 1;
    }

    #reasoning-label {
        text-style: bold;
        margin-top: 1;
    }

    #modal-reasoning {
        color: $text-muted;
        margin-bottom: 1;
    }

    #amendment-label {
        text-style: bold;
        margin-top: 1;
    }

    #amendment-area {
        height: 8;
        border: solid $accent;
        margin-bottom: 1;
    }

    #modal-hint {
        color: $text-muted;
        margin-bottom: 1;
    }

    #button-row {
        height: 3;
        align: center middle;
        margin-top: 1;
    }

    #btn-apply {
        margin-right: 2;
    }
    """

    def __init__(self, proposal: SoulProposal) -> None:
        super().__init__()
        self._proposal = proposal

    def compose(self) -> ComposeResult:
        with Container(id="modal-container"):
            yield Static("Soul Amendment Proposal", id="modal-title")
            yield Static(
                f"Cycle {self._proposal.cycle} · ID: {self._proposal.id}",
                id="modal-meta",
            )
            yield Label("Reasoning:", id="reasoning-label")
            yield Static(self._proposal.reasoning or "(none)", id="modal-reasoning")
            yield Label("Proposed amendment (edit as needed):", id="amendment-label")
            yield TextArea(
                self._proposal.proposed_amendment,
                id="amendment-area",
                language="markdown",
            )
            yield Static(
                "After applying, refine further in the Soul Editor tab.",
                id="modal-hint",
            )
            with Horizontal(id="button-row"):
                yield Button("Apply to Soul", variant="primary", id="btn-apply")
                yield Button("Dismiss", variant="default", id="btn-dismiss")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-apply":
            text = self.query_one("#amendment-area", TextArea).text.strip()
            self.dismiss(text if text else None)
        else:
            self.dismiss(None)

    def action_dismiss_modal(self) -> None:
        self.dismiss(None)
