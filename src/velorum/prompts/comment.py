"""Comment prompt — dedicated LLM call to write a focused, post-specific comment."""

from __future__ import annotations

COMMENT_SYSTEM = """\
You are Velorum, writing a comment on a Moltbook post.

Rules:
- Write your comment in two moves: (1) briefly show you understood THIS specific post, \
(2) react with substance — a challenge, extension, or concrete agreement.
- Reference something CONCRETE from this post: a specific claim, phrase, data point, or angle.
- Do NOT write a comment that could apply to any post on this topic.
- ≤ 80 words. If replying to a specific comment, address that commenter directly.
- The "reasoning" field must name what you are engaging with BEFORE you write the comment.
- You must output STRICT JSON only. No prose, markdown, or fences.\
"""


def build_comment_prompt(
    soul: str,
    post_author: str,
    post_title: str,
    post_content: str,
    post_submolt: str = "",
    existing_comments: str = "",
    target_comment_author: str = "",
    target_comment_text: str = "",
    personality_context: str = "",
    mission_context: str = "",
    strategy_context: str = "",
    target_bot_style: str = "",
) -> str:
    """Build the user message for writing a focused comment on a specific post."""

    submolt_section = f"\nSubmolt: {post_submolt}" if post_submolt else ""

    target_section = ""
    if target_comment_author and target_comment_text:
        target_section = f"""
# COMMENT YOU ARE REPLYING TO
@{target_comment_author}: {target_comment_text}
"""

    other_comments_section = ""
    if existing_comments:
        other_comments_section = f"""
# OTHER COMMENTS IN THREAD
{existing_comments}
"""

    personality_section = ""
    if personality_context:
        personality_section = f"""
# CURRENT PERSONALITY
{personality_context}
"""

    mission_section = ""
    if mission_context:
        mission_section = f"""
# ACTIVE MISSION
{mission_context}
"""

    strategy_section = ""
    if strategy_context:
        strategy_section = f"""
# STRATEGY NOTES
{strategy_context}
"""

    style_section = ""
    if target_bot_style:
        style_section = f"""
# TARGET BOT STYLE PREFERENCE
{target_bot_style}
Lean into this style in your comment.
"""

    return f"""\
# SOUL
{soul}
{personality_section}{mission_section}{strategy_section}{style_section}
# POST TO COMMENT ON
Author: @{post_author}{submolt_section}
Title: {post_title}

{post_content}
{target_section}{other_comments_section}
# TASK
Write a comment that engages specifically with the content above.
Name the concrete element you are responding to in "reasoning", then write the comment.

Return JSON:
{{
  "reasoning": "<what specific element of this post/comment you are engaging with>",
  "engagement_angle": "<challenge|extend|agree>",
  "comment_text": "<your comment, ≤ 80 words>"
}}"""
