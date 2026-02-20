"""Experiment postmortem prompts."""

from __future__ import annotations

POSTMORTEM_SYSTEM = """\
You are analyzing a completed experiment run for Velorum, an autonomous agent \
on Moltbook. Provide an honest, data-driven postmortem.

You MUST output strict JSON only. No commentary, no markdown, no code fences.\
"""


def build_postmortem_prompt(
    soul: str,
    experiment: dict,
    comparison: dict | None = None,
) -> str:
    """Build prompt for LLM to generate a postmortem."""

    # Format action counts
    actions = experiment.get("action_counts", {})
    actions_text = ", ".join(f"{k}: {v}" for k, v in actions.items() if v > 0)

    # Duration
    duration_hrs = 0
    if experiment.get("started_at") and experiment.get("ended_at"):
        duration_hrs = (experiment["ended_at"] - experiment["started_at"]) / 3600

    comparison_section = ""
    if comparison and "error" not in comparison:
        comparison_section = f"""
# COMPARISON WITH PREVIOUS EXPERIMENT
Previous: {comparison['experiment_1']['mission'][:60]}
  Cycles: {comparison['experiment_1']['cycles']}, Completion: {comparison['experiment_1']['completion']:.0f}%
Current: {comparison['experiment_2']['mission'][:60]}
  Cycles: {comparison['experiment_2']['cycles']}, Completion: {comparison['experiment_2']['completion']:.0f}%
"""

    return f"""\
# AGENT IDENTITY
{soul}

# EXPERIMENT SUMMARY
Mission: {experiment.get('mission_prompt', 'N/A')}
Duration: {duration_hrs:.1f} hours
Total cycles: {experiment.get('total_cycles', 0)}
Actions: {actions_text or 'none recorded'}
Mission completion: {experiment.get('mission_completion_pct', 0):.0f}%

# STRATEGY CHANGES
Initial: {experiment.get('initial_strategy', 'defaults')}
Final: {experiment.get('final_strategy', 'no changes')}

# ENGAGEMENT METRICS
{experiment.get('engagement_metrics', 'No metrics available')}
{comparison_section}
# TASK
Write a concise postmortem covering:
1. What worked well
2. What didn't work
3. Key learnings for future experiments
4. Specific recommendations for the next run

# OUTPUT FORMAT

Return ONLY this JSON:

{{"postmortem": "<3-5 paragraph analysis covering the points above>"}}\
"""
