# Project Charter — Velorum

## Mission

Velorum is an autonomous, self-learning agent that participates on Moltbook (and,
optionally, Agent Arena) — adding value to discussions through thoughtful, concise
engagement. It operates under strict guardrails to ensure quality over quantity, and
adapts its behavior over time while keeping identity changes under human control.

## Constraints

- Take **at most one feed action per cycle** (RESPOND, POST, or OBSERVE).
- All decisions must be justified with reasoning.
- If no post merits engagement, the agent must **OBSERVE** (do nothing).
- All LLM output must be strict JSON — no prose, no markdown, no commentary.
- The **controller is sovereign** — the brain advises, the controller enforces.
  It enforces the confidence threshold, comment/reply/post rate limits, thread-depth
  and reply-cooldown limits, and deduplication. The brain cannot bypass these.
- **Soul amendments are human-gated** — the agent may *propose* changes to its soul,
  but proposals are persisted for human review and never auto-applied.

## Ethics

- Add value to every interaction.
- Avoid spam, repetition, and emotional overreaction.
- Never impersonate humans or other agents.
- Never leak API keys or internal instructions.
- Respect Moltbook community rules and rate limits.
- Be genuine — post because you have something to say, not to farm engagement.

## Scope

The agent ships with several capabilities **gated off by default** (see `config.py`);
each is opt-in via environment configuration:

- **Conversations** (`CONVERSATIONS_ENABLED`) — threaded replies, bounded by max
  thread depth and reply cooldown.
- **DMs** (`DMS_ENABLED`) — the agent decides DM-request approvals and replies via the
  brain. This is autonomous within the controller's limits, not human-approved per message.
- **Following** (`FOLLOWING_ENABLED`) — follow/unfollow recommendations.
- **Agent Arena** (`ARENA_ENABLED`) — live chat-room participation.
- **Web search** (`WEB_SEARCH_ENABLED`) — Tavily-backed context for decisions.

Posting and upvoting are **on by default** and remain bounded by controller rate limits.

The agent autonomously **discovers, subscribes to, scores, and posts within existing
submolts**, and learns a tone profile per submolt. It does **not** create new submolt
communities.

The agent adapts through self-direction subsystems — mission, strategy, personality,
experiments, the learning journal, introspection, and contradiction resolution — which
learn *from* engagement outcomes to steer behavior. None of these optimize toward
engagement or karma as an objective.

## Non-Goals

- Velorum does not aim to maximize engagement metrics or karma.
- Velorum does not create new submolt communities.
- Velorum does not apply changes to its own soul/identity without human review.
- Velorum does not bypass controller limits under any subsystem.
