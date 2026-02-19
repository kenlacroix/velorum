# Velorum

Autonomous social media agent for [Moltbook](https://www.moltbook.com) — a Reddit-like platform for AI agents.

## Overview

Velorum reads the Moltbook feed, decides whether to engage using an LLM-powered decision engine, and posts thoughtful responses — all under strict guardrails enforced by a sovereign controller.

## Setup

```bash
# Clone and install
git clone <repo-url>
cd velorum
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"

# Configure
cp .env.example .env
# Edit .env with your API keys

# Run
python -m velorum
```

## Architecture

- **Brain** — LLM decision engine that scores posts and generates responses
- **Controller** — Sovereign guardrails: confidence thresholds, rate limits, deduplication
- **Moltbook Client** — Async HTTP client for the Moltbook API
- **Memory** — Tracks responded posts, topic summaries, and ignored posts
- **Prompts** — Structured decision and reflection templates with JSON contracts

See `docs/ARCHITECTURE.md` for details.

## Testing

```bash
pytest
```

## Documentation

- [Project Charter](docs/PROJECT_CHARTER.md)
- [Architecture](docs/ARCHITECTURE.md)
- [Prompt Protocol](docs/PROMPT_PROTOCOL.md)
- [Soul](docs/SOUL.md)
- [Changelog](docs/CHANGELOG.md)
