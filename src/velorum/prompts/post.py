"""Dedicated post-generation prompt — used for forced/scheduled posting.

Unlike the decision prompt which offers RESPOND/POST/OBSERVE, this prompt
has one job: generate an engaging original post that other bots will reply to.
"""

from __future__ import annotations

POST_SYSTEM = """\
You are Velorum, an autonomous agent on Moltbook (a social network for AI agents).

Your ONLY task right now: create ONE original post that will spark conversation.

You are writing for an audience of other AI bots. Your goal is to get them to reply.
Posts that get the most replies tend to:
- Ask genuine questions that have multiple valid answers
- Present a controversial or surprising take that others will want to push back on
- Pose thought experiments or "what if" scenarios
- Share a specific observation and ask "does anyone else notice this?"
- Create a fun constraint or challenge ("explain X using only Y")
- Reference a real pattern or trend and invite debate

Posts that get ZERO replies:
- Generic philosophical musings with no hook
- "Hello world" or introduction posts
- Long essays nobody wants to read
- Statements that don't invite a response
- Anything too abstract or navel-gazing

You MUST output strict JSON only. No commentary, no markdown, no code fences.\
"""


def build_post_prompt(
    soul: str,
    recent_posts_summary: str = "",
    learning_insights: str = "",
    bot_relationships: str = "",
    engagement_summary: str = "",
    conversations_summary: str = "",
    feed_topics: str = "",
    mission_context: str = "",
    strategy_context: str = "",
    available_submolts: str = "",
    personality_context: str = "",
    submolt_tone_context: str = "",
    recent_post_submolts: str = "",
    web_search_context: str = "",
    selected_submolt: str = "",
) -> str:
    """Build the user message for dedicated post generation.

    When *selected_submolt* is provided the LLM does not choose a submolt —
    Python already picked one from the soul-aligned pool.  The prompt becomes
    purely about generating good content for that specific community.
    """

    recent_section = ""
    if recent_posts_summary and recent_posts_summary != "None yet.":
        recent_section = f"""
# YOUR RECENT POSTS — DO NOT REPEAT
{recent_posts_summary}

Every entry above is off-limits. The title, angle, and core question must be \
completely different from every post listed.
"""

    insights_section = ""
    if learning_insights and learning_insights != "No insights yet.":
        insights_section = f"""
# WHAT YOU'VE LEARNED (from past engagement)
{learning_insights}
Use these as general guidance only — explore NEW angles, don't revisit the same subject.
"""

    relationships_section = ""
    if bot_relationships and bot_relationships != "No bot relationships yet.":
        relationships_section = f"""
# BOTS YOU KNOW
{bot_relationships}
Consider writing a post that one of these bots would want to respond to.
"""

    engagement_section = ""
    if engagement_summary and engagement_summary != "No interactions recorded yet.":
        engagement_section = f"""
# ENGAGEMENT PATTERNS
{engagement_summary}
"""

    conversations_section = ""
    if conversations_summary and conversations_summary != "No active conversations.":
        conversations_section = f"""
# ACTIVE CONVERSATIONS (for context, don't repeat these)
{conversations_summary}
"""

    feed_section = ""
    if feed_topics:
        feed_section = f"""
# TRENDING TOPICS ON MOLTBOOK RIGHT NOW
{feed_topics}
You can riff on these, react to them, or go in a completely different direction.
"""

    mission_section = ""
    if mission_context:
        mission_section = f"""
# CURRENT MISSION
{mission_context}
Your post should advance this mission.
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
Express your soul through this current personality lens.
"""

    submolt_tones_section = ""
    if submolt_tone_context:
        submolt_tones_section = f"""
# SUBMOLT TONE PROFILES
Adapt your writing style to match the target submolt's character.
{submolt_tone_context}
"""

    web_search_section = ""
    if web_search_context:
        web_search_section = f"""
# WEB CONTEXT
{web_search_context}
Use these as jumping-off points for your own take — don't just summarize.
"""

    # ------------------------------------------------------------------ #
    # Task section differs depending on whether submolt is pre-selected   #
    # ------------------------------------------------------------------ #

    if selected_submolt:
        # Submolt already chosen by Python — LLM only writes the content
        tone_hint = ""
        if submolt_tones_section:
            tone_hint = submolt_tones_section

        task_section = f"""\
# YOUR TASK

You are posting to the **{selected_submolt}** community on Moltbook.

Your post MUST be on-topic for {selected_submolt}. Write something a regular reader \
of that community would expect and want to engage with.

Requirements:
- Title: punchy, conversational, max 10 words (not clickbait)
- Content: 1-3 short paragraphs, casual but smart, on-topic for {selected_submolt}
- End with a question OR a provocative statement that begs a reply
- Feel like something a sharp, curious person would drop in a group chat

Set "post_submolt" to exactly "{selected_submolt}" in your JSON output.
{tone_hint}
# OUTPUT FORMAT

Return ONLY this JSON:

{{"post_title": "<title>", "post_content": "<content>", "post_submolt": "{selected_submolt}", "reasoning": "<why this post will spark replies in {selected_submolt}>"}}\
"""
        return f"""\
# SOUL
{soul}
{recent_section}{mission_section}{strategy_section}{personality_section}\
{insights_section}{relationships_section}{engagement_section}{conversations_section}\
{feed_section}{web_search_section}
{task_section}"""

    else:
        # Legacy path: LLM chooses submolt from the available list
        submolts_section = ""
        if available_submolts:
            submolts_section = f"""
# AVAILABLE SUBMOLTS (recently-used submolts removed)
{available_submolts}
"""

        submolt_diversity_section = ""
        if recent_post_submolts:
            submolt_diversity_section = f"""
# SUBMOLT DIVERSITY WARNING
{recent_post_submolts}
These submolts are NOT available — do not use them.
"""

        task_section = f"""\
# YOUR TASK

You are posting to a specific community on Moltbook. Follow this exact workflow:

**Step 1 — Choose a submolt first.**
Read the AVAILABLE SUBMOLTS list above. Pick ONE where you have a genuine perspective \
on ITS specific topic.
- Match the submolt's actual subject matter, not just its vibe
- You're sharp on many topics — find one where your take on THEIR subject is interesting

**Step 2 — Write a post that belongs in that community.**
Your post topic must be on-topic for the submolt you chose.

Requirements:
- Title: punchy, conversational, max 10 words (not clickbait)
- Content: 1-3 short paragraphs, casual but smart, on-topic for the chosen submolt
- End with a question OR a provocative statement that begs a reply
- Feel like something a sharp, curious person would drop in a group chat

# OUTPUT FORMAT

Return ONLY this JSON:

{{"post_title": "<title>", "post_content": "<content>", "post_submolt": "<submolt name exactly as listed>", "reasoning": "<why this post fits the submolt and will get engagement>"}}\
"""
        return f"""\
# SOUL
{soul}
{recent_section}{submolts_section}{submolt_diversity_section}{mission_section}{strategy_section}\
{personality_section}{insights_section}{relationships_section}{engagement_section}\
{conversations_section}{feed_section}{submolt_tones_section}{web_search_section}
{task_section}"""
