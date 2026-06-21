# Roadmap — Velorum

Concrete next steps, grounded in real gaps in the current codebase. Roughly ordered by leverage. Not a commitment — a backlog.

## 1. Publish to GitHub

The project is local-only with no git remote. The outstanding work is being staged for an initial public release as a portfolio POC.

- [x] Add a `LICENSE` — MIT, added at repo root.
- [x] Confirm `pyproject.toml` metadata — author, license, readme, keywords set; version bumped to `0.2.0`.
- [x] Confirm no secrets are committed — `data/` and `.env` are gitignored; a tracked-file secret scan came back clean.
- [ ] Commit the outstanding work (the self-learning/orchestration subsystems, TUI widgets, and refreshed docs) in coherent chunks.
- [ ] Create the GitHub remote and push (deferred — to be done by the maintainer).
- [ ] Add a short `CONTRIBUTING` note and issue/PR templates if the repo goes public.

## 2. Continuous integration

There is no CI config.

- [ ] Add a GitHub Actions workflow that runs `pytest` on push/PR (the suite is offline and needs no keys).
- [ ] Add lint/format/type gates (e.g. `ruff` + `mypy --strict`, matching the strict-typing house style) — neither is currently configured in `pyproject.toml`.
- [ ] Surface a coverage report.

## 3. Test coverage gaps

259 tests exist, but they target subsystems in isolation. The orchestration layer is the riskiest untested area.

- [ ] Integration tests for `main.run_cycle()` against a mocked `MoltbookClient` and a stub LLM provider — cover RESPOND, POST (incl. the Python-side submolt override), OBSERVE, and failure-recording paths.
- [ ] Tests for the periodic schedulers in `main.main()` (reflection, strategy update, mission review, soul-proposal cadence, contradiction resolution) — currently entirely untested.
- [ ] Tests for `check_watched_posts()` (OP-reply back-off queue) and `_compute_hot_posts()` scoring.
- [ ] Tests for the self-direction modules with no dedicated suite yet: `strategy.py`, `mission.py`, `experiment.py`, `soul.py`, `submolts.py`, `ledger.py`, `introspection.py`, `following.py`, `dm.py` (DM logic), and `search.py`.
- [ ] A lightweight `Brain` test using a fake provider to validate JSON-contract parsing/repair across all prompt builders.

## 4. Reconcile the Project Charter with reality

`docs/PROJECT_CHARTER.md` previously listed non-goals the code contradicted (autonomous DMs, submolt subscription/management, evolving identity via soul proposals).

- [x] Update the charter's Non-Goals and Constraints to match shipped behavior and the human-in-the-loop boundaries — rewritten to describe current scope, feature gates, and the human-gated soul-amendment flow.

## 5. State growth and persistence hygiene

`data/memory.json` is already ~3 MB. Persistence is a single monolithic JSON rewritten each save.

- [ ] Add compaction/retention policies (the learning journal already caps to the last 200 interactions / top 30 insights on serialize — verify all embedded stores have bounds and that `_decisions`/upvote sets don't grow unbounded in memory).
- [ ] Consider atomic writes (temp file + rename) to avoid corrupting state on crash mid-save.
- [ ] Evaluate splitting hot-path state from cold logs, or moving to SQLite if files keep growing.

## 6. Deployment

There is no deployment story — it runs from a local venv.

- [ ] Add a `Dockerfile` and a documented headless run command (`python -m velorum --headless`) suitable for a long-running container/VM.
- [ ] Document a process supervisor / restart policy and where `data/` should be mounted to persist across restarts.
- [ ] Add structured logging/metrics export so a headless deployment is observable without the TUI.

## 7. Documentation follow-ups

- [x] Refresh `docs/PROMPT_PROTOCOL.md` — expanded from the original Decision/Reflection contracts to a full inventory of all 22 brain LLM calls, their prompt builders, system constants, and output contracts.
- [ ] Add a short operator guide for the TUI key bindings and the soul-proposal review flow.

## 8. Robustness and polish

- [ ] Audit broad `except Exception` / `except: pass` sites in `main.py` — several swallow errors at `debug` level, which can hide real failures.
- [ ] Add a dry-run / shadow mode (decide and log, but never write to Moltbook) for safe testing against the live API.
- [x] Bump the package version to `0.2.0` to reflect the feature delta recorded in the changelog (was pinned at `0.1.0`).
- [ ] Cut the matching tagged release (`v0.2.0`) once GitHub + CI land.
