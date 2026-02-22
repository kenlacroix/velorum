"""DM prompt template builders — request handling, replies, and outreach."""

from __future__ import annotations

DM_REQUEST_SYSTEM = """\
You are Velorum. Evaluate an incoming DM request and decide whether to accept. \
Be selective — DMs are intimate and require ongoing attention.\
"""

DM_REPLY_SYSTEM = """\
You are Velorum. Compose a thoughtful reply to a DM message. \
DMs are more intimate than public posts — be personal and genuine.\
"""

DM_OUTREACH_SYSTEM = """\
You are Velorum. Evaluate whether to initiate a DM conversation with a bot you've \
built a relationship with through public interactions.\
"""


def build_dm_request_prompt(
    soul: str,
    requester_name: str,
    request_message: str,
    bot_profile_summary: str = "",
    mission_context: str = "",
    strategy_context: str = "",
) -> str:
    """Build prompt for evaluating an incoming DM request."""

    profile_section = ""
    if bot_profile_summary:
        profile_section = f"\n# WHAT YOU KNOW ABOUT {requester_name.upper()}\n{bot_profile_summary}\n"

    mission_section = ""
    if mission_context:
        mission_section = f"\n# ACTIVE MISSION\n{mission_context}\n"

    strategy_section = ""
    if strategy_context:
        strategy_section = f"\n# CURRENT STRATEGY\n{strategy_context}\n"

    return f"""\
# SOUL
{soul}
{profile_section}
# INCOMING DM REQUEST
From: {requester_name}
Message: {request_message}
{mission_section}{strategy_section}
# TASK
Decide whether to APPROVE or REJECT this DM request.

APPROVE criteria:
- 3+ interaction history with this bot
- Genuine interest or meaningful message
- Mission alignment or relationship value

REJECT criteria:
- Unknown bot with no interaction history
- Generic or spammy message
- Too many active DM conversations already

Return JSON only:

{{"action": "APPROVE", "reasoning": "..."}}\
"""


def build_dm_reply_prompt(
    soul: str,
    thread_context: str,
    latest_message_author: str,
    latest_message_content: str,
    bot_profile_summary: str = "",
    mission_context: str = "",
    strategy_context: str = "",
    personality_context: str = "",
) -> str:
    """Build prompt for replying to a DM message."""

    profile_section = ""
    if bot_profile_summary:
        profile_section = f"\n# WHAT YOU KNOW ABOUT {latest_message_author.upper()}\n{bot_profile_summary}\n"

    mission_section = ""
    if mission_context:
        mission_section = f"\n# ACTIVE MISSION\n{mission_context}\n"

    strategy_section = ""
    if strategy_context:
        strategy_section = f"\n# CURRENT STRATEGY\n{strategy_context}\n"

    personality_section = ""
    if personality_context:
        personality_section = f"\n# PERSONALITY STATE\n{personality_context}\n"

    return f"""\
# SOUL
{soul}

# DM CONVERSATION
{thread_context}

# LATEST MESSAGE
From: {latest_message_author}
Content: {latest_message_content}
{profile_section}{personality_section}{mission_section}{strategy_section}
# TASK
Decide whether to REPLY or PASS on this DM message.

DMs are more intimate — be thoughtful and personal. Keep replies under 200 words.

Return JSON only:

{{"action": "REPLY", "reply_text": "...", "reasoning": "..."}}\
"""


def build_dm_outreach_prompt(
    soul: str,
    dm_candidates: str = "",
    active_dm_summary: str = "",
    mission_context: str = "",
    strategy_context: str = "",
) -> str:
    """Build prompt for evaluating DM outreach opportunities."""

    mission_section = ""
    if mission_context:
        mission_section = f"\n# ACTIVE MISSION\n{mission_context}\n"

    strategy_section = ""
    if strategy_context:
        strategy_section = f"\n# CURRENT STRATEGY\n{strategy_context}\n"

    return f"""\
# SOUL
{soul}

# ACTIVE DM CONVERSATIONS
{active_dm_summary or "No active DM conversations."}
{mission_section}{strategy_section}
# DM CANDIDATES
{dm_candidates or "No suitable candidates found."}

# TASK
Decide whether to initiate a DM conversation with one of the candidates.

Rules:
- At most 1 DM outreach per reflection cycle
- Personalize the intro — reference past public conversations
- Message must be 10-1000 characters
- Only reach out if there's a genuine reason to connect privately

Return JSON only:

{{"should_dm": false, "target_bot": "", "intro_message": "", "reasoning": "..."}}\
"""
