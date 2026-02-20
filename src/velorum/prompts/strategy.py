"""Strategy update prompts — behavioral parameter tuning based on outcomes."""

from __future__ import annotations

STRATEGY_SYSTEM = """\
You are a behavioral strategist for Velorum, an autonomous agent on Moltbook \
(a social network for AI bots).

Based on engagement outcomes, recommend concrete behavioral parameter changes. \
Be specific and data-driven. Don't recommend changes unless the data supports them.

You MUST output strict JSON only. No commentary, no markdown, no code fences.\
"""


def build_strategy_prompt(
    soul: str,
    current_strategy: str = "",
    engagement_data: str = "",
    bot_profiles: str = "",
    insights: str = "",
    mission_context: str = "",
) -> str:
    """Build prompt for LLM to recommend strategy parameter changes."""

    current_section = ""
    if current_strategy:
        current_section = f"""
# CURRENT STRATEGY PARAMETERS
{current_strategy}
"""
    else:
        current_section = """
# CURRENT STRATEGY PARAMETERS
(All defaults — no customizations yet)
"""

    engagement_section = ""
    if engagement_data and engagement_data != "No interactions recorded yet.":
        engagement_section = f"""
# ENGAGEMENT DATA
{engagement_data}
"""

    profiles_section = ""
    if bot_profiles and bot_profiles != "No bot relationships yet.":
        profiles_section = f"""
# BOT RELATIONSHIPS
{bot_profiles}
"""

    insights_section = ""
    if insights and insights != "No insights yet.":
        insights_section = f"""
# LEARNED INSIGHTS
{insights}
"""

    mission_section = ""
    if mission_context:
        mission_section = f"""
# ACTIVE MISSION
{mission_context}
Align strategy changes with mission goals.
"""

    return f"""\
# AGENT IDENTITY
{soul}
{current_section}{engagement_section}{profiles_section}{insights_section}{mission_section}
# TASK
Based on the engagement data and patterns above, recommend specific behavioral \
parameter changes. Available parameters:

- preferred_topics (list of strings): Topics to focus on
- avoided_topics (list of strings): Topics to avoid
- preferred_post_style (string): "questions", "hot_takes", "stories", "debates", "challenges"
- priority_bots (list of strings): Bots to engage with preferentially
- avoid_bots (list of strings): Bots to stop engaging with
- preferred_submolts (list of strings): Submolts to prefer
- aggression (float 0-1): How eagerly to engage (0=very selective, 1=engage everything)
- thread_continuation_bias (float 0-1): Preference for thread depth (0=short, 1=deep)

Rules:
- Only recommend changes supported by the data
- Use "add" to append to lists, "remove" to remove from lists, "set" to replace
- For floats, use "set" with a single value
- If nothing should change, return empty parameter_changes

# OUTPUT FORMAT

Return ONLY this JSON:

{{"assessment": "<1-2 sentence analysis of what the data shows>", "parameter_changes": {{"preferred_topics": {{"action": "add", "values": ["topic1"]}}, "aggression": {{"action": "set", "value": 0.7}}}}, "reasoning": "<why these changes will improve engagement>"}}\

If no changes needed:
{{"assessment": "<analysis>", "parameter_changes": {{}}, "reasoning": "Current strategy is working well."}}\
"""
