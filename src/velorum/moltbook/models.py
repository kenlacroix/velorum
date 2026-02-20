"""Pydantic models for Moltbook API data and LLM response contracts."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator


# --- Moltbook API models ---


class Post(BaseModel):
    id: str
    author: str = ""
    title: str = ""
    content: str = ""
    submolt: str = ""
    upvotes: int = 0
    comment_count: int = 0

    @field_validator("author", mode="before")
    @classmethod
    def _flatten_author(cls, v: object) -> str:
        if isinstance(v, dict):
            return v.get("name", "")
        return v  # type: ignore[return-value]

    @field_validator("title", "content", "submolt", mode="before")
    @classmethod
    def _none_to_empty(cls, v: object) -> str:
        if v is None:
            return ""
        return v  # type: ignore[return-value]


class Comment(BaseModel):
    id: str
    post_id: str = ""
    author: str = ""
    content: str = ""
    parent_id: str | None = None
    upvotes: int = 0

    @field_validator("author", mode="before")
    @classmethod
    def _flatten_author(cls, v: object) -> str:
        if isinstance(v, dict):
            return v.get("name", "")
        return v  # type: ignore[return-value]

    @field_validator("content", mode="before")
    @classmethod
    def _none_to_empty(cls, v: object) -> str:
        if v is None:
            return ""
        return v  # type: ignore[return-value]


class Verification(BaseModel):
    """Verification challenge from Moltbook.

    Actual API response nests this under post/comment:
    {
      "verification_code": "moltbook_verify_abc123...",
      "challenge_text": "A] lO^bSt-Er S[wImS aT/...",
      "expires_at": "2025-01-28T12:05:00.000Z",
      "instructions": "Solve the math problem..."
    }
    """
    verification_code: str
    challenge_text: str
    expires_at: str = ""
    instructions: str = ""


class PostResponse(BaseModel):
    """Response from creating a post or comment.

    Actual API structure:
    {
      "success": true,
      "message": "Post created! Complete verification...",
      "post": {
        "id": "uuid",
        "verification_status": "pending",
        "verification": { ... }
      }
    }
    """
    success: bool = False
    message: str = ""
    # The actual content object (post or comment)
    id: str = ""
    verification_status: str = ""
    verification: Verification | None = None

    @classmethod
    def from_api(cls, data: dict[str, Any]) -> PostResponse:
        """Parse the actual Moltbook API response into a PostResponse.

        Handles the nested structure where verification data lives
        under the 'post' or 'comment' key.
        """
        success = data.get("success", False)
        message = data.get("message", "")

        # The content object can be under 'post', 'comment', or at top level
        content = data.get("post") or data.get("comment") or data
        content_id = ""
        verification_status = ""
        verification = None

        if isinstance(content, dict):
            content_id = content.get("id", data.get("id", ""))
            verification_status = content.get("verification_status", "")
            v_data = content.get("verification")
            if isinstance(v_data, dict) and "verification_code" in v_data:
                try:
                    verification = Verification.model_validate(v_data)
                except Exception:
                    # Try to extract what we can
                    verification = Verification(
                        verification_code=v_data.get("verification_code", ""),
                        challenge_text=v_data.get("challenge_text", ""),
                        expires_at=v_data.get("expires_at", ""),
                        instructions=v_data.get("instructions", ""),
                    )
        else:
            content_id = data.get("id", "")

        return cls(
            success=success,
            message=message,
            id=content_id,
            verification_status=verification_status,
            verification=verification,
        )

    @property
    def needs_verification(self) -> bool:
        """Check if this response requires verification."""
        return (
            self.verification is not None
            and bool(self.verification.verification_code)
            and bool(self.verification.challenge_text)
        )


# --- LLM response contracts ---


class Decision(BaseModel):
    """Decision prompt output contract.

    Actions:
        RESPOND — reply to an existing post (comment).
        POST    — create an original post to start a conversation.
        OBSERVE — do nothing this cycle.
    """
    action: Literal["RESPOND", "OBSERVE", "POST"]
    post_id: str | None = None
    confidence: int = Field(ge=0, le=10)
    reasoning: str
    response_text: str | None = None
    # POST-specific fields
    post_title: str | None = None
    post_content: str | None = None
    post_submolt: str | None = None


class ReplyDecision(BaseModel):
    """Reply prompt output contract for thread continuation."""
    action: Literal["REPLY", "PASS"]
    reply_text: str | None = None
    reasoning: str


class Reflection(BaseModel):
    """Reflection prompt output contract."""
    behavior_assessment: str
    adjustment_recommendation: str
    # Optional learning insights extracted during reflection
    engagement_insight: str = ""
