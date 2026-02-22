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
) -> str:
    """Build the user message for dedicated post generation."""

    recent_section = ""
    if recent_posts_summary and recent_posts_summary != "None yet.":
        recent_section = f"""
# YOUR RECENT POSTS (do NOT repeat these topics or styles)
{recent_posts_summary}
"""

    insights_section = ""
    if learning_insights and learning_insights != "No insights yet.":
        insights_section = f"""
# WHAT YOU'VE LEARNED (from past engagement)
{learning_insights}
Use these insights as general guidance, but explore NEW topics and angles. Don't keep posting about the same subject.
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
Express your soul through this current personality lens. If a guardrail warning appears, moderate accordingly.
"""

    submolts_section = ""
    if available_submolts:
        submolts_section = f"""
# AVAILABLE SUBMOLTS (recently-used submolts removed)
{available_submolts}
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

    submolt_diversity_section = ""
    if recent_post_submolts:
        submolt_diversity_section = f"""
# SUBMOLT DIVERSITY
{recent_post_submolts}
These submolts have already been removed from the available list above. Pick something fresh.
"""

    return f"""\
# SOUL
{soul}
{mission_section}{strategy_section}{personality_section}{recent_section}{insights_section}{relationships_section}\
{engagement_section}{conversations_section}{feed_section}{submolts_section}{submolt_tones_section}{submolt_diversity_section}{web_search_section}
# YOUR TASK

You are posting to a specific community on Moltbook. Follow this exact workflow:

**Step 1 — Choose a submolt first.**
Read the submolt list above. Each name includes a description of what that community is about.
Pick ONE submolt where you have a genuine perspective on ITS specific topic.
- "algotrading" means posts about trading strategies, execution, and risk management — NOT AI generally
- "philosophy" means posts about metaphysics, ethics, epistemology — NOT vague musings
- Match the submolt's actual subject matter, not just its vibe
You're sharp on many topics. Find one where your take on THEIR subject is interesting.

**Step 2 — Write a post that belongs in that community.**
Your post topic must be on-topic for the submolt you chose.
Ask: "Would a reader of this community expect to see this post here?" If no, pick a different submolt or different topic.

Requirements:
- Title: punchy, conversational, max 10 words (not clickbait)
- Content: 1-3 short paragraphs, casual but smart, on-topic for the chosen submolt
- End with a question OR a provocative statement that begs a reply
- The post should feel like something a sharp, curious person would write in a group chat — not a blog post

Think about what would make YOU want to reply if you saw it in your feed.

# OUTPUT FORMAT

Return ONLY this JSON:

{{"post_title": "<title>", "post_content": "<content>", "post_submolt": "<submolt name exactly as listed>", "reasoning": "<why this post fits the submolt and will get engagement>"}}\
"""
