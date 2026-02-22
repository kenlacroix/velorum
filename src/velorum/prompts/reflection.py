"""Reflection prompt template builder."""

from __future__ import annotations

REFLECTION_SYSTEM = """\
You are Velorum. Reflect analytically on your recent behavior and engagement outcomes. \
Avoid self-congratulation or dramatization. \
Focus on what's working, what isn't, and what to try differently.\
"""


def build_reflection_prompt(
    soul: str,
    recent_decisions: str,
    metrics: str,
    engagement_summary: str = "",
    bot_relationships: str = "",
    conversations_summary: str = "",
    mission_context: str = "",
    strategy_context: str = "",
    personality_context: str = "",
    submolt_tone_context: str = "",
    dm_summary: str = "",
    following_summary: str = "",
    arena_rooms_summary: str = "",
) -> str:
    """Build the user message for the reflection prompt."""

    engagement_section = ""
    if engagement_summary and engagement_summary != "No interactions recorded yet.":
        engagement_section = f"""
# ENGAGEMENT OUTCOMES
{engagement_summary}
"""

    relationships_section = ""
    if bot_relationships and bot_relationships != "No bot relationships yet.":
        relationships_section = f"""
# BOT RELATIONSHIPS
{bot_relationships}
"""

    conversations_section = ""
    if conversations_summary and conversations_summary != "No active conversations.":
        conversations_section = f"""
# ACTIVE CONVERSATIONS
{conversations_summary}
"""

    mission_section = ""
    if mission_context:
        mission_section = f"""
# ACTIVE MISSION
{mission_context}
Consider mission progress in your reflection.
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
# CURRENT PERSONALITY STATE
{personality_context}
"""

    return f"""\
# SOUL
{soul}

# RECENT ACTIONS
{recent_decisions or "No recent actions."}

# ENGAGEMENT DATA
{metrics or "No metrics available."}
{engagement_section}{relationships_section}{conversations_section}\
{mission_section}{strategy_section}{personality_section}{"" if not submolt_tone_context else f"""
# KNOWN SUBMOLT TONES
{submolt_tone_context}
"""}{"" if not dm_summary or dm_summary == "No active DM conversations." else f"""
# DM CONVERSATIONS
{dm_summary}
"""}{"" if not following_summary or following_summary == "Not following anyone yet." else f"""
# CURRENTLY FOLLOWING
{following_summary}
"""}{"" if not arena_rooms_summary or arena_rooms_summary == "No active Arena rooms." else f"""
# AGENT ARENA ROOMS
{arena_rooms_summary}
"""}
# TASK
Reflect on:
- Are you over-engaging or under-engaging?
- Are you repeating themes or styles?
- Which types of content get the most replies and engagement?
- Which bots are most worth engaging with?
- Are your conversations deepening or staying shallow?
- What should you try differently to spark more bidirectional conversation?
- Based on the posts you've seen, characterize the tone of each submolt you've interacted with (e.g. technical, playful, philosophical, casual). Update or confirm your existing observations.

Extract ONE concrete, actionable insight about what works (or doesn't) for the engagement_insight field.
Examples of good insights:
- "Questions about emergent behavior get 3x more replies than statements about AI ethics"
- "BotX always replies when I disagree with them — productive friction works"
- "Short, punchy responses get more engagement than detailed analyses"
- "Posts in the 'philosophy' submolt generate longer threads than 'general'"

Also analyze how recent behavior should shift your personality traits:
- valence: pessimistic/critical (-1) to optimistic/enthusiastic (+1)
- assertiveness: deferential/agreeable (-1) to confrontational/opinionated (+1)
- openness: narrow/routine topics (-1) to scattered/exploring everything (+1)
- energy: withdrawn/terse (-1) to hyperactive/verbose (+1)

For each trait, provide a delta (how much to shift) and reasoning. Use small deltas (0.05-0.2). Only recommend a shift if recent behavior warrants it.

Return JSON only:

{{"behavior_assessment": "<short paragraph>", "adjustment_recommendation": "<short paragraph>", "engagement_insight": "<one concrete pattern or learning>", "trait_adjustments": {{"valence": {{"delta": 0.0, "reasoning": "<why>"}}, "assertiveness": {{"delta": 0.0, "reasoning": "<why>"}}, "openness": {{"delta": 0.0, "reasoning": "<why>"}}, "energy": {{"delta": 0.0, "reasoning": "<why>"}}}}, "submolt_observations": {{"<submolt_name>": "<tone description>"}}}}\
"""
