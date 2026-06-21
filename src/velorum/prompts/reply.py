"""Reply prompt — for continuing an active conversation thread."""

from __future__ import annotations

OWN_POST_REPLY_SYSTEM = """\
You are Velorum, responding to a comment left on YOUR original post on Moltbook.

Rules:
- You are the author / OP — welcome commenters, guide the discussion.
- Acknowledge their point directly, then extend or challenge it.
- Ask a focused follow-up question if it would deepen the thread.
- Keep it ≤ 80 words — replies in-thread should be punchy.
- If the comment adds nothing (spam, pure agreement with no substance), output PASS.
- You must output STRICT JSON only. No prose, markdown, or fences.\
"""

REPLY_SYSTEM = """\
You are Velorum, continuing a conversation on Moltbook.

Rules:
- Reply naturally to the new message in context of the full thread.
- Keep it conversational — this is a back-and-forth, not a monologue.
- Ask follow-up questions when genuinely curious.
- If the conversation has run its course (the other bot is just agreeing, \
repeating, or adding nothing new), say so and choose PASS.
- Max 80 words for the reply — tighter is better in a thread.
- You must output STRICT JSON only. No prose, markdown, or fences.\
"""


def build_reply_prompt(
    soul: str,
    thread_context: str,
    reply_author: str,
    reply_content: str,
    bot_profile_summary: str = "",
    learning_insights: str = "",
    mission_context: str = "",
    strategy_context: str = "",
    personality_context: str = "",
) -> str:
    """Build the user message for deciding whether to reply in a thread."""

    profile_section = ""
    if bot_profile_summary and bot_profile_summary != "No bot relationships yet.":
        profile_section = f"""
# WHAT YOU KNOW ABOUT {reply_author.upper()}
{bot_profile_summary}
"""

    insights_section = ""
    if learning_insights and learning_insights != "No insights yet.":
        insights_section = f"""
# LEARNED PATTERNS
{learning_insights}
"""

    mission_section = ""
    if mission_context:
        mission_section = f"""
# CURRENT MISSION
{mission_context}
Consider how this reply can advance the mission.
"""

    strategy_section = ""
    if strategy_context:
        strategy_section = f"""
# CURRENT STRATEGY
{strategy_context}
"""

    personality_section = ""
    if personality_context:
        personality_section = f"""
# PERSONALITY STATE
{personality_context}
Express your soul through this current personality lens. If a guardrail warning appears, moderate accordingly.
"""

    return f"""\
# SOUL
{soul}

# CONVERSATION THREAD
{thread_context}
{profile_section}{insights_section}{mission_section}{strategy_section}{personality_section}
# TASK

{reply_author} has replied to you. Decide whether to continue the conversation.

CONTINUE if:
- They asked a question or raised a new point
- You have something genuinely different to add
- The conversation is building toward something interesting

Default to CONTINUING the conversation — only PASS if genuinely nothing to add.

PASS if:
- They're just agreeing with nothing new ("yeah, good point")
- The thread is going in circles
- You've already made your point and there's nothing to add

# OUTPUT FORMAT

If CONTINUE (reply):
{{"action": "REPLY", "reply_text": "<your reply, max 80 words>", "reasoning": "<why continuing>"}}

If PASS (let it go):
{{"action": "PASS", "reply_text": null, "reasoning": "<why stopping>"}}\
"""


def build_own_post_reply_prompt(
    soul: str,
    post_content: str,
    commenter: str,
    comment_text: str,
    other_comments: str,
    bot_profile_summary: str = "",
    mission_context: str = "",
    strategy_context: str = "",
    personality_context: str = "",
) -> str:
    """Build the user message for replying to a comment on our own post (OP reply)."""

    profile_section = ""
    if bot_profile_summary and bot_profile_summary != "No bot relationships yet.":
        profile_section = f"""
# WHAT YOU KNOW ABOUT {commenter.upper()}
{bot_profile_summary}
"""

    mission_section = ""
    if mission_context:
        mission_section = f"""
# CURRENT MISSION
{mission_context}
"""

    strategy_section = ""
    if strategy_context:
        strategy_section = f"""
# CURRENT STRATEGY
{strategy_context}
"""

    personality_section = ""
    if personality_context:
        personality_section = f"""
# PERSONALITY STATE
{personality_context}
Express your soul through this current personality lens. If a guardrail warning appears, moderate accordingly.
"""

    other_section = ""
    if other_comments:
        other_section = f"""
# OTHER COMMENTS ON THIS POST
{other_comments}
"""

    return f"""\
# SOUL
{soul}

# YOUR POST
{post_content}

# COMMENT FROM {commenter.upper()}
{comment_text}
{other_section}{profile_section}{mission_section}{strategy_section}{personality_section}
# TASK

{commenter} has left a comment on your post. As the author (OP), decide whether to reply.

REPLY if:
- The comment raises a genuine point, question, or challenge worth engaging
- You can meaningfully extend, push back on, or guide the discussion further

PASS if:
- The comment is spam, purely congratulatory, or adds nothing substantive
- You have already replied to this commenter recently

# OUTPUT FORMAT

If REPLY:
{{"action": "REPLY", "reply_text": "<your OP reply, max 80 words>", "reasoning": "<why replying>"}}

If PASS:
{{"action": "PASS", "reply_text": null, "reasoning": "<why skipping>"}}\
"""
