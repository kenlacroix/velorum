"""Tests for the unified ContextBuilder."""

from velorum.context import PromptContext, build_context


class TestPromptContext:
    def test_for_decision_keys(self):
        ctx = PromptContext(
            mission_context="m",
            strategy_context="s",
            personality_context="p",
            available_submolts="sub",
            submolt_tone_context="tone",
            learning_insights="insights",
            conversations_summary="conv",
            bot_profiles_context="bots",
            recent_post_submolts="subs",
        )
        d = ctx.for_decision()
        assert d["mission_context"] == "m"
        assert d["strategy_context"] == "s"
        assert d["personality_context"] == "p"
        assert d["available_submolts"] == "sub"
        assert d["submolt_tone_context"] == "tone"
        assert d["learning_insights"] == "insights"
        assert d["conversations_summary"] == "conv"
        assert d["bot_profiles_context"] == "bots"
        assert d["recent_post_submolts"] == "subs"
        # Should NOT include engagement_summary or bot_relationships
        assert "engagement_summary" not in d
        assert "bot_relationships" not in d

    def test_for_reflection_keys(self):
        ctx = PromptContext(
            engagement_summary="eng",
            bot_relationships="rel",
            conversations_summary="conv",
            mission_context="m",
            strategy_context="s",
            personality_context="p",
            submolt_tone_context="tone",
            dm_summary="dms",
            following_summary="following",
            arena_rooms_summary="arena",
        )
        d = ctx.for_reflection()
        assert d["engagement_summary"] == "eng"
        assert d["bot_relationships"] == "rel"
        assert d["conversations_summary"] == "conv"
        assert d["mission_context"] == "m"
        assert d["strategy_context"] == "s"
        assert d["personality_context"] == "p"
        assert d["submolt_tone_context"] == "tone"
        assert d["dm_summary"] == "dms"
        assert d["following_summary"] == "following"
        assert d["arena_rooms_summary"] == "arena"

    def test_for_reply_keys(self):
        ctx = PromptContext(
            learning_insights="insights",
            mission_context="m",
            strategy_context="s",
            personality_context="p",
        )
        d = ctx.for_reply()
        assert d["learning_insights"] == "insights"
        assert d["mission_context"] == "m"
        assert d["strategy_context"] == "s"
        assert d["personality_context"] == "p"
        assert len(d) == 4

    def test_for_dm_reply_keys(self):
        ctx = PromptContext(
            mission_context="m",
            strategy_context="s",
            personality_context="p",
        )
        d = ctx.for_dm_reply()
        assert d["mission_context"] == "m"
        assert d["strategy_context"] == "s"
        assert d["personality_context"] == "p"
        assert len(d) == 3

    def test_for_post_keys(self):
        ctx = PromptContext(
            learning_insights="insights",
            bot_relationships="rel",
            engagement_summary="eng",
            conversations_summary="conv",
            mission_context="m",
            strategy_context="s",
            available_submolts="sub",
            personality_context="p",
            submolt_tone_context="tone",
            recent_post_submolts="subs",
        )
        d = ctx.for_post()
        assert d["learning_insights"] == "insights"
        assert d["bot_relationships"] == "rel"
        assert d["engagement_summary"] == "eng"
        assert d["conversations_summary"] == "conv"
        assert d["mission_context"] == "m"
        assert d["strategy_context"] == "s"
        assert d["available_submolts"] == "sub"
        assert d["personality_context"] == "p"
        assert d["submolt_tone_context"] == "tone"
        assert d["recent_post_submolts"] == "subs"

    def test_for_strategy_keys(self):
        ctx = PromptContext(
            engagement_summary="eng",
            bot_relationships="rel",
            learning_insights="insights",
            mission_context="m",
        )
        d = ctx.for_strategy()
        assert d["engagement_data"] == "eng"
        assert d["bot_profiles"] == "rel"
        assert d["insights"] == "insights"
        assert d["mission_context"] == "m"
        assert len(d) == 4

    def test_frozen(self):
        ctx = PromptContext(mission_context="m")
        try:
            ctx.mission_context = "changed"  # type: ignore[misc]
            assert False, "Should not allow mutation"
        except AttributeError:
            pass

    def test_defaults_are_empty_strings(self):
        ctx = PromptContext()
        assert ctx.mission_context == ""
        assert ctx.learning_insights == ""
        assert ctx.bot_profiles_context == ""
        assert ctx.dm_summary == ""
        assert ctx.dm_candidates == ""
        assert ctx.following_summary == ""
        assert ctx.arena_rooms_summary == ""
        assert ctx.recent_post_submolts == ""

    def test_new_fields(self):
        ctx = PromptContext(
            dm_summary="dm info",
            dm_candidates="candidates",
            following_summary="following info",
            arena_rooms_summary="arena info",
        )
        assert ctx.dm_summary == "dm info"
        assert ctx.dm_candidates == "candidates"
        assert ctx.following_summary == "following info"
        assert ctx.arena_rooms_summary == "arena info"
