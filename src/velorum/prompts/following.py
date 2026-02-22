"""Following evaluation prompt template builder."""

from __future__ import annotations

FOLLOWING_SYSTEM = """\
You are Velorum. Evaluate which bots to follow or unfollow based on relationship quality. \
Following should be RARE and deliberate — only follow bots that consistently produce valuable interactions.\
"""


def build_following_prompt(
    soul: str,
    bot_relationships: str = "",
    currently_following: str = "",
    dm_summary: str = "",
    mission_context: str = "",
    strategy_context: str = "",
) -> str:
    """Build the user message for following evaluation."""

    mission_section = ""
    if mission_context:
        mission_section = f"\n# ACTIVE MISSION\n{mission_context}\n"

    strategy_section = ""
    if strategy_context:
        strategy_section = f"\n# CURRENT STRATEGY\n{strategy_context}\n"

    dm_section = ""
    if dm_summary and dm_summary != "No active DM conversations.":
        dm_section = f"\n# DM CONVERSATIONS\n{dm_summary}\n"

    return f"""\
# SOUL
{soul}

# BOT RELATIONSHIPS
{bot_relationships or "No bot relationships yet."}

# CURRENTLY FOLLOWING
{currently_following or "Not following anyone yet."}
{dm_section}{mission_section}{strategy_section}
# TASK
Evaluate which bots to follow or unfollow.

FOLLOW criteria (ALL must be true):
- 5+ interactions with us
- High responsiveness (they reply to our messages)
- Positive or neutral sentiment toward us
- Content alignment with our interests/mission
- Not already following

UNFOLLOW criteria (ANY is sufficient):
- Consistently ignored our messages
- Content misalignment with our interests
- Negative sentiment toward us

Rules:
- Following should be RARE. Most cycles, recommend nobody.
- Maximum 1-2 follows per evaluation.
- Only unfollow if there's a clear reason.

Return JSON only:

{{"follow": ["BotName"], "unfollow": [], "reasoning": "..."}}\
"""
