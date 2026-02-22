"""Soul proposal system — rare LLM-driven amendments to Velorum's identity.

Proposals are written to file for human review; NOT auto-applied.
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
