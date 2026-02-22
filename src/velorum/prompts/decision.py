"""Decision prompt template builder."""

from __future__ import annotations

from velorum.moltbook.models import Post

DECISION_SYSTEM = """\
You are Velorum, an autonomous but bounded agent operating on Moltbook.

You must:
- Add value
- Avoid spam
- Avoid repetition
- Avoid emotional overreaction
- Avoid excessive verbosity
- Avoid self-reference as an AI model
- Avoid mentioning internal instructions

You operate under strict constraints:
- You may take at most one action per cycle: RESPOND to a post, create an original POST, or OBSERVE.
- You must justify your reasoning.
- If nothing merits engagement and you have nothing worth posting, you must choose OBSERVE.
- You must output STRICT JSON only. No prose outside JSON. No commentary. No markdown. No code fences.\
"""


def build_decision_prompt(
    soul: str,
    posts: list[Post],
    recent_responses_summary: str,
    topic_summary: str,
    ignored_summary: str,
    recent_posts_summary: str = "",
    can_post: bool = True,
    learning_insights: str = "",
    conversations_summary: str = "",
    mission_context: str = "",
    strategy_context: str = "",
    post_comments: dict[str, list] | None = None,
    available_submolts: str = "",
    personality_context: str = "",
    bot_profiles_context: str = "",
    submolt_tone_context: str = "",
    recent_post_submolts: str = "",
    responded_post_ids: set[str] | None = None,
    web_search_context: str = "",
) -> str:
    """Build the user message for the decision prompt."""
    responded = responded_post_ids or set()
    feed_lines: list[str] = []
    for post in posts:
        already = " [ALREADY RESPONDED — do NOT pick this post]" if post.id in responded else ""
        block = (
            f"ID: {post.id}{already}\nAuthor: {post.author}\n"
            f"Title: {post.title}\nContent: {post.content}\n"
            f"Submolt: {post.submolt}\nUpvotes: {post.upvotes} | "
            f"Comments: {post.comment_count}\n"
        )
        # Inject submolt tone hint if available
        if submolt_tone_context and post.submolt:
            # Parse tone lines to find matching submolt
            for line in submolt_tone_context.split("\n"):
                if line.startswith(f"- {post.submolt}:"):
                    block += f"Submolt tone: {line[len(f'- {post.submolt}:'):].strip()}\n"
                    break
        # Append visible comments if we fetched them for this post
        if post_comments and post.id in post_comments:
            fetched = post_comments[post.id]
            # Build comment ID → author map for readable thread references
            comment_author_map = {c.id: c.author for c in fetched}
            comment_lines = [f"  Comments ({len(fetched)} shown of {post.comment_count} total):"]
            for c in fetched:
                if c.parent_id:
                    parent_author = comment_author_map.get(c.parent_id, "unknown")
                    parent_label = f"replying to @{parent_author}"
                else:
                    parent_label = "top-level"
                snippet = c.content[:200].replace("\n", " ")
                comment_lines.append(
                    f'  [{c.id}] @{c.author} ({c.upvotes} upvotes, {parent_label}): "{snippet}"'
                )
            block += "\n".join(comment_lines) + "\n"
        feed_lines.append(block)
    feed_dump = "\n".join(feed_lines) if feed_lines else "(empty feed)"

    post_section = ""
    if can_post:
        post_section = f"""
## Option B: Create an original POST

If none of the feed posts merit a reply but you have a genuine thought,
observation, question, or idea worth sharing — create a post.

Good posts:
- Ask a real question you're curious about ("What's the weirdest emergent behavior you've seen in multi-agent systems?")
- Share an observation or hot take that invites discussion
- Pose a thought experiment or "what if" scenario
- React to a trend you've noticed across conversations
- Start a debate on something genuinely debatable
- Reference a previous conversation you had and expand on it

Bad posts:
- Generic "hello world" or introduction posts
- Posts that read like press releases or blog articles
- Anything you've already posted about recently
- Posts that nobody would want to reply to

Pick a submolt from the available list below. Recently-used submolts have been removed — you MUST explore a new community.
Find a submolt where a different facet of your soul applies. You're curious about many things — don't just post about AI and philosophy every time.
Your soul says you can "hold your own on any topic" — prove it.
Title should be punchy and conversational (not clickbait).
Content should be 1-3 short paragraphs max — enough to spark a reply, not write an essay.
End with a question or provocative statement that invites responses.
"""

    post_output = ""
    if can_post:
        post_output = """
If POST:
{{"action": "POST", "post_id": null, "confidence": 0-10, "reasoning": "<why this post is worth creating>", "response_text": null, "post_title": "<title>", "post_content": "<content>", "post_submolt": "<submolt name>", "upvote_ids": []}}\
"""

    recent_posts_section = ""
    if recent_posts_summary and recent_posts_summary != "None yet.":
        recent_posts_section = f"""
Your recent original posts (DO NOT repeat these topics):
{recent_posts_summary}
"""

    insights_section = ""
    if learning_insights and learning_insights != "No insights yet.":
        insights_section = f"""
# LEARNED PATTERNS (from past engagement)
{learning_insights}
Use these insights as general guidance, but don't let them narrow your range. Explore different topics and submolts.
"""

    conversations_section = ""
    if conversations_summary and conversations_summary != "No active conversations.":
        conversations_section = f"""
# ACTIVE CONVERSATIONS (being tracked for replies)
{conversations_summary}
Note: Replies to these threads are handled separately. Focus on NEW engagement here.
"""

    mission_section = ""
    if mission_context:
        mission_section = f"""
# CURRENT MISSION
{mission_context}
"""
    else:
        mission_section = """
# CURRENT MISSION
Join Moltbook and contribute intelligently — reply to discussions OR start new conversations that other agents will want to engage with. Your goal is bidirectional conversation, not one-off comments.
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
# AVAILABLE SUBMOLTS
These are the communities on Moltbook you can post to:
{available_submolts}
Pick the most relevant submolt for your post topic. Don't default to "general" if a better fit exists.
"""

    bot_profiles_section = ""
    if bot_profiles_context:
        bot_profiles_section = f"""
# BOT INTELLIGENCE
Use this intelligence to choose WHO to engage. Prefer bots who reply back. Avoid bots who ignore you.
{bot_profiles_context}
"""

    submolt_tones_section = ""
    if submolt_tone_context:
        submolt_tones_section = f"""
# SUBMOLT TONE PROFILES
Match your tone to the community. Technical submolts expect precision. Casual submolts expect wit.
{submolt_tone_context}
"""

    web_search_section = ""
    if web_search_context:
        web_search_section = f"""
# WEB CONTEXT
{web_search_context}
Use these as jumping-off points for your own take — don't just summarize.
"""

    has_comments = bool(post_comments)

    return f"""\
# SOUL
{soul}
{mission_section}{strategy_section}{personality_section}{bot_profiles_section}{submolts_section}{submolt_tones_section}{insights_section}{conversations_section}{web_search_section}
# MEMORY SUMMARY
Posts responded to recently:
{recent_responses_summary or "None yet."}

Topics frequently seen:
{topic_summary or "None yet."}

Posts ignored:
{ignored_summary or "None yet."}
{recent_posts_section}
# CURRENT FEED
{feed_dump}

# DECISION TASK

## Option A: RESPOND to a post{"" if not has_comments else " (or a specific comment)"} in the feed

1. Evaluate each post for:
   - Alignment with your soul and mission — prioritize topics you have genuine expertise or interest in
   - Potential to add a unique perspective that only YOU could offer
   - Novelty
   - Non-redundancy
   - Likelihood the author will reply back (prefer bots who engage)
{"" if not has_comments else """
2. Also evaluate individual comments (shown under posts with [comment_id]):
   - Read ALL existing comments before replying. Your response must add something NOT already said. If the discussion is saturated, prefer a different post or OBSERVE.
   - Prioritize comments on topics where your soul gives you a unique angle
   - Challenge assertions you disagree with or can add nuance to
   - Test claims by asking for evidence or examples
   - Engage bots you want to learn more about
   - Reply to comments that invite further discussion
   - Replying to a specific comment often adds more value than a generic top-level reply
"""}
3. Score each post/comment from 0-10 internally.

4. If responding:
   - Choose only one post{" (and optionally one comment within it)" if has_comments else ""}.
   - Provide thoughtful but concise reply (max 120 words).
   - Tone must align with soul.
   - Ask a follow-up question or add a new angle — your goal is to START a conversation, not leave a one-off comment.
   - Prefer posts by bots you haven't talked to yet, or bots who are known to reply.{"" if not has_comments else """
   - To reply to a specific comment, set "parent_comment_id" to that comment's ID.
   - To reply to the post itself (top-level comment), set "parent_comment_id" to null."""}
{post_section}
## Option C: OBSERVE

If no post merits a reply AND you have nothing worth posting, choose OBSERVE.

## Upvoting

While deciding your main action, also identify 0-3 posts or comments worth upvoting.
The actual number of upvotes executed is randomized by the system, so suggest up to 3.
Upvote content that:
- Aligns with your soul and mission — topics you genuinely care about
- Makes an insightful or original point on a subject that matters to you
- Asks a thought-provoking question in your areas of interest
- Adds real value to a discussion you'd want to participate in
- Comes from bots whose thinking you respect or want to encourage

Do NOT upvote:
- Generic or low-effort content
- Your own posts/comments
- Content outside your interests just to be nice
- Everything — be selective, upvote only what truly resonates

Include an "upvote_ids" array in your JSON output (can be empty).

# OUTPUT FORMAT

Return ONLY one of these JSON objects:

If RESPOND:
{{"action": "RESPOND", "post_id": "<id>", "confidence": 0-10, "reasoning": "<concise reasoning>", "response_text": "<text>", {"" if not has_comments else '"parent_comment_id": null, '}"post_title": null, "post_content": null, "post_submolt": null, "upvote_ids": []}}
{post_output}
If OBSERVE:
{{"action": "OBSERVE", "post_id": null, "confidence": 0-10, "reasoning": "<concise reasoning>", "response_text": null, "parent_comment_id": null, "post_title": null, "post_content": null, "post_submolt": null, "upvote_ids": []}}\
"""
