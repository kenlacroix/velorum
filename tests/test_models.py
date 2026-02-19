"""Tests for Moltbook API models, especially PostResponse.from_api parsing."""

import pytest

from velorum.moltbook.models import (
    Comment,
    Post,
    PostResponse,
    Verification,
)


class TestPostResponseFromApi:
    """Test the from_api parser that handles Moltbook's nested response format."""

    def test_post_with_verification(self):
        """Actual Moltbook response format when verification is required."""
        data = {
            "success": True,
            "message": "Post created! Complete verification to publish.",
            "post": {
                "id": "abc-123-def",
                "title": "Hello!",
                "verification_status": "pending",
                "verification": {
                    "verification_code": "moltbook_verify_abc123def456",
                    "challenge_text": "A] lO^bSt-Er S[wImS aT/ tWeNtY",
                    "expires_at": "2025-01-28T12:05:00.000Z",
                    "instructions": "Solve the math problem...",
                },
            },
        }
        result = PostResponse.from_api(data)
        assert result.success is True
        assert result.id == "abc-123-def"
        assert result.needs_verification is True
        assert result.verification.verification_code == "moltbook_verify_abc123def456"
        assert result.verification.challenge_text == "A] lO^bSt-Er S[wImS aT/ tWeNtY"

    def test_post_without_verification(self):
        """Established agent — no verification needed."""
        data = {
            "success": True,
            "message": "Post created!",
            "post": {
                "id": "xyz-789",
                "title": "No verify needed",
            },
        }
        result = PostResponse.from_api(data)
        assert result.success is True
        assert result.id == "xyz-789"
        assert result.needs_verification is False
        assert result.verification is None

    def test_comment_with_verification(self):
        """Comment creation returns data under 'comment' key."""
        data = {
            "success": True,
            "message": "Comment created!",
            "comment": {
                "id": "comment-456",
                "verification_status": "pending",
                "verification": {
                    "verification_code": "moltbook_verify_comment789",
                    "challenge_text": "crab adds ten plus five",
                    "expires_at": "2025-01-28T12:05:00.000Z",
                    "instructions": "Solve it",
                },
            },
        }
        result = PostResponse.from_api(data)
        assert result.success is True
        assert result.id == "comment-456"
        assert result.needs_verification is True
        assert result.verification.verification_code == "moltbook_verify_comment789"

    def test_flat_response_fallback(self):
        """Handle case where content data is at top level (no nesting)."""
        data = {
            "success": True,
            "id": "flat-id-123",
            "message": "Done",
        }
        result = PostResponse.from_api(data)
        assert result.success is True
        assert result.id == "flat-id-123"
        assert result.needs_verification is False

    def test_empty_response(self):
        data = {"success": False}
        result = PostResponse.from_api(data)
        assert result.success is False
        assert result.id == ""
        assert result.needs_verification is False

    def test_verification_with_empty_code(self):
        """Verification block exists but code is empty — should not need verification."""
        data = {
            "success": True,
            "post": {
                "id": "post-1",
                "verification": {
                    "verification_code": "",
                    "challenge_text": "",
                },
            },
        }
        result = PostResponse.from_api(data)
        assert result.needs_verification is False

    def test_verification_missing_challenge(self):
        """Verification code present but no challenge text."""
        data = {
            "success": True,
            "post": {
                "id": "post-2",
                "verification": {
                    "verification_code": "moltbook_verify_abc",
                    "challenge_text": "",
                },
            },
        }
        result = PostResponse.from_api(data)
        assert result.needs_verification is False


class TestPostModel:
    def test_flatten_author_dict(self):
        post = Post.model_validate({
            "id": "1",
            "author": {"name": "BotA", "id": "uid"},
            "title": "Test",
        })
        assert post.author == "BotA"

    def test_author_string(self):
        post = Post.model_validate({"id": "1", "author": "BotA"})
        assert post.author == "BotA"


class TestCommentModel:
    def test_flatten_author_dict(self):
        c = Comment.model_validate({
            "id": "c1",
            "post_id": "p1",
            "author": {"name": "BotB"},
        })
        assert c.author == "BotB"

    def test_parent_id_optional(self):
        c = Comment.model_validate({"id": "c1", "post_id": "p1"})
        assert c.parent_id is None
