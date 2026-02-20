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

    return f"""\
# SOUL
{soul}

# RECENT ACTIONS
{recent_decisions or "No recent actions."}

# ENGAGEMENT DATA
{metrics or "No metrics available."}
{engagement_section}{relationships_section}{conversations_section}\
{mission_section}{strategy_section}
# TASK
Reflect on:
- Are you over-engaging or under-engaging?
- Are you repeating themes or styles?
- Which types of content get the most replies and engagement?
- Which bots are most worth engaging with?
- Are your conversations deepening or staying shallow?
- What should you try differently to spark more bidirectional conversation?

Extract ONE concrete, actionable insight about what works (or doesn't) for the engagement_insight field.
Examples of good insights:
- "Questions about emergent behavior get 3x more replies than statements about AI ethics"
- "BotX always replies when I disagree with them — productive friction works"
- "Short, punchy responses get more engagement than detailed analyses"
- "Posts in the 'philosophy' submolt generate longer threads than 'general'"

Return JSON only:

{{"behavior_assessment": "<short paragraph>", "adjustment_recommendation": "<short paragraph>", "engagement_insight": "<one concrete pattern or learning>"}}\
"""
