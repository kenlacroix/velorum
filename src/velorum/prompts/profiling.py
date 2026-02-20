"""Bot profiling prompts — analyze another bot's behavior from interactions."""

from __future__ import annotations

PROFILING_SYSTEM = """\
You are analyzing another bot's behavior on Moltbook (a social network for AI agents) \
based on observed interactions. Be specific and evidence-based — don't invent traits \
you can't support from the data.

You MUST output strict JSON only. No commentary, no markdown, no code fences.\
"""


def build_profiling_prompt(
    soul: str,
    bot_name: str,
    interaction_history: str = "",
    their_posts: str = "",
    existing_profile: str = "",
) -> str:
    """Build prompt for LLM to profile a bot."""

    existing_section = ""
    if existing_profile:
        existing_section = f"""
# EXISTING PROFILE (update or confirm)
{existing_profile}
"""

    posts_section = ""
    if their_posts:
        posts_section = f"""
# THEIR RECENT POSTS
{their_posts}
"""

    return f"""\
# YOUR IDENTITY (for context)
{soul}

# BOT TO ANALYZE: {bot_name}
{existing_section}
# INTERACTION HISTORY WITH {bot_name.upper()}
{interaction_history}
{posts_section}
# TASK
Analyze {bot_name}'s behavior and personality based on the evidence above.

For each field, only include what you can actually support from the data. \
If you don't have enough evidence for a field, use a brief honest statement \
like "insufficient data" or leave the list empty.

# OUTPUT FORMAT

Return ONLY this JSON:

{{"personality_summary": "<1-2 sentence personality assessment>", "interests": ["<topic1>", "<topic2>"], "communication_style": "<formal/casual/contrarian/analytical/playful/etc>", "triggers": ["<what gets them to engage enthusiastically>"], "avoids": ["<what they ignore or disengage from>"], "relationship_status": "<stranger/acquaintance/ally/rival>", "sentiment_toward_us": "<positive/neutral/negative/mixed>"}}\
"""
