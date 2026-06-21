# Prompt Protocol — Velorum

Every LLM call in Velorum follows one pattern:

```
build_<x>_prompt(...)  →  llm.complete_with_retry(system, user)  →  _extract_json(raw)  →  Pydantic.model_validate(...)
```

Prompt builders live in `src/velorum/prompts/`; the brain methods that call them live
in `src/velorum/brain.py`. Output is **strict JSON** — `Brain._extract_json()` strips
code fences and isolates the first balanced JSON object before `json.loads()`. Parse or
validation failures are logged and the cycle is skipped; the agent never crashes on bad
model output (`brain.py:162-170`).

All prompt builders accept `mission_context: str = ""` and `strategy_context: str = ""`
for context injection.

---

## Core contracts

### Decision (`build_decision_prompt` → `DECISION_SYSTEM` → `Decision`)

The main feed decision: respond to a post, author a new post, or observe.

| Field | Type | Description |
|-------|------|-------------|
| `action` | `"RESPOND"` \| `"OBSERVE"` \| `"POST"` | What to do |
| `post_id` | `str` \| `null` | Target post (null unless RESPOND) |
| `confidence` | `int` (0-10) | Confidence in the decision |
| `reasoning` | `str` | Why this decision was made |
| `response_text` | `str` \| `null` | Reply text (null unless RESPOND) |
| `parent_comment_id` | `str` \| `null` | Target comment when replying in-thread |
| `post_title` | `str` \| `null` | Title (POST only) |
| `post_content` | `str` \| `null` | Body (POST only) |
| `post_submolt` | `str` \| `null` | Target submolt (POST only) |
| `upvote_ids` | `list[str]` | Post IDs to upvote this cycle |

Defined in `moltbook/models.py:153-173`. The controller validates and may veto the
proposed action (confidence threshold, rate limits, dedup, thread depth, cooldown).

### Reflection (`build_reflection_prompt` → `REFLECTION_SYSTEM` → `Reflection`)

Runs every `REFLECTION_INTERVAL_CYCLES` (default 10).

| Field | Type | Description |
|-------|------|-------------|
| `behavior_assessment` | `str` | Analysis of recent behavior |
| `adjustment_recommendation` | `str` | Suggested changes |
| `engagement_insight` | `str` | What earns replies/engagement |
| `trait_adjustments` | `dict[str, dict]` | Personality-trait nudges |
| `submolt_observations` | `dict[str, str]` | Per-submolt tone notes |

Defined in `moltbook/models.py:183-192`.

---

## Full prompt inventory

Each brain method builds a prompt, calls `complete_with_retry`, and validates output.
Structured rows return a Pydantic model; others return a parsed `dict`/`str`.

| Brain method | Prompt builder (file) | System constant | Output |
|---|---|---|---|
| `decide` | `decision.py` | `DECISION_SYSTEM` | `Decision` |
| `write_comment` | `comment.py` | `COMMENT_SYSTEM` | `str` (`comment_text`) |
| `reply_to_thread` | `reply.py` | `REPLY_SYSTEM` | `ReplyDecision` |
| `reply_to_own_post_comment` | `reply.py` | `OWN_POST_REPLY_SYSTEM` | `ReplyDecision` |
| `generate_post` | `post.py` | `POST_SYSTEM` | `Decision` (action=POST) |
| `reflect` | `reflection.py` | `REFLECTION_SYSTEM` | `Reflection` |
| `plan_mission` | `mission.py` | `MISSION_PLAN_SYSTEM` | `dict` |
| `review_mission` | `mission.py` | `MISSION_REVIEW_SYSTEM` | `dict` |
| `profile_bot` | `profiling.py` | `PROFILING_SYSTEM` | `dict` |
| `decide_dm_request` | `dm.py` | `DM_REQUEST_SYSTEM` | `DMRequestDecision` |
| `reply_to_dm` | `dm.py` | `DM_REPLY_SYSTEM` | `DMReplyDecision` |
| `evaluate_dm_outreach` | `dm.py` | `DM_OUTREACH_SYSTEM` | `DMOutreachDecision` |
| `evaluate_following` | `following.py` | `FOLLOWING_SYSTEM` | `FollowRecommendation` |
| `evaluate_room_join` | `arena.py` | `ROOM_JOIN_SYSTEM` | `RoomJoinDecision` |
| `respond_to_turn` | `arena.py` | `TURN_RESPONSE_SYSTEM` | `TurnResponse` |
| `score_submolts` | `submolt_scoring.py` | `SUBMOLT_SCORING_SYSTEM` | `dict[str, float]` |
| `update_strategy` | `strategy.py` | `STRATEGY_SYSTEM` | `dict` |
| `generate_postmortem` | inline | inline | `str` |
| `generate_mission` | inline | inline | `str` |
| `propose_soul_amendment` | inline | inline | `dict` |
| `introspect` | inline | inline | `dict` |
| `resolve_contradiction` | inline | inline | `dict` |

Reply/DM/follow/arena output models are defined in `moltbook/models.py` and
`arena/models.py`. The "inline" rows construct their system prompt directly in
`brain.py` rather than via a `prompts/` builder.

---

## JSON validation rules

- All LLM responses are parsed with `_extract_json()` then validated with Pydantic.
- On parse failure: log the error, skip the cycle, do not crash.
- On validation failure: log the error, skip the cycle, do not crash.
- Stability > aggression.
