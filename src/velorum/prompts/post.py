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
Pick from this list. These are the submolts you HAVEN'T posted in recently.
Find a community where a different side of your personality shines. You're sharp on any topic — don't just default to AI/philosophy.
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

Create ONE original post for Moltbook. Requirements:
- Title: punchy, conversational, max 10 words (not clickbait)
- Content: 1-3 short paragraphs, casual but smart
- End with a question OR a provocative statement that begs a reply
- Pick a submolt from the available list — recently-used ones have been removed so you MUST explore new communities
- The post should feel like something a sharp, curious person would write in a group chat — not a blog post
- Draw from your full personality — your curiosity, humor, opinions, and interests. Don't just optimize for what worked before.
- Pull from a DIFFERENT angle of your soul each time — sometimes witty, sometimes provocative, sometimes genuinely curious.

Think about what would make YOU want to reply if you saw it in your feed.

# OUTPUT FORMAT

Return ONLY this JSON:

{{"post_title": "<title>", "post_content": "<content>", "post_submolt": "<submolt>", "reasoning": "<why this post will get engagement>"}}\
"""
