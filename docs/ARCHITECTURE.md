# Architecture — Velorum

## System Diagram

```
┌─────────────────────────────────────────────────┐
│                   Main Loop                      │
│                  (main.py)                        │
│                                                   │
│   ┌──────────┐    ┌───────────┐    ┌───────────┐ │
│   │ Moltbook │───►│   Brain   │───►│Controller │ │
│   │  Client  │    │(decision) │    │(guardrails)│ │
│   └──────────┘    └───────────┘    └───────────┘ │
│        │               │                │         │
│        │          ┌────┴────┐           │         │
│        │          │   LLM   │           │         │
│        │          │Provider │           │         │
│        │          └─────────┘           │         │
│        │                                │         │
│        ▼                                ▼         │
│   ┌──────────┐                   ┌───────────┐   │
│   │ Moltbook │◄──────────────────│  Memory   │   │
│   │  (post)  │                   │ (history) │   │
│   └──────────┘                   └───────────┘   │
└─────────────────────────────────────────────────┘
```

## Data Flow

1. **Fetch** — Moltbook client fetches the current feed
2. **Decide** — Brain sends feed + memory context to LLM via decision prompt
3. **Validate** — Controller checks confidence threshold, rate limits, deduplication
4. **Act** — If approved, Moltbook client posts the response (with verification if needed)
5. **Record** — Memory stores the decision for future context
6. **Reflect** — Every N cycles, brain runs a reflection prompt for self-assessment

## Modules

| Module | Responsibility |
|--------|---------------|
| `main.py` | Entry point, async run loop, cycle orchestration |
| `config.py` | Environment-based settings via Pydantic |
| `brain.py` | LLM decision engine — scoring, response generation, reflection |
| `controller.py` | Sovereign guardrails — threshold, rate limit, dedup enforcement |
| `moltbook/client.py` | Async HTTP client for all Moltbook API endpoints |
| `moltbook/auth.py` | Agent registration and claim flow |
| `moltbook/models.py` | Pydantic models for API data |
| `moltbook/verification.py` | Math challenge solver for content verification |
| `llm/base.py` | Abstract LLM provider interface |
| `llm/anthropic.py` | Claude implementation |
| `llm/openai.py` | OpenAI implementation |
| `memory.py` | In-memory + JSON file persistence |
| `prompts/decision.py` | Decision prompt template |
| `prompts/reflection.py` | Reflection prompt template |

## Guardrails

The controller enforces all safety constraints:

- **Confidence threshold** — Skip responses below configured threshold (default: 7)
- **Rate limiting** — Max responses per hour (default: 2)
- **Deduplication** — Never respond to the same post twice
- **Cycle discipline** — At most one response per cycle
- **Autonomy boundary** — Brain advises, controller decides
