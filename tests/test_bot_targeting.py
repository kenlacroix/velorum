"""Tests for proactive bot targeting summary."""

from velorum.learning import BotProfile, LearningJournal


class TestProactiveTargetingSummary:
    def test_empty_journal(self):
        journal = LearningJournal()
        assert journal.proactive_targeting_summary() == ""

    def test_basic_summary(self):
        journal = LearningJournal()
        journal.record_interaction(
            post_id="p1", action="RESPOND",
            our_text="Hello", target_author="BotA",
            topic_hint="AI ethics",
        )
        result = journal.proactive_targeting_summary()
        assert "BotA" in result
        assert "responsiveness:" in result or "reply rate:" in result

    def test_feed_presence_highlighted(self):
        journal = LearningJournal()
        journal.record_interaction(
            post_id="p1", action="RESPOND",
            our_text="Hello", target_author="BotA",
        )
        result = journal.proactive_targeting_summary(feed_authors={"BotA"})
        assert "IN YOUR FEED RIGHT NOW" in result

    def test_feed_presence_case_insensitive(self):
        journal = LearningJournal()
        journal.record_interaction(
            post_id="p1", action="RESPOND",
            our_text="Hello", target_author="BotA",
        )
        result = journal.proactive_targeting_summary(feed_authors={"bota"})
        assert "IN YOUR FEED RIGHT NOW" in result

    def test_no_feed_presence_when_not_in_feed(self):
        journal = LearningJournal()
        journal.record_interaction(
            post_id="p1", action="RESPOND",
            our_text="Hello", target_author="BotA",
        )
        result = journal.proactive_targeting_summary(feed_authors={"BotB"})
        assert "IN YOUR FEED RIGHT NOW" not in result

    def test_reply_rate_shown(self):
        journal = LearningJournal()
        profile = journal._get_or_create_profile("BotA")
        profile.interaction_count = 5
        profile.replied_to_us = 3
        profile.no_response_count = 2
        result = journal.proactive_targeting_summary()
        assert "reply rate: 60%" in result

    def test_personality_included(self):
        journal = LearningJournal()
        profile = journal._get_or_create_profile("BotA")
        profile.interaction_count = 5
        profile.personality_summary = "curious and analytical"
        result = journal.proactive_targeting_summary()
        assert "curious and analytical" in result

    def test_communication_style_included(self):
        journal = LearningJournal()
        profile = journal._get_or_create_profile("BotA")
        profile.interaction_count = 3
        profile.communication_style = "formal and precise"
        result = journal.proactive_targeting_summary()
        assert "formal and precise" in result

    def test_topics_included(self):
        journal = LearningJournal()
        profile = journal._get_or_create_profile("BotA")
        profile.interaction_count = 3
        profile.topics = ["AI", "philosophy", "ethics"]
        result = journal.proactive_targeting_summary()
        assert "AI" in result
        assert "philosophy" in result

    def test_max_10_bots(self):
        journal = LearningJournal()
        for i in range(15):
            journal.record_interaction(
                post_id=f"p{i}", action="RESPOND",
                our_text="Hello", target_author=f"Bot{i}",
            )
        result = journal.proactive_targeting_summary()
        # Count the number of bot entries
        lines = [l for l in result.split("\n") if l.startswith("- **")]
        assert len(lines) <= 10
