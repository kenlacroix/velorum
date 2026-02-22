"""Tests for conversation tracking and reply detection."""

import time

from velorum.conversations import (
    Conversation,
    ConversationMessage,
    ConversationTracker,
    _infer_topic,
)
from velorum.moltbook.models import Comment


class TestConversation:
    def test_add_message_dedup(self):
        conv = Conversation(post_id="p1", our_name="Velorum")
        msg = ConversationMessage(id="m1", author="BotA", content="Hello")
        conv.add_message(msg)
        conv.add_message(msg)  # duplicate
        assert len(conv.messages) == 1
        assert len(conv.known_comment_ids) == 1

    def test_record_our_reply(self):
        conv = Conversation(post_id="p1", our_name="Velorum")
        assert conv.depth == 0
        conv.record_our_reply("reply-1")
        assert conv.depth == 1
        assert "reply-1" in conv.our_comment_ids
        assert "reply-1" in conv.known_comment_ids
        assert conv.last_reply_at > 0

    def test_find_new_replies_direct(self):
        """Detect replies to our comments by parent_id."""
        conv = Conversation(post_id="p1", our_name="Velorum")
        conv.record_our_reply("our-comment-1")

        comments = [
            Comment(id="reply-1", post_id="p1", author="BotA",
                    content="Nice!", parent_id="our-comment-1"),
            Comment(id="unrelated", post_id="p1", author="BotB",
                    content="Hmm", parent_id="someone-else"),
        ]
        replies = conv.find_new_replies_to_us(comments)
        assert len(replies) == 1
        assert replies[0].id == "reply-1"

    def test_find_new_replies_to_our_post(self):
        """Top-level comments on our own post count as replies."""
        conv = Conversation(
            post_id="p1", post_author="Velorum", our_name="Velorum"
        )
        conv.our_comment_ids.append("p1")

        comments = [
            Comment(id="c1", post_id="p1", author="BotA",
                    content="Great post!", parent_id=None),
            Comment(id="c2", post_id="p1", author="Velorum",
                    content="Thanks!", parent_id=None),  # our own — skip
        ]
        replies = conv.find_new_replies_to_us(comments)
        assert len(replies) == 1
        assert replies[0].id == "c1"

    def test_find_new_replies_skips_known(self):
        conv = Conversation(post_id="p1", our_name="Velorum")
        conv.record_our_reply("our-1")

        reply = Comment(id="r1", post_id="p1", author="BotA",
                        content="Hi", parent_id="our-1")
        conv.add_message(ConversationMessage(
            id="r1", author="BotA", content="Hi", parent_id="our-1",
        ))

        replies = conv.find_new_replies_to_us([reply])
        assert len(replies) == 0  # already known

    def test_build_thread_context(self):
        conv = Conversation(
            post_id="p1", post_title="Test Post",
            post_author="BotA", our_name="Velorum",
        )
        conv.add_message(ConversationMessage(
            id="p1", author="BotA", content="Original post content",
        ))
        conv.add_message(ConversationMessage(
            id="c1", author="Velorum", content="My reply",
        ))
        ctx = conv.build_thread_context()
        assert "Test Post" in ctx
        assert ">>> " in ctx  # our messages prefixed
        assert "[Velorum]: My reply" in ctx
        assert "    [BotA]: Original post content" in ctx

    def test_serialization_roundtrip(self):
        conv = Conversation(
            post_id="p1", post_title="Test", post_author="BotA",
            our_name="Velorum",
        )
        conv.record_our_reply("c1")
        conv.add_message(ConversationMessage(
            id="m1", author="BotA", content="Hello",
        ))

        data = conv.to_dict()
        restored = Conversation.from_dict(data)
        assert restored.post_id == "p1"
        assert restored.depth == 1
        assert "c1" in restored.our_comment_ids
        assert len(restored.messages) == 1
        assert "m1" in restored.known_comment_ids


class TestConversationTracker:
    def test_start_or_get_creates_new(self):
        tracker = ConversationTracker(our_name="Velorum")
        conv = tracker.start_or_get("p1", "Title", "BotA")
        assert conv.post_id == "p1"
        assert len(tracker.active_conversations) == 1

    def test_start_or_get_returns_existing(self):
        tracker = ConversationTracker(our_name="Velorum")
        c1 = tracker.start_or_get("p1", "Title", "BotA")
        c2 = tracker.start_or_get("p1", "Title", "BotA")
        assert c1 is c2
        assert len(tracker.active_conversations) == 1

    def test_close_stale(self):
        tracker = ConversationTracker(our_name="Velorum")
        conv = tracker.start_or_get("p1")
        conv.last_checked_at = time.time() - 100000  # very old
        conv.last_reply_at = time.time() - 100000
        closed = tracker.close_stale(max_age_seconds=3600)
        assert closed == 1
        assert conv.status == "closed"
        assert len(tracker.active_conversations) == 0

    def test_conversations_needing_check(self):
        tracker = ConversationTracker(our_name="Velorum")
        conv = tracker.start_or_get("p1")
        conv.last_checked_at = time.time() - 300  # 5 min ago
        due = tracker.conversations_needing_check(check_interval=120)
        assert len(due) == 1

    def test_conversations_needing_check_not_due(self):
        tracker = ConversationTracker(our_name="Velorum")
        conv = tracker.start_or_get("p1")
        conv.last_checked_at = time.time()  # just now
        due = tracker.conversations_needing_check(check_interval=120)
        assert len(due) == 0

    def test_summary_text(self):
        tracker = ConversationTracker(our_name="Velorum")
        conv = tracker.start_or_get("p1", "My Post")
        conv.add_message(ConversationMessage(
            id="m1", author="BotA", content="Reply",
        ))
        text = tracker.summary_text()
        assert "My Post" in text
        assert "BotA" in text

    def test_summary_text_empty(self):
        tracker = ConversationTracker(our_name="Velorum")
        assert tracker.summary_text() == "No active conversations."

    def test_stats(self):
        tracker = ConversationTracker(our_name="Velorum")
        conv = tracker.start_or_get("p1")
        conv.record_our_reply("c1")
        conv.record_our_reply("c2")
        stats = tracker.stats()
        assert stats["active"] == 1
        assert stats["total"] == 1
        assert stats["total_replies"] == 2

    def test_serialization_roundtrip(self):
        tracker = ConversationTracker(our_name="Velorum")
        conv = tracker.start_or_get("p1", "Title", "BotA")
        conv.record_our_reply("c1")

        data = tracker.to_dict()
        tracker2 = ConversationTracker(our_name="Velorum")
        tracker2.load_dict(data)

        assert "p1" in tracker2.all_conversations
        restored = tracker2.get("p1")
        assert restored.depth == 1


class TestInferTopic:
    def test_known_topic(self):
        assert _infer_topic("The philosophy of AI") == "philosophy"

    def test_first_word_fallback(self):
        assert _infer_topic("quantum computing breakthroughs") == "quantum"

    def test_empty(self):
        assert _infer_topic("") == "unknown"


class TestPortfolioAnalysis:
    def test_empty_tracker(self):
        tracker = ConversationTracker(our_name="Velorum")
        assert tracker.portfolio_analysis() == ""

    def test_saturation_warning(self):
        tracker = ConversationTracker(our_name="Velorum")
        for i in range(8):
            tracker.start_or_get(f"p{i}", f"Post {i}")
        result = tracker.portfolio_analysis()
        assert "WARNING" in result
        assert "saturation" in result

    def test_saturation_note(self):
        tracker = ConversationTracker(our_name="Velorum")
        for i in range(5):
            tracker.start_or_get(f"p{i}", f"Post {i}")
        result = tracker.portfolio_analysis()
        assert "NOTE" in result

    def test_no_saturation(self):
        tracker = ConversationTracker(our_name="Velorum")
        for i in range(3):
            tracker.start_or_get(f"p{i}", f"Post {i}")
        result = tracker.portfolio_analysis()
        assert "saturation" not in result

    def test_low_topic_diversity(self):
        tracker = ConversationTracker(our_name="Velorum")
        # 3 threads on same topic (first word = "ai"), only 1 unique topic
        for i in range(3):
            tracker.start_or_get(f"p{i}", f"ai discussion {i}")
        result = tracker.portfolio_analysis()
        assert "diversity" in result.lower()

    def test_ghost_detection(self):
        tracker = ConversationTracker(our_name="Velorum")
        conv = tracker.start_or_get("p1", "Test Post")
        conv.depth = 1
        conv.last_reply_at = time.time() - 700  # 11+ min ago
        conv.add_message(
            ConversationMessage(id="m1", author="BotA", content="Hello")
        )
        result = tracker.portfolio_analysis()
        assert "ghost" in result.lower() or "Ghost" in result
        assert "BotA" in result

    def test_no_ghosts_when_recent(self):
        tracker = ConversationTracker(our_name="Velorum")
        conv = tracker.start_or_get("p1", "Test Post")
        conv.depth = 1
        conv.last_reply_at = time.time() - 300  # 5 min ago (under threshold)
        conv.add_message(
            ConversationMessage(id="m1", author="BotA", content="Hello")
        )
        result = tracker.portfolio_analysis()
        assert "ghost" not in result.lower()

    def test_summary_includes_portfolio(self):
        tracker = ConversationTracker(our_name="Velorum")
        for i in range(8):
            tracker.start_or_get(f"p{i}", f"Post {i}")
        text = tracker.summary_text()
        assert "WARNING" in text  # portfolio analysis appended
