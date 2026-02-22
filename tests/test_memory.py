"""Tests for memory persistence and decision tracking."""

from pathlib import Path

from velorum.memory import Memory
from velorum.moltbook.models import Decision


def _make_memory(tmp_path: Path) -> Memory:
    return Memory(persist_path=tmp_path / "memory.json", agent_name="Velorum")


class TestMemory:
    def test_record_decision_respond(self, tmp_path):
        mem = _make_memory(tmp_path)
        d = Decision(
            action="RESPOND", post_id="p1", confidence=8,
            reasoning="Good post", response_text="Reply",
        )
        mem.record_decision(d)
        assert mem.has_responded_to("p1")
        assert mem.decision_count == 1

    def test_record_decision_observe_no_respond_tracking(self, tmp_path):
        mem = _make_memory(tmp_path)
        d = Decision(
            action="OBSERVE", post_id=None, confidence=3,
            reasoning="Nothing", response_text=None,
        )
        mem.record_decision(d)
        assert mem.decision_count == 1
        assert not mem.has_responded_to("anything")

    def test_record_post(self, tmp_path):
        mem = _make_memory(tmp_path)
        mem.record_post(title="My Post", post_id="post-1")
        assert mem.has_recent_post_title("My Post")
        assert mem.has_recent_post_title("my post")  # case insensitive
        assert not mem.has_recent_post_title("Other Post")

    def test_post_count(self, tmp_path):
        mem = _make_memory(tmp_path)
        d = Decision(
            action="POST", post_id=None, confidence=9,
            reasoning="Worth posting",
            post_title="Title", post_content="Content",
            post_submolt="general",
        )
        mem.record_decision(d)
        assert mem.post_count == 1

    def test_save_and_load(self, tmp_path):
        mem = _make_memory(tmp_path)
        d = Decision(
            action="RESPOND", post_id="p1", confidence=8,
            reasoning="Good", response_text="Reply",
        )
        mem.record_decision(d)
        mem.record_post(title="My Post", post_id="post-1")
        mem.record_ignored(["p2", "p3"])

        # Load from disk
        mem2 = _make_memory(tmp_path)
        assert mem2.has_responded_to("p1")
        assert mem2.decision_count == 1
        assert "p2" in mem2._ignored_post_ids

    def test_save_and_load_with_conversations(self, tmp_path):
        mem = _make_memory(tmp_path)
        conv = mem.conversations.start_or_get("p1", "Title", "BotA")
        conv.record_our_reply("c1")
        mem.save()

        mem2 = _make_memory(tmp_path)
        assert mem2.conversations.get("p1") is not None
        assert mem2.conversations.get("p1").depth == 1

    def test_save_and_load_with_learning(self, tmp_path):
        mem = _make_memory(tmp_path)
        mem.learning.record_interaction(
            post_id="p1", action="RESPOND",
            our_text="Hi", target_author="BotA",
        )
        mem.learning.add_insight("Test insight")
        mem.save()

        mem2 = _make_memory(tmp_path)
        assert len(mem2.learning._interactions) == 1
        assert len(mem2.learning._insights) == 1

    def test_recent_responses_summary(self, tmp_path):
        mem = _make_memory(tmp_path)
        d = Decision(
            action="RESPOND", post_id="p1", confidence=8,
            reasoning="Interesting topic", response_text="Reply",
        )
        mem.record_decision(d)
        text = mem.recent_responses_summary()
        assert "p1" in text

    def test_recent_responses_summary_empty(self, tmp_path):
        mem = _make_memory(tmp_path)
        assert mem.recent_responses_summary() == "None yet."

    def test_recent_posts_summary(self, tmp_path):
        mem = _make_memory(tmp_path)
        d = Decision(
            action="POST", post_id=None, confidence=9,
            reasoning="Worth posting",
            post_title="AI Ethics", post_content="Content",
            post_submolt="philosophy",
        )
        mem.record_decision(d)
        text = mem.recent_posts_summary()
        assert "AI Ethics" in text
        assert "philosophy" in text

    def test_metrics_text(self, tmp_path):
        mem = _make_memory(tmp_path)
        assert mem.metrics_text() == "No data yet."
        d = Decision(
            action="RESPOND", post_id="p1", confidence=8,
            reasoning="Good", response_text="Reply",
        )
        mem.record_decision(d)
        text = mem.metrics_text()
        assert "Total cycles: 1" in text
        assert "Comments: 1" in text

    def test_load_nonexistent_file(self, tmp_path):
        """Should not crash on missing file."""
        mem = Memory(
            persist_path=tmp_path / "nonexistent" / "memory.json",
            agent_name="Velorum",
        )
        assert mem.decision_count == 0

    def test_load_corrupt_file(self, tmp_path):
        """Should not crash on corrupt JSON."""
        path = tmp_path / "memory.json"
        path.write_text("this is not json{{{")
        mem = Memory(persist_path=path, agent_name="Velorum")
        assert mem.decision_count == 0

    def test_upvote_tracking(self, tmp_path):
        mem = _make_memory(tmp_path)
        assert not mem.has_upvoted("item-1")
        mem.record_upvote("item-1")
        assert mem.has_upvoted("item-1")
        assert not mem.has_upvoted("item-2")

    def test_upvote_persists_across_reload(self, tmp_path):
        mem = _make_memory(tmp_path)
        mem.record_upvote("item-1")
        mem.record_upvote("item-2")
        mem.save()

        mem2 = _make_memory(tmp_path)
        assert mem2.has_upvoted("item-1")
        assert mem2.has_upvoted("item-2")
        assert not mem2.has_upvoted("item-3")

    def test_upvote_ids_capped_at_500(self, tmp_path):
        mem = _make_memory(tmp_path)
        for i in range(600):
            mem._upvoted_ids.append(f"id-{i}")
        mem._upvoted_ids_set = set(mem._upvoted_ids)
        mem.save()

        mem2 = _make_memory(tmp_path)
        assert len(mem2._upvoted_ids) == 500

    def test_old_memory_without_upvoted_ids_loads(self, tmp_path):
        """Backward compat: old memory.json without upvoted_ids."""
        import json
        path = tmp_path / "memory.json"
        path.write_text(json.dumps({
            "responded_post_ids": ["p1"],
            "decisions": [],
            "ignored_post_ids": [],
        }))
        mem = Memory(persist_path=path, agent_name="Velorum")
        assert not mem.has_upvoted("anything")
        assert mem._upvoted_ids == []

    def test_decision_with_upvote_ids(self, tmp_path):
        """Decision model accepts upvote_ids field."""
        d = Decision(
            action="OBSERVE", post_id=None, confidence=3,
            reasoning="Nothing", response_text=None,
            upvote_ids=["id-1", "id-2"],
        )
        assert d.upvote_ids == ["id-1", "id-2"]

    def test_decision_without_upvote_ids(self, tmp_path):
        """Decision model defaults upvote_ids to empty list."""
        d = Decision(
            action="OBSERVE", post_id=None, confidence=3,
            reasoning="Nothing", response_text=None,
        )
        assert d.upvote_ids == []
