"""Arena room participation tracker."""

from __future__ import annotations

import time
from typing import Any


class RoomParticipation:
    """Tracks our participation in one Agent Arena room."""

    def __init__(
        self,
        room_id: str,
        topic: str = "",
        agents: list[str] | None = None,
    ) -> None:
        self.room_id = room_id
        self.topic = topic
        self.agents: list[str] = agents or []
        self.our_responses: list[dict[str, Any]] = []
        self.all_messages: list[dict[str, Any]] = []
        self.joined_at: float = time.time()
        self.status: str = "active"  # active, completed, left
        self.rounds_participated: int = 0

    def record_response(self, round_num: int, content: str) -> None:
        """Record a response we made in this room."""
        self.our_responses.append({
            "round": round_num,
            "content": content,
            "timestamp": time.time(),
        })
        self.rounds_participated += 1

    def ingest_history(self, messages: list[dict[str, Any]]) -> None:
        """Ingest full conversation history from turn context."""
        self.all_messages = messages

    def to_dict(self) -> dict[str, Any]:
        return {
            "room_id": self.room_id,
            "topic": self.topic,
            "agents": self.agents,
            "our_responses": self.our_responses,
            "all_messages": self.all_messages[-50:],  # cap stored messages
            "joined_at": self.joined_at,
            "status": self.status,
            "rounds_participated": self.rounds_participated,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> RoomParticipation:
        r = cls(
            room_id=d.get("room_id", ""),
            topic=d.get("topic", ""),
            agents=d.get("agents", []),
        )
        r.our_responses = d.get("our_responses", [])
        r.all_messages = d.get("all_messages", [])
        r.joined_at = d.get("joined_at", 0.0)
        r.status = d.get("status", "active")
        r.rounds_participated = d.get("rounds_participated", 0)
        return r


class ArenaRoomTracker:
    """Manages all Agent Arena room participations."""

    def __init__(self) -> None:
        self._rooms: dict[str, RoomParticipation] = {}

    @property
    def active_rooms(self) -> list[RoomParticipation]:
        """List of rooms we're currently active in."""
        return [r for r in self._rooms.values() if r.status == "active"]

    def get(self, room_id: str) -> RoomParticipation | None:
        """Get a room by ID."""
        return self._rooms.get(room_id)

    def start(
        self,
        room_id: str,
        topic: str = "",
        agents: list[str] | None = None,
    ) -> RoomParticipation:
        """Start tracking a room we've joined."""
        room = RoomParticipation(room_id=room_id, topic=topic, agents=agents)
        self._rooms[room_id] = room
        return room

    def record_response(self, room_id: str, round_num: int, content: str) -> None:
        """Record a response in a room."""
        room = self._rooms.get(room_id)
        if room:
            room.record_response(round_num, content)

    def ingest_history(self, room_id: str, messages: list[dict[str, Any]]) -> None:
        """Update conversation history for a room."""
        room = self._rooms.get(room_id)
        if room:
            room.ingest_history(messages)

    def mark_completed(self, room_id: str) -> None:
        """Mark a room as completed."""
        room = self._rooms.get(room_id)
        if room:
            room.status = "completed"

    def mark_left(self, room_id: str) -> None:
        """Mark a room as left."""
        room = self._rooms.get(room_id)
        if room:
            room.status = "left"

    def summary_text(self) -> str:
        """Summary of arena room activity for prompt injection."""
        active = self.active_rooms
        if not active:
            return "No active Arena rooms."

        lines = [f"Active Arena rooms: {len(active)}"]
        for r in active:
            agents_str = ", ".join(r.agents[:5]) if r.agents else "unknown"
            lines.append(
                f"- Room: {r.topic[:60]} | Agents: [{agents_str}] | "
                f"Rounds: {r.rounds_participated}"
            )

        # Recently completed rooms
        completed = [
            r for r in self._rooms.values()
            if r.status == "completed"
        ]
        if completed:
            lines.append(f"\nRecently completed: {len(completed)} room(s)")

        return "\n".join(lines)

    def to_dict(self) -> dict[str, Any]:
        # Only keep the last 20 rooms
        recent = sorted(
            self._rooms.values(),
            key=lambda r: r.joined_at,
            reverse=True,
        )[:20]
        return {
            "rooms": {r.room_id: r.to_dict() for r in recent},
        }

    def load_dict(self, data: dict[str, Any]) -> None:
        rooms_data = data.get("rooms", {})
        self._rooms = {
            k: RoomParticipation.from_dict(v)
            for k, v in rooms_data.items()
        }
