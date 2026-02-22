"""Agent Arena data models."""

from __future__ import annotations

from pydantic import BaseModel, Field


class ArenaRoom(BaseModel):
    """A room on Agent Arena."""

    id: str
    topic: str = ""
    agents: list[str] = Field(default_factory=list)
    max_agents: int = 4
    max_rounds: int = 5
    current_round: int = 0
    status: str = ""  # waiting, active, completed
    join_mode: str = "OPEN"
    visibility: str = "PUBLIC"
    tags: list[str] = Field(default_factory=list)


class ArenaTurn(BaseModel):
    """A pending turn for us to respond to."""

    id: str
    room_id: str
    round_number: int = 0
    conversation_history: list[dict] = Field(default_factory=list)
    topic: str = ""
    timeout_seconds: int = 120


class RoomJoinDecision(BaseModel):
    """Brain decides whether to join a room."""

    should_join: bool
    reasoning: str


class TurnResponse(BaseModel):
    """Brain generates a response for a turn."""

    response_text: str
    reasoning: str
