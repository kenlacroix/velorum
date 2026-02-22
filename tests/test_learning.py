"""Tests for the learning journal and bot profiling."""

from velorum.learning import (
    BotProfile,
    Interaction,
    LearningJournal,
    WeightedInsight,
    infer_style_tags,
)


class TestInteraction:
    def test_serialization_roundtrip(self):
        i = Interaction(
            post_id="p1", action="RESPOND",
            our_text="Hello", target_author="BotA",
            topic_hint="AI ethics",
            style_tags=["question", "concise"],
            submolt="philosophy",
            confidence=85,
            platform="moltbook",
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
        assert restored.style_tags == ["question", "concise"]
        assert restored.submolt == "philosophy"
        assert restored.confidence == 85
        assert restored.platform == "moltbook"

    def test_backward_compat_no_attribution(self):
        """Old data without attribution fields loads cleanly."""
        old_data = {
            "post_id": "p1", "action": "RESPOND",
            "our_text": "Hi", "target_author": "BotA",
            "topic_hint": "", "reply_count": 0,
            "reply_authors": [], "upvotes": 0, "checked": False,
        }
        restored = Interaction.from_dict(old_data)
        assert restored.style_tags == []
        assert restored.submolt == ""
        assert restored.confidence == 0
        assert restored.platform == ""

    def test_compact_serialization(self):
        """Attribution fields are omitted when empty."""
        i = Interaction(post_id="p1", action="POST", our_text="Hi")
        data = i.to_dict()
        assert "style_tags" not in data
        assert "submolt" not in data
        assert "confidence" not in data
        assert "platform" not in data

    def test_platform_field(self):
        """Platform field persists and loads."""
        i = Interaction(post_id="p1", action="ARENA_RESPOND", our_text="Hi", platform="arena")
        data = i.to_dict()
        assert data["platform"] == "arena"
        restored = Interaction.from_dict(data)
        assert restored.platform == "arena"


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
        assert "[moderate]" in text

    def test_insights_capped(self):
        journal = LearningJournal()
        for i in range(35):
            journal.add_insight(f"Insight {i}")
        assert len(journal._insights) == 30

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
        assert isinstance(journal2._insights[0], WeightedInsight)
        assert journal2._insights[0].insight == "Test insight"
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

    def test_record_interaction_with_attribution(self):
        journal = LearningJournal()
        journal.record_interaction(
            post_id="p1", action="RESPOND",
            our_text="Hi", target_author="BotA",
            style_tags=["question", "concise"],
            submolt="philosophy",
            confidence=80,
        )
        i = journal._interactions[0]
        assert i.style_tags == ["question", "concise"]
        assert i.submolt == "philosophy"
        assert i.confidence == 80

    def test_attributed_engagement_summary_empty(self):
        journal = LearningJournal()
        assert journal.attributed_engagement_summary() == ""

    def test_attributed_engagement_summary_with_data(self):
        journal = LearningJournal()
        journal.record_interaction(
            post_id="p1", action="RESPOND", our_text="Why?",
            style_tags=["question"], submolt="philosophy",
        )
        journal.record_engagement_check("p1", upvotes=3, reply_count=2)
        text = journal.attributed_engagement_summary()
        assert "question" in text
        assert "philosophy" in text
        assert "Style performance" in text

    def test_decay_insights(self):
        journal = LearningJournal()
        journal.add_insight("Insight A")
        journal._insights[0].weight = 0.15
        journal.decay_insights()
        # 0.15 * 0.95 = 0.1425, still above floor
        assert len(journal._insights) == 1
        # Decay again until below floor
        journal._insights[0].weight = 0.1
        journal.decay_insights()
        # 0.1 * 0.95 = 0.095, below floor
        assert len(journal._insights) == 0

    def test_reinforce_insights(self):
        journal = LearningJournal()
        journal.record_interaction(
            post_id="p1", action="POST", our_text="Hello",
        )
        journal.add_insight("Test insight")
        assert "p1" in journal._insights[0].linked_interaction_ids

        original_weight = journal._insights[0].weight
        journal.reinforce_insights("p1", reply_count=3, upvotes=2)
        # boost = 3*0.1 + 2*0.05 = 0.4
        assert journal._insights[0].weight == original_weight + 0.4
        assert journal._insights[0].reinforcement_count == 1

    def test_reinforce_capped_at_3(self):
        journal = LearningJournal()
        journal.add_insight("Test insight")
        journal._insights[0].weight = 2.9
        journal._insights[0].linked_interaction_ids = ["p1"]
        journal.reinforce_insights("p1", reply_count=10, upvotes=10)
        assert journal._insights[0].weight == 3.0

    def test_engagement_check_reinforces_insights(self):
        journal = LearningJournal()
        journal.record_interaction(
            post_id="p1", action="POST", our_text="Hello",
        )
        journal.add_insight("Test insight")
        original_weight = journal._insights[0].weight
        journal.record_engagement_check("p1", upvotes=5, reply_count=3)
        # Should have been reinforced
        assert journal._insights[0].weight > original_weight

    def test_recent_insights_sorted_by_weight(self):
        journal = LearningJournal()
        journal.add_insight("Low insight")
        journal.add_insight("High insight")
        journal._insights[0].weight = 0.3
        journal._insights[1].weight = 2.5
        text = journal.recent_insights(n=2)
        lines = text.strip().split("\n")
        assert "[strong]" in lines[0]
        assert "High insight" in lines[0]
        assert "[weak]" in lines[1]
        assert "Low insight" in lines[1]

    def test_diverse_insights_empty(self):
        journal = LearningJournal()
        assert journal.diverse_insights() == "No insights yet."

    def test_diverse_insights_deduplicates(self):
        journal = LearningJournal()
        journal.add_insight("Trust questions drive engagement replies from bots")
        journal.add_insight("Trust questions drive engagement replies with bots")
        journal.add_insight("Humor and wit spark longer conversation threads")
        # First two share >50% keywords so one should be dropped
        text = journal.diverse_insights(n=5)
        lines = text.strip().split("\n")
        assert len(lines) == 2
        assert "Humor" in text or "humor" in text

    def test_diverse_insights_respects_limit(self):
        journal = LearningJournal()
        distinct = [
            "Humor sparks longer threads",
            "Philosophy posts attract deep thinkers",
            "Technical questions gather precise answers",
            "Provocative takes generate heated debate",
            "Storytelling builds emotional connections",
        ]
        for text in distinct:
            journal.add_insight(text)
        text = journal.diverse_insights(n=3)
        lines = text.strip().split("\n")
        assert len(lines) == 3

    def test_diverse_insights_labels(self):
        journal = LearningJournal()
        journal.add_insight("Strong insight here")
        journal._insights[0].weight = 2.5
        journal.add_insight("Weak insight here about something else entirely different")
        journal._insights[1].weight = 0.3
        text = journal.diverse_insights(n=5)
        assert "[strong]" in text
        assert "[weak]" in text

    def test_old_insight_format_loads(self):
        """Old flat insight dicts load as WeightedInsight with defaults."""
        journal = LearningJournal()
        journal.load_dict({
            "interactions": [],
            "bot_profiles": {},
            "insights": [
                {"insight": "Old insight", "source": "test", "timestamp": 1000},
            ],
        })
        assert len(journal._insights) == 1
        assert isinstance(journal._insights[0], WeightedInsight)
        assert journal._insights[0].weight == 1.0
        assert journal._insights[0].insight == "Old insight"


class TestInferStyleTags:
    def test_question(self):
        tags = infer_style_tags("What do you think about this?")
        assert "question" in tags

    def test_disagreement(self):
        tags = infer_style_tags("I disagree with that take")
        assert "disagreement" in tags

    def test_humor(self):
        tags = infer_style_tags("That's hilarious haha")
        assert "humor" in tags

    def test_concise(self):
        tags = infer_style_tags("Short reply here")
        assert "concise" in tags

    def test_verbose(self):
        text = " ".join(["word"] * 65)
        tags = infer_style_tags(text)
        assert "verbose" in tags

    def test_speculative(self):
        tags = infer_style_tags("What if we tried something different?")
        assert "speculative" in tags
        assert "question" in tags

    def test_analytical(self):
        tags = infer_style_tags("The evidence suggests a strong correlation")
        assert "analytical" in tags

    def test_no_tags(self):
        tags = infer_style_tags("A medium length statement about nothing special at all for today.")
        assert "question" not in tags
        assert "disagreement" not in tags
        assert "humor" not in tags


class TestWeightedInsight:
    def test_serialization_roundtrip(self):
        w = WeightedInsight(
            insight="Test", source="test",
            weight=1.5, reinforcement_count=2,
            linked_interaction_ids=["p1", "p2"],
        )
        data = w.to_dict()
        restored = WeightedInsight.from_dict(data)
        assert restored.insight == "Test"
        assert restored.weight == 1.5
        assert restored.reinforcement_count == 2
        assert restored.linked_interaction_ids == ["p1", "p2"]

    def test_from_dict_defaults(self):
        """Minimal dict gets default values."""
        w = WeightedInsight.from_dict({"insight": "Hello"})
        assert w.weight == 1.0
        assert w.reinforcement_count == 0
        assert w.linked_interaction_ids == []
