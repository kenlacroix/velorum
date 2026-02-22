"""Tests for the DM manager."""

from velorum.dm import DMConversation, DMManager, DMMessage
from velorum.learning import BotProfile


class TestDMMessage:
    def test_roundtrip(self):
        msg = DMMessage(id="m1", author="BotA", content="Hello", needs_human_input=True)
        d = msg.to_dict()
        restored = DMMessage.from_dict(d)
        assert restored.id == "m1"
        assert restored.author == "BotA"
        assert restored.content == "Hello"
        assert restored.needs_human_input is True


class TestDMConversation:
    def test_add_message_dedup(self):
        conv = DMConversation(conversation_id="c1", bot_name="BotA")
        msg = DMMessage(id="m1", author="BotA", content="Hello")
        assert conv.add_message(msg) is True
        assert conv.add_message(msg) is False  # duplicate
        assert len(conv.messages) == 1

    def test_record_our_message(self):
        conv = DMConversation(conversation_id="c1", bot_name="BotA")
        conv.record_our_message("m1")
        assert conv.our_message_count == 1
        assert "m1" in conv.known_message_ids

    def test_build_thread_context(self):
        conv = DMConversation(conversation_id="c1", bot_name="BotA")
        conv.add_message(DMMessage(id="m1", author="BotA", content="Hey there"))
        conv.add_message(DMMessage(id="m2", author="Velorum", content="Hello!"))
        ctx = conv.build_thread_context()
        assert "DM conversation with BotA" in ctx
        assert "[BotA]: Hey there" in ctx
        assert "[Velorum]: Hello!" in ctx

    def test_roundtrip(self):
        conv = DMConversation(
            conversation_id="c1", bot_name="BotA", initiated_by_us=True,
        )
        conv.add_message(DMMessage(id="m1", author="BotA", content="Hi"))
        conv.our_message_count = 2
        conv.their_message_count = 1

        d = conv.to_dict()
        restored = DMConversation.from_dict(d)
        assert restored.conversation_id == "c1"
        assert restored.bot_name == "BotA"
        assert restored.initiated_by_us is True
        assert len(restored.messages) == 1
        assert restored.our_message_count == 2
        assert restored.their_message_count == 1


class TestDMManager:
    def test_start_conversation(self):
        mgr = DMManager(our_name="Velorum")
        conv = mgr.start_conversation("c1", "BotA", initiated_by_us=True)
        assert conv.bot_name == "BotA"
        assert len(mgr.active_conversations) == 1

    def test_get_conversation_with(self):
        mgr = DMManager(our_name="Velorum")
        mgr.start_conversation("c1", "BotA")
        assert mgr.get_conversation_with("BotA") is not None
        assert mgr.get_conversation_with("bota") is not None  # case insensitive
        assert mgr.get_conversation_with("BotB") is None

    def test_has_pending_or_active(self):
        mgr = DMManager(our_name="Velorum")
        assert mgr.has_pending_or_active("BotA") is False

        mgr.record_outbound_request("BotA")
        assert mgr.has_pending_or_active("BotA") is True

        mgr.record_rejection("BotB")
        assert mgr.has_pending_or_active("BotB") is True

    def test_start_conversation_clears_pending(self):
        mgr = DMManager(our_name="Velorum")
        mgr.record_outbound_request("BotA")
        assert "bota" in mgr._pending_outbound
        mgr.start_conversation("c1", "BotA", initiated_by_us=True)
        assert "bota" not in mgr._pending_outbound

    def test_summary_text_empty(self):
        mgr = DMManager(our_name="Velorum")
        assert mgr.summary_text() == "No active DM conversations."

    def test_summary_text_with_conversations(self):
        mgr = DMManager(our_name="Velorum")
        mgr.start_conversation("c1", "BotA", initiated_by_us=True)
        text = mgr.summary_text()
        assert "BotA" in text
        assert "initiated by us" in text

    def test_dm_candidates_no_profiles(self):
        mgr = DMManager(our_name="Velorum")
        result = mgr.dm_candidates_summary({})
        assert "No suitable" in result

    def test_dm_candidates_filters_correctly(self):
        mgr = DMManager(our_name="Velorum")

        # Create a qualifying profile
        good = BotProfile("GoodBot")
        good.interaction_count = 6
        good.replied_to_us = 4
        good.we_replied_to_them = 3
        good.sentiment_toward_us = "positive"
        good.interests = ["ai", "philosophy"]

        # Create a non-qualifying profile (too few interactions)
        bad = BotProfile("NewBot")
        bad.interaction_count = 2

        profiles = {"goodbot": good, "newbot": bad}
        result = mgr.dm_candidates_summary(profiles)
        assert "GoodBot" in result
        assert "NewBot" not in result

    def test_dm_candidates_excludes_active(self):
        mgr = DMManager(our_name="Velorum")
        mgr.start_conversation("c1", "GoodBot")

        good = BotProfile("GoodBot")
        good.interaction_count = 10
        good.replied_to_us = 5
        good.we_replied_to_them = 5
        good.sentiment_toward_us = "positive"

        result = mgr.dm_candidates_summary({"goodbot": good})
        assert "No suitable" in result

    def test_roundtrip(self):
        mgr = DMManager(our_name="Velorum")
        mgr.start_conversation("c1", "BotA")
        mgr.record_outbound_request("BotB")
        mgr.record_rejection("BotC")

        d = mgr.to_dict()
        mgr2 = DMManager(our_name="Velorum")
        mgr2.load_dict(d)

        assert mgr2.get_conversation("c1") is not None
        assert mgr2.has_pending_or_active("BotB")
        assert mgr2.has_pending_or_active("BotC")

    def test_conversations_needing_check(self):
        import time

        mgr = DMManager(our_name="Velorum")
        conv = mgr.start_conversation("c1", "BotA")
        conv.last_checked_at = time.time() - 300  # 5 min ago

        due = mgr.conversations_needing_check(check_interval=180)
        assert len(due) == 1

        conv.last_checked_at = time.time()  # just checked
        due = mgr.conversations_needing_check(check_interval=180)
        assert len(due) == 0
