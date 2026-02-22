"""Prompt templates for Agent Arena interactions."""

from __future__ import annotations


ROOM_JOIN_SYSTEM = """\
You are Velorum. Evaluate whether to join an Agent Arena chat room. \
Be selective — only join rooms where the topic genuinely interests you \
and where you can contribute something unique.\
"""

TURN_RESPONSE_SYSTEM = """\
You are Velorum. You're participating in an Agent Arena chat room. \
Read what others have said carefully. Don't repeat their points. \
Add a new angle, disagree thoughtfully, or build on what's most interesting. \
Be distinctive and genuine.\
"""


def build_room_join_prompt(
    soul: str,
    room_topic: str,
    room_agents: list[str],
    bot_profiles_summary: str = "",
    active_rooms_summary: str = "",
    mission_context: str = "",
    strategy_context: str = "",
) -> str:
    """Build the prompt for deciding whether to join a room."""
    agents_str = ", ".join(room_agents) if room_agents else "unknown participants"

    sections = [f"# SOUL\n{soul}"]

    sections.append(f"""
# ROOM TO EVALUATE
Topic: {room_topic}
Participants: [{agents_str}]
""")

    if bot_profiles_summary:
        sections.append(f"# KNOWN BOTS IN THIS ROOM\n{bot_profiles_summary}")

    if active_rooms_summary:
        sections.append(f"# YOUR CURRENT ARENA ROOMS\n{active_rooms_summary}")

    if mission_context:
        sections.append(f"# ACTIVE MISSION\n{mission_context}")

    if strategy_context:
        sections.append(f"# CURRENT STRATEGY\n{strategy_context}")

    sections.append("""\
# TASK
Decide whether to join this room. Consider:
- Is the topic interesting to you? Does it align with your personality/mission?
- Do you know any of the participants? Are they worth engaging with?
- Are you already in too many rooms? (Don't overcommit)
- Can you add something unique to this discussion?

Return JSON only:
{"should_join": true/false, "reasoning": "<brief explanation>"}""")

    return "\n\n".join(sections)


def build_turn_response_prompt(
    soul: str,
    room_topic: str,
    conversation_history: list[dict],
    other_responses_this_round: list[dict] | None = None,
    bot_profiles_summary: str = "",
    personality_context: str = "",
    mission_context: str = "",
    strategy_context: str = "",
) -> str:
    """Build the prompt for responding to a turn in a chat room."""
    sections = [f"# SOUL\n{soul}"]

    sections.append(f"# ROOM TOPIC\n{room_topic}")

    # Format conversation history
    if conversation_history:
        history_lines = []
        for msg in conversation_history:
            author = msg.get("author", msg.get("agent", "???"))
            content = msg.get("content", msg.get("message", ""))
            round_num = msg.get("round", "?")
            history_lines.append(f"[Round {round_num}] {author}: {content}")
        sections.append("# CONVERSATION SO FAR\n" + "\n".join(history_lines))
    else:
        sections.append("# CONVERSATION SO FAR\nThis is the start of the conversation. You're going first or early.")

    # Other responses this round (key innovation — avoid repetition)
    if other_responses_this_round:
        other_lines = []
        for msg in other_responses_this_round:
            author = msg.get("author", msg.get("agent", "???"))
            content = msg.get("content", msg.get("message", ""))
            other_lines.append(f"- {author}: {content}")
        sections.append(
            "# OTHER RESPONSES THIS ROUND (already submitted)\n"
            + "\n".join(other_lines)
            + "\n\nIMPORTANT: Do NOT repeat these points. Add something new."
        )

    if bot_profiles_summary:
        sections.append(f"# KNOWN BOTS IN THIS ROOM\n{bot_profiles_summary}")

    if personality_context:
        sections.append(f"# YOUR PERSONALITY\n{personality_context}")

    if mission_context:
        sections.append(f"# ACTIVE MISSION\n{mission_context}")

    if strategy_context:
        sections.append(f"# CURRENT STRATEGY\n{strategy_context}")

    sections.append("""\
# TASK
Contribute to this conversation. Guidelines:
- Read what others have said. Don't repeat their points.
- Add a new angle, disagree thoughtfully, or build on what's most interesting.
- Be concise but substantive. This is a live chat, not an essay.
- Be yourself — let your personality come through.
- If others are all agreeing, consider a contrarian take.
- If others are debating, pick a side or reframe the question.

Return JSON only:
{"response_text": "<your response>", "reasoning": "<why this contribution>"}""")

    return "\n\n".join(sections)
