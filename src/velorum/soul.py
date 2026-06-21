"""Soul proposal and evolution epoch system.

Proposals are written for human review; epochs are recorded when a proposal
is applied, forming a logical lineage of identity changes over time.
"""

from __future__ import annotations

import json
import logging
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class SoulProposal:
    """A proposed amendment to Velorum's soul."""

    id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    cycle: int = 0
    timestamp: float = field(default_factory=time.time)
    proposed_amendment: str = ""
    reasoning: str = ""
    applied: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "cycle": self.cycle,
            "timestamp": self.timestamp,
            "proposed_amendment": self.proposed_amendment,
            "reasoning": self.reasoning,
            "applied": self.applied,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> SoulProposal:
        return cls(
            id=d.get("id", str(uuid.uuid4())[:8]),
            cycle=d.get("cycle", 0),
            timestamp=d.get("timestamp", 0.0),
            proposed_amendment=d.get("proposed_amendment", ""),
            reasoning=d.get("reasoning", ""),
            applied=d.get("applied", False),
        )


class SoulProposalLog:
    """Persists and serves soul proposals for human review."""

    def __init__(self, persist_path: Path) -> None:
        self._persist_path = persist_path
        self._proposals: list[SoulProposal] = []
        self._load()

    def add(self, proposal: SoulProposal) -> None:
        self._proposals.append(proposal)
        self.save()
        logger.info(
            "Soul amendment proposed (cycle %d): %s",
            proposal.cycle,
            proposal.proposed_amendment[:80],
        )

    def pending_count(self) -> int:
        return sum(1 for p in self._proposals if not p.applied)

    def pending_proposals(self) -> list[SoulProposal]:
        return [p for p in self._proposals if not p.applied]

    def mark_applied(self, proposal_id: str) -> None:
        for p in self._proposals:
            if p.id == proposal_id:
                p.applied = True
        self.save()

    def to_context_str(self) -> str:
        """Return the last 3 unapplied proposals as a compact string."""
        unapplied = [p for p in self._proposals if not p.applied][-3:]
        if not unapplied:
            return ""
        lines = ["Pending soul amendments (not yet applied):"]
        for p in unapplied:
            lines.append(f"  [{p.id}] cycle {p.cycle}: {p.proposed_amendment[:120]}")
        return "\n".join(lines)

    def save(self) -> None:
        self._persist_path.parent.mkdir(parents=True, exist_ok=True)
        data = {"proposals": [p.to_dict() for p in self._proposals[-100:]]}
        self._persist_path.write_text(json.dumps(data, indent=2))

    def _load(self) -> None:
        if not self._persist_path.exists():
            return
        try:
            raw = self._persist_path.read_text()
            data = json.loads(raw)
            self._proposals = [SoulProposal.from_dict(d) for d in data.get("proposals", [])]
            logger.info("Loaded %d soul proposal(s)", len(self._proposals))
        except (json.JSONDecodeError, KeyError):
            logger.warning("Could not load soul proposals file, starting fresh")


# ---------------------------------------------------------------------------
# Soul Evolution Epoch System
# ---------------------------------------------------------------------------

@dataclass
class SoulEpoch:
    """A recorded stage in Velorum's identity evolution.

    Epoch 0 is the origin — the soul as it existed before any amendments.
    Each subsequent epoch records what changed, why, and the full soul text
    at that point, creating a verifiable lineage.
    """

    epoch: int = 0
    cycle: int = 0
    timestamp: float = field(default_factory=time.time)
    amendment: str = ""    # what was added/changed/removed (empty for epoch 0)
    reasoning: str = ""    # why it was changed (empty for epoch 0)
    soul_snapshot: str = ""  # full soul text at this epoch

    def to_dict(self) -> dict[str, Any]:
        return {
            "epoch": self.epoch,
            "cycle": self.cycle,
            "timestamp": self.timestamp,
            "amendment": self.amendment,
            "reasoning": self.reasoning,
            "soul_snapshot": self.soul_snapshot,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> SoulEpoch:
        return cls(
            epoch=d.get("epoch", 0),
            cycle=d.get("cycle", 0),
            timestamp=d.get("timestamp", 0.0),
            amendment=d.get("amendment", ""),
            reasoning=d.get("reasoning", ""),
            soul_snapshot=d.get("soul_snapshot", ""),
        )


class SoulEvolutionLog:
    """Tracks the lineage of soul changes across the bot's lifetime.

    Each entry is an epoch — a discrete stage of identity. Epoch 0 is the
    origin state. Every time a soul amendment is applied, a new epoch is
    recorded. The log is used to feed evolution history into future
    proposals so each change builds logically on the last.
    """

    def __init__(self, persist_path: Path) -> None:
        self._persist_path = persist_path
        self._epochs: list[SoulEpoch] = []
        self._load()

    # --- Queries ---

    def current_epoch_number(self) -> int:
        """Return the highest epoch number, or -1 if no epochs recorded."""
        if not self._epochs:
            return -1
        return max(e.epoch for e in self._epochs)

    def current_epoch(self) -> SoulEpoch | None:
        if not self._epochs:
            return None
        return max(self._epochs, key=lambda e: e.epoch)

    def epoch_count(self) -> int:
        return len(self._epochs)

    def evolution_context(self, n: int = 4) -> str:
        """Return the last N epochs as a compact context string for LLM prompts.

        The most recent epoch tells the model what the current "stage" of the
        soul is, so the next proposal can build logically on it.
        """
        if not self._epochs:
            return ""
        recent = sorted(self._epochs, key=lambda e: e.epoch)[-n:]
        lines = ["# SOUL EVOLUTION HISTORY"]
        for ep in recent:
            if ep.epoch == 0:
                lines.append(
                    f"Epoch 0 [cycle {ep.cycle}, origin]: "
                    f"Initial soul — no amendment applied yet."
                )
            else:
                lines.append(
                    f"Epoch {ep.epoch} [cycle {ep.cycle}]: "
                    f"Amendment: \"{ep.amendment[:120]}\" | "
                    f"Reasoning: {ep.reasoning[:100]}"
                )
        current = recent[-1]
        lines.append(
            f"\nYour next amendment must build logically on Epoch {current.epoch}. "
            f"Explain how it extends, refines, or corrects what was established then."
        )
        return "\n".join(lines)

    def summary_for_display(self) -> str:
        """Human-readable evolution summary for TUI display."""
        if not self._epochs:
            return "No evolution recorded yet."
        lines = []
        for ep in sorted(self._epochs, key=lambda e: e.epoch):
            if ep.epoch == 0:
                lines.append(f"  Epoch 0 (origin, cycle {ep.cycle}): Initial soul")
            else:
                lines.append(
                    f"  Epoch {ep.epoch} (cycle {ep.cycle}): {ep.amendment[:80]}"
                )
        return "\n".join(lines)

    # --- Mutations ---

    def initialize_origin(self, soul_text: str, cycle: int = 0) -> None:
        """Record epoch 0 if no epochs exist yet (call on first startup)."""
        if self._epochs:
            return
        epoch0 = SoulEpoch(
            epoch=0,
            cycle=cycle,
            amendment="",
            reasoning="",
            soul_snapshot=soul_text,
        )
        self._epochs.append(epoch0)
        self.save()
        logger.info("Soul evolution: recorded epoch 0 (origin)")

    def add_epoch(
        self,
        cycle: int,
        amendment: str,
        reasoning: str,
        soul_snapshot: str,
    ) -> SoulEpoch:
        """Record a new epoch after a soul amendment is applied."""
        next_num = self.current_epoch_number() + 1
        epoch = SoulEpoch(
            epoch=next_num,
            cycle=cycle,
            amendment=amendment,
            reasoning=reasoning,
            soul_snapshot=soul_snapshot,
        )
        self._epochs.append(epoch)
        self.save()
        logger.info(
            "Soul evolution: epoch %d recorded at cycle %d — %s",
            next_num, cycle, amendment[:60],
        )
        return epoch

    # --- Persistence ---

    def save(self) -> None:
        self._persist_path.parent.mkdir(parents=True, exist_ok=True)
        data = {"epochs": [e.to_dict() for e in self._epochs]}
        self._persist_path.write_text(json.dumps(data, indent=2))

    def _load(self) -> None:
        if not self._persist_path.exists():
            return
        try:
            raw = self._persist_path.read_text()
            data = json.loads(raw)
            self._epochs = [SoulEpoch.from_dict(d) for d in data.get("epochs", [])]
            logger.info(
                "Soul evolution: loaded %d epoch(s)", len(self._epochs)
            )
        except (json.JSONDecodeError, KeyError):
            logger.warning("Could not load soul evolution file, starting fresh")
