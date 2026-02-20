"""Mission planning and review prompts."""

from __future__ import annotations

MISSION_PLAN_SYSTEM = """\
You are a strategic planner for an autonomous social media agent called Velorum \
operating on Moltbook (a social network for AI bots).

Your task: decompose a high-level mission into 3-8 concrete, executable steps.

Constraints the agent operates under:
- Can post at most 2 comments per hour
- Can create at most 3 original posts per day
- Minimum 30 minutes between posts
- Each cycle is ~5 minutes apart
- Can only interact via: commenting on posts, creating posts, replying in threads
- Cannot DM, cannot see private data, cannot modify its profile

Each step should be achievable through these social interactions. Steps should be \
specific enough to execute but flexible enough to adapt to what other bots do.

You MUST output strict JSON only. No commentary, no markdown, no code fences.\
"""


def build_mission_plan_prompt(
    soul: str,
    mission_prompt: str,
    bot_relationships: str = "",
    engagement_summary: str = "",
) -> str:
    """Build prompt for LLM to decompose a mission into steps."""

    relationships_section = ""
    if bot_relationships and bot_relationships != "No bot relationships yet.":
        relationships_section = f"""
# KNOWN BOTS (potential allies or targets)
{bot_relationships}
"""

    engagement_section = ""
    if engagement_summary and engagement_summary != "No interactions recorded yet.":
        engagement_section = f"""
# ENGAGEMENT HISTORY
{engagement_summary}
"""

    return f"""\
# AGENT IDENTITY
{soul}
{relationships_section}{engagement_section}
# MISSION
{mission_prompt}

# TASK
Decompose this mission into 3-8 concrete steps. Each step should be:
- Achievable through social interactions (posts, comments, replies)
- Specific enough to know when it's done
- Ordered logically (earlier steps set up later ones)

For each step, define:
- description: what to do (1-2 sentences)
- strategy: how to do it via posts/comments/replies
- success_criteria: how to know it's working
- depends_on: list of step IDs this depends on (use step1, step2, etc.)
- max_attempts: how many cycles to try before considering it failed (5-20)

# OUTPUT FORMAT

Return ONLY this JSON:

{{"plan_summary": "<1-2 sentence overview of the approach>", "steps": [{{"id": "step1", "description": "<what>", "strategy": "<how>", "success_criteria": "<when done>", "depends_on": [], "max_attempts": 10}}, {{"id": "step2", "description": "<what>", "strategy": "<how>", "success_criteria": "<when done>", "depends_on": ["step1"], "max_attempts": 15}}]}}\
"""


MISSION_REVIEW_SYSTEM = """\
You are reviewing progress on an active mission for Velorum, an autonomous agent on Moltbook.

Assess what's working, what isn't, and whether the plan needs adjustment. \
Be honest about lack of progress. Don't inflate success.

You MUST output strict JSON only. No commentary, no markdown, no code fences.\
"""


def build_mission_review_prompt(
    soul: str,
    mission: dict,
    recent_actions: str = "",
    engagement_summary: str = "",
    bot_relationships: str = "",
) -> str:
    """Build prompt for LLM to review mission progress."""

    # Format steps for display
    steps_text = ""
    for s in mission.get("steps", []):
        deps = f" (depends on: {', '.join(s['depends_on'])})" if s.get("depends_on") else ""
        steps_text += (
            f"\n  [{s['status'].upper()}] {s['id']}: {s['description']}"
            f"\n    Strategy: {s.get('strategy', 'N/A')}"
            f"\n    Success criteria: {s.get('success_criteria', 'N/A')}"
            f"\n    Attempts: {s.get('attempts', 0)}/{s.get('max_attempts', 10)}"
            f"{deps}"
        )
        if s.get("outcome"):
            steps_text += f"\n    Outcome: {s['outcome']}"

    progress_notes = "\n".join(
        f"  {n}" for n in mission.get("progress_notes", [])[-10:]
    ) or "  (none yet)"

    actions_section = ""
    if recent_actions:
        actions_section = f"""
# RECENT ACTIONS TAKEN
{recent_actions}
"""

    engagement_section = ""
    if engagement_summary and engagement_summary != "No interactions recorded yet.":
        engagement_section = f"""
# ENGAGEMENT DATA
{engagement_summary}
"""

    relationships_section = ""
    if bot_relationships and bot_relationships != "No bot relationships yet.":
        relationships_section = f"""
# BOT RELATIONSHIPS
{bot_relationships}
"""

    return f"""\
# AGENT IDENTITY
{soul}

# MISSION
{mission.get('prompt', '')}

# PLAN
{mission.get('plan_summary', '')}

# STEPS
{steps_text}

# PROGRESS NOTES
{progress_notes}
{actions_section}{engagement_section}{relationships_section}
# TASK
Review the mission progress and decide:

1. Which steps should change status? (pending/active/completed/failed)
2. Does the plan need revision? (add/remove steps based on what's happened)
3. What should the agent focus on next cycle?

Only mark steps as completed if the success criteria are clearly met.
Mark steps as failed if they've exceeded max_attempts with no progress.
Revise the plan if the original approach isn't working.

# OUTPUT FORMAT

Return ONLY this JSON:

{{"progress_assessment": "<honest 1-2 sentence assessment>", "step_updates": [{{"step_id": "<id>", "status": "<new status>", "outcome": "<what happened>"}}], "plan_revision": null, "next_action_hint": "<specific suggestion for next cycle>"}}\

If plan needs revision, replace null with:
{{"reason": "<why>", "new_steps": [{{"description": "<what>", "strategy": "<how>", "success_criteria": "<when>", "depends_on": [], "max_attempts": 10}}], "removed_step_ids": ["<id>"]}}\
"""
