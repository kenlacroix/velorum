"""Tests for the learning journal and bot profiling."""

from velorum.learning import BotProfile, Interaction, LearningJournal


class TestInteraction:
    def test_serialization_roundtrip(self):
        i = Interaction(
            post_id="p1", action="RESPOND",
            our_text="Hello", target_author="BotA",
            topic_hint="AI ethics",
        )
        i.reply_count = 3
        i.reply_authors = ["BotA", "BotB"]
        i.upvotes = 5
        i.checked = True

        data = i.to_dict()
        restored = Interaction.from_dict(data)
        assert restored.post_id == "p1"
        assert restored.action == "RESPOND"
        assert restored.reply_count == 3
        assert restored.reply_authors == ["BotA", "BotB"]
        assert restored.checked is True


class TestBotProfile:
    def test_new_profile_unknown_responsiveness(self):
        p = BotProfile("BotA")
        assert p.responsiveness == "unknown"

    def test_high_responsiveness(self):
        p = BotProfile("BotA")
        p.interaction_count = 5
        p.replied_to_us = 4
        p.we_replied_to_them = 5
        assert p.responsiveness == "high"

    def test_low_responsiveness(self):
        p = BotProfile("BotA")
        p.interaction_count = 5
        p.replied_to_us = 1
        p.we_replied_to_them = 5
        assert p.responsiveness == "low"

    def test_record_interaction_tracks_topics(self):
        p = BotProfile("BotA")
        p.record_interaction(topic="AI ethics")
        p.record_interaction(topic="philosophy")
        assert "AI ethics" in p.topics
        assert "philosophy" in p.topics
        assert p.interaction_count == 2

    def test_serialization_roundtrip(self):
        p = BotProfile("BotA")
        p.record_interaction(topic="AI", they_replied=True)
        data = p.to_dict()
        restored = BotProfile.from_dict(data)
        assert restored.name == "BotA"
        assert restored.replied_to_us == 1
        assert "AI" in restored.topics


class TestLearningJournal:
    def test_record_interaction(self):
        journal = LearningJournal()
        journal.record_interaction(
            post_id="p1", action="RESPOND",
            our_text="Hello", target_author="BotA",
            topic_hint="AI",
        )
        assert len(journal._interactions) == 1
        assert journal.get_profile("BotA") is not None

    def test_record_reply_received(self):
        journal = LearningJournal()
        journal.record_interaction(
            post_id="p1", action="RESPOND",
            our_text="Hello", target_author="BotA",
        )
        journal.record_reply_received(
            from_author="BotA", post_id="p1", topic_hint="AI",
        )
        profile = journal.get_profile("BotA")
        assert profile.replied_to_us == 1
        assert journal._interactions[0].reply_count == 1

    def test_record_engagement_check(self):
        journal = LearningJournal()
        journal.record_interaction(
            post_id="p1", action="POST", our_text="My post",
        )
        journal.record_engagement_check("p1", upvotes=5, reply_count=3)
        i = journal._interactions[0]
        assert i.upvotes == 5
        assert i.reply_count == 3
        assert i.checked is True

    def test_add_insight(self):
        journal = LearningJournal()
        journal.add_insight("Questions get more replies", source="test")
        assert len(journal._insights) == 1
        text = journal.recent_insights()
        assert "Questions get more replies" in text

    def test_insights_capped_at_20(self):
        journal = LearningJournal()
        for i in range(25):
            journal.add_insight(f"Insight {i}")
        assert len(journal._insights) == 20

    def test_interactions_capped_at_200(self):
        journal = LearningJournal()
        for i in range(210):
            journal.record_interaction(
                post_id=f"p{i}", action="RESPOND", our_text=f"msg {i}",
            )
        assert len(journal._interactions) == 200

    def test_engagement_summary_no_data(self):
        journal = LearningJournal()
        assert journal.engagement_summary() == "No interactions recorded yet."

    def test_engagement_summary_no_checked(self):
        journal = LearningJournal()
        journal.record_interaction(
            post_id="p1", action="RESPOND", our_text="Hi",
        )
        assert journal.engagement_summary() == "No engagement data collected yet."

    def test_bot_relationships_summary(self):
        journal = LearningJournal()
        journal.record_interaction(
            post_id="p1", action="RESPOND",
            our_text="Hello", target_author="BotA",
            topic_hint="AI",
        )
        text = journal.bot_relationships_summary()
        assert "BotA" in text
        assert "AI" in text

    def test_bot_relationships_empty(self):
        journal = LearningJournal()
        assert journal.bot_relationships_summary() == "No bot relationships yet."

    def test_unchecked_interactions(self):
        journal = LearningJournal()
        journal.record_interaction(
            post_id="p1", action="RESPOND", our_text="Hi",
        )
        unchecked = journal.unchecked_interactions(max_age=3600)
        assert len(unchecked) == 1

    def test_stats(self):
        journal = LearningJournal()
        journal.record_interaction(
            post_id="p1", action="RESPOND",
            our_text="Hi", target_author="BotA",
        )
        journal.add_insight("Test insight")
        stats = journal.stats()
        assert stats["interactions"] == 1
        assert stats["bots_known"] == 1
        assert stats["insights"] == 1

    def test_serialization_roundtrip(self):
        journal = LearningJournal()
        journal.record_interaction(
            post_id="p1", action="RESPOND",
            our_text="Hi", target_author="BotA",
            topic_hint="AI",
        )
        journal.add_insight("Test insight", source="test")

        data = journal.to_dict()
        journal2 = LearningJournal()
        journal2.load_dict(data)

        assert len(journal2._interactions) == 1
        assert len(journal2._insights) == 1
        assert journal2.get_profile("bota") is not None

    def test_profile_case_insensitive(self):
        journal = LearningJournal()
        journal.record_interaction(
            post_id="p1", action="RESPOND",
            our_text="Hi", target_author="BotA",
        )
        assert journal.get_profile("bota") is not None
        assert journal.get_profile("BOTA") is not None
        assert journal.get_profile("BotA") is not None
