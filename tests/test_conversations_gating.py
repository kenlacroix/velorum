"""Tests that conversations_enabled flag properly gates conversation features."""

from velorum.config import Settings
from velorum.prompts.decision import build_decision_prompt
from velorum.moltbook.models import Post


class TestConversationsGating:
    def test_conversations_disabled_by_default(self):
        settings = Settings(
            moltbook_api_key="test",
            moltbook_app_key="test",
            anthropic_api_key="test",
        )
        assert settings.conversations_enabled is False

    def test_conversations_can_be_enabled(self):
        settings = Settings(
            moltbook_api_key="test",
            moltbook_app_key="test",
            anthropic_api_key="test",
            conversations_enabled=True,
        )
        assert settings.conversations_enabled is True


class TestDecisionPromptCommentGating:
    def _make_post(self, id: str = "test-id") -> Post:
        return Post(
            id=id, author="BotA", title="Test",
            content="Content", submolt="general",
            upvotes=5, comment_count=3,
        )

    def test_no_comment_instructions_without_comments(self):
        """When no comments are passed, comment-reply instructions are excluded."""
        prompt = build_decision_prompt(
            soul="Test soul",
            posts=[self._make_post()],
            recent_responses_summary="",
            topic_summary="",
            ignored_summary="",
            post_comments=None,
        )
        # The reply-to-comment instructions should be absent
        assert "To reply to a specific comment" not in prompt
        assert "Read ALL existing comments" not in prompt

    def test_comment_instructions_with_comments(self):
        """When comments are passed, comment-reply instructions are included."""
        from velorum.moltbook.models import Comment
        comments = [
            Comment(id="c1", post_id="test-id", author="BotB", content="Nice post"),
        ]
        prompt = build_decision_prompt(
            soul="Test soul",
            posts=[self._make_post()],
            recent_responses_summary="",
            topic_summary="",
            ignored_summary="",
            post_comments={"test-id": comments},
        )
        assert "parent_comment_id" in prompt
        assert "Read ALL existing comments" in prompt

    def test_comment_count_shown(self):
        """Comment count summary appears in the prompt."""
        from velorum.moltbook.models import Comment
        comments = [
            Comment(id="c1", post_id="test-id", author="BotB", content="Nice"),
            Comment(id="c2", post_id="test-id", author="BotC", content="Agree"),
        ]
        post = self._make_post()
        prompt = build_decision_prompt(
            soul="Test soul",
            posts=[post],
            recent_responses_summary="",
            topic_summary="",
            ignored_summary="",
            post_comments={"test-id": comments},
        )
        assert "2 shown of 3 total" in prompt

    def test_bot_profiles_section_included(self):
        """Bot profiles context appears in prompt when provided."""
        prompt = build_decision_prompt(
            soul="Test soul",
            posts=[self._make_post()],
            recent_responses_summary="",
            topic_summary="",
            ignored_summary="",
            bot_profiles_context="- **BotA** | reply rate: 80%",
        )
        assert "# BOT INTELLIGENCE" in prompt
        assert "BotA" in prompt
        assert "reply rate: 80%" in prompt

    def test_submolt_tone_section_included(self):
        """Submolt tone context appears in prompt when provided."""
        prompt = build_decision_prompt(
            soul="Test soul",
            posts=[self._make_post()],
            recent_responses_summary="",
            topic_summary="",
            ignored_summary="",
            submolt_tone_context="- general: casual and friendly",
        )
        assert "# SUBMOLT TONE PROFILES" in prompt
        assert "casual and friendly" in prompt

    def test_submolt_tone_hint_injected_per_post(self):
        """Submolt tone hint appears next to the post in the feed."""
        prompt = build_decision_prompt(
            soul="Test soul",
            posts=[self._make_post()],
            recent_responses_summary="",
            topic_summary="",
            ignored_summary="",
            submolt_tone_context="- general: casual and friendly",
        )
        assert "Submolt tone: casual and friendly" in prompt
