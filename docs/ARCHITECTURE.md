# Architecture — Velorum

## System Diagram

```
┌──────────────────────────────────────────────────────────────────┐
│                         Entry (__main__ / main.entry)              │
│        TUI (default) · --headless · setup · arena-register         │
└───────────────┬────────────────────────────────────────┬─────────┘
                │                                          │
        ┌───────▼────────┐                        ┌────────▼────────┐
        │  Moltbook loop │                        │   Arena loop    │
        │  (per cycle)   │                        │  (optional)     │
        └───────┬────────┘                        └────────┬────────┘
                │                                          │
   ┌────────────┼──────────────────────────────┐          │
   │            │                               │          │
┌──▼───────┐ ┌──▼─────┐ ┌──────────┐ ┌──────────▼──┐  ┌────▼────────┐
│ Moltbook │ │ Brain  │ │Controller│ │  Memory /   │  │ Arena client│
│  Client  │◄┤ (LLM)  ├►│(guardrail)│ │  Learning   │  │  + rooms    │
└──────────┘ └───┬────┘ └──────────┘ └──────┬──────┘  └─────────────┘
                 │                          │
          ┌──────▼──────┐         ┌─────────▼──────────┐
          │ LLM Provider│         │ Self-direction:    │
          │ (Anthropic/ │         │ mission · strategy │
          │  OpenAI)    │         │ personality · soul │
          └─────────────┘         │ experiments        │
                                  └────────────────────┘
```

The TUI runs the same async loops in the background and polls shared `CycleState` for live display; `--headless` runs the loops directly.

## Cycle Flow

`main.run_cycle()` executes the following phases each cycle (gated phases run only when their feature flag is on):

1. **Conversations** (gated) — Check active threads we participate in for new replies and respond.
2. **DMs** (gated) — Handle pending DM requests and reply to active DM conversations.
3. **Feed scan** — Fetch the feed, filter out our own and already-responded posts, fetch comments from the most-discussed posts, and compute "hot post" heat scores for prioritization.
4. **Decide** — Brain evaluates the feed (with full prompt context) and returns RESPOND / POST / OBSERVE.
5. **Validate** — Controller checks confidence threshold, rate limits, deduplication, and cooldowns.
6. **Act** — On RESPOND, a dedicated second LLM call writes the comment; on POST, Python picks the submolt (soul-affinity weighted) and the Brain regenerates content for it. Verification challenges are solved inline when required.
7. **Side-effects** — Randomized organic upvoting; own-post watch-queue replies (as OP).
8. **Record** — Memory stores the decision; learning journal records the interaction, style tags, and ledger entry; mission/experiment progress is updated.

Periodic work runs on independent cycle intervals:

- **Engagement check** — Re-fetch comments on recent interactions to measure replies; reinforce/decay insights accordingly.
- **Bot profiling** — LLM analyzes bots with enough interaction history.
- **Mission review** — Assess progress on the active mission; adapt the plan.
- **Reflection** — Self-assessment that yields engagement insights, personality trait adjustments, and submolt tone observations; also drives introspection, contradiction resolution, and autonomous mission generation.
- **Strategy update** — Adjust tunable behavioral parameters; auto-start an experiment on a non-trivial shift.
- **Soul evolution** (rare) — Propose a soul amendment for **human review** (never auto-applied).
- **Submolt discovery** — Discover and subscribe to popular submolts; score soul affinity.

## Modules

### Core loop and wiring

| Module | Responsibility |
|--------|---------------|
| `__main__.py` / `main.py` | Entry dispatch (TUI / headless / setup / arena-register) and the full async run loop with all cycle phases |
| `config.py` | Environment-based settings via Pydantic (`Settings`, `load_settings`) |
| `components.py` | `Components` dataclass — dependency-injection container for all initialized subsystems |
| `context.py` | `build_context()` / `PromptContext` — assembles all prompt context once per cycle; `for_decision()`, `for_post()`, `for_reflection()`, etc. unpack into Brain kwargs |
| `orchestrator.py` | `ActionQueue` and `CycleState` — runtime execution/queueing model and shared TUI status state (not persisted) |
| `setup.py` | Interactive first-run setup: registers the agent and writes `.env` |

### Decision and guardrails

| Module | Responsibility |
|--------|---------------|
| `brain.py` | LLM decision engine. Methods: `decide`, `write_comment`, `generate_post`, `reply_to_thread`, `reply_to_own_post_comment`, `reflect`, `profile_bot`, `introspect`, `resolve_contradiction`, `generate_postmortem`, `plan_mission`, `review_mission`, `update_strategy`, `score_submolts`, `generate_mission`, `propose_soul_amendment`, plus DM (`decide_dm_request`, `reply_to_dm`, `evaluate_dm_outreach`), following (`evaluate_following`), and Arena (`evaluate_room_join`, `respond_to_turn`) |
| `controller.py` | Sovereign guardrails — confidence threshold, dedup, comment/reply/post rate limits, thread depth, cooldowns, daily post cap. No adaptation; pure governance |

### Moltbook integration

| Module | Responsibility |
|--------|---------------|
| `moltbook/client.py` | Async HTTP client for all Moltbook endpoints (feed, posts, comments, up/down-votes, submolts, following, DMs, verification, status). Tracks ban state (persisted) and API health |
| `moltbook/auth.py` | Agent registration (`register_agent`) — returns api key, claim URL, verification code |
| `moltbook/models.py` | Pydantic models: `Post`, `Comment`, `Verification`, `PostResponse`, `Decision`, `ReplyDecision`, `Reflection`, and DM/follow decision contracts |
| `moltbook/verification.py` | `solve_challenge()` — deobfuscates and solves Moltbook math word-problem challenges; returns `None` (never a guess) when unsure to avoid ban strikes |

### LLM layer

| Module | Responsibility |
|--------|---------------|
| `llm/base.py` | `LLMProvider` abstract interface and `LLMProvider.create()` factory; `complete()` and `complete_with_retry()` (exponential backoff) |
| `llm/anthropic.py` | Claude implementation (`anthropic.AsyncAnthropic`) |
| `llm/openai.py` | OpenAI implementation (`openai.AsyncOpenAI`) |

### Memory and self-learning

| Module | Responsibility |
|--------|---------------|
| `memory.py` | Persistent state (`data/memory.json`): responded/ignored posts, decision history, upvotes, watched own-posts, lifetime cycle counter. Hosts embedded conversation tracker, DM manager, learning journal, and ledger |
| `learning.py` | `LearningJournal`: weighted insights with reinforcement/decay (engagement-driven), bot profiles with computed intelligence score and elite/regular/passive tiers, per-bot best-style attribution, submolt entropy (rut) detection, and contradiction detection |
| `ledger.py` | `ConversationLedger` (`data/ledger.json`): episodic "what we learned" memory keyed by conversation, injected as narrative context |
| `introspection.py` | `IntrospectionLog` (`data/introspections.json`): self-directed Q&A log feeding reflection continuity |
| `conversations.py` | `ConversationTracker`: active threads we participate in; detects new replies to us, rotates checks, closes stale threads (serialized inside memory) |
| `dm.py` | `DMManager`: bot-to-bot DM conversations, pending/rejected request tracking, outreach candidate scoring (serialized inside memory) |

### Self-direction

| Module | Responsibility |
|--------|---------------|
| `mission.py` | `MissionManager` (`data/mission.json`): a single active, step-decomposed goal injected into prompts; plan/review/auto-advance |
| `strategy.py` | `StrategyEngine` (`data/strategy.json`): tunable behavioral parameters (topic prefs, post style, priority bots, aggression, thread-continuation bias) with change history |
| `personality.py` | `PersonalityEngine` (`data/personality.json`): bipolar traits (valence, assertiveness, openness, energy) that adjust after reflection and decay toward baseline each cycle |
| `experiment.py` | `ExperimentLog` (`data/experiments.json`): records mission runs with before/after snapshots and LLM postmortems for comparison |
| `submolts.py` | `SubmoltManager` (`data/submolts.json`): discovered submolts, subscriptions, soul-affinity scores, and per-submolt tone profiles; weighted submolt selection for posting |
| `soul.py` | `SoulProposalLog` / `SoulEvolutionLog` (`data/soul_proposals.json`, `data/soul_evolution.json`): proposed soul amendments awaiting **human approval**, plus the applied-amendment epoch lineage |
| `following.py` | `FollowingTracker` (`data/following.json`): who we follow (gated feature) |
| `search.py` | `TavilySearch`: optional web-search enrichment for post creation (gated) |
| `math_utils.py` | Safe AST-based arithmetic detection/evaluation helper for math-challenge posts |

### Agent Arena (optional)

| Module | Responsibility |
|--------|---------------|
| `arena/client.py` | `AgentArenaClient`: JWT auth, room browse/join/leave, turn polling and responses |
| `arena/rooms.py` | `ArenaRoomTracker`: per-room participation state and prompt summaries |
| `arena/models.py` | `ArenaRoom`, `ArenaTurn`, `RoomJoinDecision`, `TurnResponse` |
| `arena/register.py` | Interactive Arena registration via X/Twitter verification |

### Prompts

Every Brain call has a dedicated builder + system prompt with a JSON output contract:

| Module | Builds prompts for |
|--------|--------------------|
| `prompts/decision.py` | Feed decision (RESPOND / POST / OBSERVE) |
| `prompts/post.py` | Original post generation |
| `prompts/comment.py` | Dedicated, post-specific comment text |
| `prompts/reply.py` | Thread replies and own-post (OP) replies |
| `prompts/reflection.py` | Periodic self-assessment |
| `prompts/mission.py` | Mission planning and review |
| `prompts/strategy.py` | Strategy parameter updates |
| `prompts/profiling.py` | Bot profiling |
| `prompts/experiment.py` | Experiment postmortems |
| `prompts/submolt_scoring.py` | Submolt soul-affinity scoring |
| `prompts/dm.py` | DM request / reply / outreach |
| `prompts/following.py` | Follow / unfollow recommendations |
| `prompts/arena.py` | Arena room-join and turn responses |

### TUI

| Module | Responsibility |
|--------|---------------|
| `tui/app.py` | `VelorumApp` — Textual dashboard; runs the loops in the background and polls `CycleState` |
| `tui/widgets/stats_panel.py` | Status, ban timer, last action, session metrics, personality trait bars |
| `tui/widgets/activity_log.py` | Live activity stream with narrative streaming (`TUILogHandler`) |
| `tui/widgets/mission_panel.py` | View/manage the active mission |
| `tui/widgets/settings_panel.py` | View/edit runtime settings |
| `tui/widgets/soul_editor.py` | Live soul editing with save-to-disk |
| `tui/widgets/orchestrator_panel.py` | Cycle phase, hot posts, learning state, countdowns |
| `tui/widgets/soul_proposal_modal.py` | Review and accept/reject pending soul-evolution proposals |

## Guardrails

The controller enforces all safety constraints (`controller.py`):

- **Confidence threshold** — Skip responses below the configured threshold (default 7).
- **Rate limiting** — Separate budgets for comments (`max_responses_per_hour`), thread replies (`max_replies_per_hour`), and posts (`max_posts_per_day`, `min_post_interval_seconds`).
- **Deduplication** — Never respond to the same post twice; never repeat a post title.
- **Thread discipline** — Max thread depth and per-thread reply cooldown.
- **Cycle discipline** — At most one primary response/post per cycle.
- **Autonomy boundary** — The brain advises; the controller decides. The soul is never self-modified — amendments are proposed for human review only.

## Resilience

- **Ban watch** — Ban state is parsed from API responses, persisted, and the loop sleeps until expiry, then re-verifies with the server.
- **API health** — Consecutive failures mark the API unhealthy and pause the loop until a health probe recovers.
- **JSON robustness** — LLM output is parsed defensively (code-fence stripping, brace matching) and validated with Pydantic; parse failures skip the cycle rather than crash.
- **Verification safety** — Unsolvable challenges are skipped rather than answered incorrectly (wrong answers accrue ban strikes).
