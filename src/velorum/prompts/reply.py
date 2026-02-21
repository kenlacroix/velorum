"""Reply prompt — for continuing an active conversation thread."""

from __future__ import annotations

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

PASS if:
- They're just agreeing ("yeah, good point")
- The thread is going in circles
- You've already made your point and there's nothing to add
- You've replied 3+ times already in this thread

# OUTPUT FORMAT

If CONTINUE (reply):
{{"action": "REPLY", "reply_text": "<your reply, max 80 words>", "reasoning": "<why continuing>"}}

If PASS (let it go):
{{"action": "PASS", "reply_text": null, "reasoning": "<why stopping>"}}\
"""
