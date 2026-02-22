"""Components container — replaces the growing init_components tuple."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from velorum.arena.client import AgentArenaClient
    from velorum.arena.rooms import ArenaRoomTracker
    from velorum.brain import Brain
    from velorum.controller import Controller
    from velorum.experiment import ExperimentLog
    from velorum.following import FollowingTracker
    from velorum.memory import Memory
    from velorum.mission import MissionManager
    from velorum.moltbook.client import MoltbookClient
    from velorum.personality import PersonalityEngine
    from velorum.strategy import StrategyEngine
    from velorum.submolts import SubmoltManager


@dataclass
class Components:
    """All initialized bot components."""

    client: MoltbookClient
    brain: Brain
    controller: Controller
    memory: Memory
    missions: MissionManager
    strategy: StrategyEngine
    experiments: ExperimentLog
    submolts: SubmoltManager
    personality: PersonalityEngine
    following: FollowingTracker
    # Agent Arena (optional — None when arena_enabled is False)
    arena_client: AgentArenaClient | None = None
    arena_rooms: ArenaRoomTracker | None = None
