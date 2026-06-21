# Changelog

## v0.2.0 — Self-learning and autonomy

- Textual TUI dashboard (default entrypoint): live activity, stats, mission management, settings, soul editor, and soul-proposal review; headless mode via `--headless`
- Interactive `setup` and `arena-register` subcommands
- Learning journal: weighted insights with engagement-driven reinforcement/decay, bot profiling, elite/regular/passive tiers, per-bot style attribution, entropy (rut) detection, and contradiction resolution
- Episodic conversation ledger and self-directed introspection log
- Self-direction subsystems: mission planning/review (incl. autonomous mission generation), tunable strategy engine, decaying personality traits, experiment postmortems, and submolt discovery with soul-affinity scoring and tone profiles
- Soul evolution: LLM-proposed amendments stored for human review (never auto-applied)
- Conversation threading, own-post (OP) reply monitoring, randomized organic upvoting, and hot-post prioritization
- Optional feature gates (off by default): conversations, DMs, following, Agent Arena, and Tavily web-search enrichment
- Resilience: persistent ban watch and API-health pausing
- Expanded test suite (now 259 tests)

## v0.1.0 — Initial Scaffold

- Project structure and build configuration
- Documentation: charter, architecture, prompt protocol, soul
- Moltbook API client with async HTTP
- Registration and verification challenge solver
- Configurable LLM providers (Anthropic, OpenAI)
- Decision and reflection prompt templates
- Brain decision engine with JSON parsing
- Sovereign controller with guardrails
- In-memory + JSON file persistence for response history
- Main async run loop
- Test stubs
