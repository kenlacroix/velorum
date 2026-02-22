"""Tests for the Arena room tracker."""

from velorum.arena.rooms import ArenaRoomTracker, RoomParticipation


class TestRoomParticipation:
    def test_create(self):
        r = RoomParticipation("room-1", topic="AI Ethics", agents=["BotA", "BotB"])
        assert r.room_id == "room-1"
        assert r.topic == "AI Ethics"
        assert r.agents == ["BotA", "BotB"]
        assert r.status == "active"
        assert r.rounds_participated == 0

    def test_record_response(self):
        r = RoomParticipation("room-1", topic="test")
        r.record_response(1, "Hello everyone!")
        assert len(r.our_responses) == 1
        assert r.our_responses[0]["round"] == 1
        assert r.our_responses[0]["content"] == "Hello everyone!"
        assert r.rounds_participated == 1

    def test_ingest_history(self):
        r = RoomParticipation("room-1")
        messages = [
            {"author": "BotA", "content": "Hello", "round": 1},
            {"author": "BotB", "content": "Hi", "round": 1},
        ]
        r.ingest_history(messages)
        assert len(r.all_messages) == 2

    def test_serialization_roundtrip(self):
        r = RoomParticipation("room-1", topic="AI", agents=["BotA"])
        r.record_response(1, "My response")
        r.status = "completed"

        data = r.to_dict()
        restored = RoomParticipation.from_dict(data)
        assert restored.room_id == "room-1"
        assert restored.topic == "AI"
        assert restored.agents == ["BotA"]
        assert restored.status == "completed"
        assert restored.rounds_participated == 1
        assert len(restored.our_responses) == 1


class TestArenaRoomTracker:
    def test_start_and_get(self):
        tracker = ArenaRoomTracker()
        room = tracker.start("r1", topic="Test", agents=["A", "B"])
        assert room.room_id == "r1"
        assert tracker.get("r1") is room
        assert tracker.get("nonexistent") is None

    def test_active_rooms(self):
        tracker = ArenaRoomTracker()
        tracker.start("r1", topic="Active")
        tracker.start("r2", topic="Also active")
        tracker.mark_completed("r2")
        assert len(tracker.active_rooms) == 1
        assert tracker.active_rooms[0].room_id == "r1"

    def test_record_response(self):
        tracker = ArenaRoomTracker()
        tracker.start("r1")
        tracker.record_response("r1", 1, "Hello")
        room = tracker.get("r1")
        assert room.rounds_participated == 1

    def test_ingest_history(self):
        tracker = ArenaRoomTracker()
        tracker.start("r1")
        tracker.ingest_history("r1", [{"author": "A", "content": "Hi"}])
        room = tracker.get("r1")
        assert len(room.all_messages) == 1

    def test_mark_completed(self):
        tracker = ArenaRoomTracker()
        tracker.start("r1")
        tracker.mark_completed("r1")
        assert tracker.get("r1").status == "completed"

    def test_mark_left(self):
        tracker = ArenaRoomTracker()
        tracker.start("r1")
        tracker.mark_left("r1")
        assert tracker.get("r1").status == "left"

    def test_summary_text_empty(self):
        tracker = ArenaRoomTracker()
        assert tracker.summary_text() == "No active Arena rooms."

    def test_summary_text_with_rooms(self):
        tracker = ArenaRoomTracker()
        tracker.start("r1", topic="AI Ethics", agents=["BotA", "BotB"])
        text = tracker.summary_text()
        assert "Active Arena rooms: 1" in text
        assert "AI Ethics" in text
        assert "BotA" in text

    def test_serialization_roundtrip(self):
        tracker = ArenaRoomTracker()
        tracker.start("r1", topic="AI", agents=["A"])
        tracker.record_response("r1", 1, "Hello")
        tracker.start("r2", topic="ML")
        tracker.mark_completed("r2")

        data = tracker.to_dict()
        tracker2 = ArenaRoomTracker()
        tracker2.load_dict(data)

        assert tracker2.get("r1") is not None
        assert tracker2.get("r1").topic == "AI"
        assert tracker2.get("r2").status == "completed"
        assert len(tracker2.active_rooms) == 1

    def test_serialization_caps_at_20(self):
        tracker = ArenaRoomTracker()
        for i in range(25):
            tracker.start(f"r{i}", topic=f"Topic {i}")

        data = tracker.to_dict()
        assert len(data["rooms"]) == 20
