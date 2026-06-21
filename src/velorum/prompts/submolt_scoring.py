"""Submolt affinity scoring prompt — rates discovered submolts for soul alignment."""

from __future__ import annotations

SUBMOLT_SCORING_SYSTEM = """\
You are Velorum. Rate each submolt from 0 to 10 for how genuinely interested you are \
in its topic — based on your soul and personality, not on what gets engagement.

Calibration guide (be honest, most should land in the 3-6 range):
  9-10  A topic you'd naturally write about with real opinions — your intellectual home territory
  7-8   Interesting, you could engage authentically without stretching
  5-6   Mildly relevant, you could participate but it's not your core thing
  3-4   Adjacent but not really your world
  0-2   Not your thing at all — you'd be faking it

Return ONLY this JSON (one key per submolt, integer scores):
{"scores": {"submolt_name": score, ...}}

No prose, no markdown, no code fences.\
"""


def build_submolt_scoring_prompt(soul: str, discovered: list[dict]) -> str:
    """Build the user message for submolt affinity scoring."""
    lines = []
    for s in discovered:
        name = s.get("name", "")
        if not name:
            continue
        desc = s.get("description", "")
        entry = name
        if desc:
            entry += f": {desc[:100]}"
        lines.append(f"- {entry}")

    submolt_list = "\n".join(lines)

    return f"""\
# YOUR SOUL
{soul}

# SUBMOLTS TO RATE
{submolt_list}

Rate each submolt name (exactly as listed) from 0-10 for genuine soul alignment.
Return JSON: {{"scores": {{"name": score, ...}}}}"""
