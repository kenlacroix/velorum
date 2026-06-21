"""Capture authentic Velorum TUI screenshots as SVG.

Renders the real dashboard against the project's real persisted state
(data/*.json), but with a mocked Moltbook client so no live network calls or
posts happen during capture. The cycle loop is paused; panels are seeded from
real memory so the shots look like a live session.

Usage:
    python3 scripts/capture_screenshots.py [output_dir]

Default output: docs/assets/screenshots/
"""

from __future__ import annotations

import asyncio
import sys
from datetime import datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

from rich.text import Text
from textual.widgets import TabbedContent

from velorum.config import Settings
from velorum.main import init_components
from velorum.tui.app import VelorumApp
from velorum.tui.widgets.activity_log import ActivityLog
from velorum.tui.widgets.orchestrator_panel import OrchestratorPanel
from velorum.tui.widgets.stats_panel import StatsPanel

SIZE = (132, 40)


def _mock_client():
    """A Moltbook client that performs no network I/O."""
    client = AsyncMock()
    client.is_banned = False
    client.ban_reason = ""
    client.ban_remaining_seconds = MagicMock(return_value=0)
    client.check_status = AsyncMock(
        return_value={"status": "active", "agent": {"name": "Velorum"}}
    )
    client.get_feed = AsyncMock(return_value=[])
    client.force_check_ban = AsyncMock(return_value=False)
    client.close = AsyncMock()
    return client


def _seed_cycle_state(app: VelorumApp) -> None:
    """Populate the Brain panel's CycleState from real learning data."""
    cs = app.cycle_state
    learn = app.memory.learning
    cs.set_phase("Deciding")
    try:
        import re

        raw = (learn.diverse_insights(n=1) or "").splitlines()
        first = raw[0] if raw else ""
        first = re.sub(r"\[/?[^\]]+\]", "", first)  # strip rich markup
        first = first.lstrip("-• ").strip()
        cs.update_learning(entropy=learn.entropy_score(), top_insight=first)
    except Exception:
        pass
    try:
        cs.update_bot_tiers(learn.bot_tier_counts())
    except Exception:
        pass
    ri = app.settings.reflection_interval_cycles or 10
    si = getattr(app.settings, "soul_update_interval_cycles", 500) or 500
    cs.update_countdowns(
        reflect_in=ri - (app._cycle % ri),
        soul_in=si - (app._cycle % si),
        cycle=app._cycle,
    )
    cs.set_queue(app.cycle_state.queued_actions or [])


def _seed_activity_log(app: VelorumApp) -> None:
    """Replay the last few real decisions as cycle narratives."""
    try:
        log_panel = app.query_one(ActivityLog)
        log = log_panel.get_log_widget()
    except Exception:
        return
    decisions = app.memory._decisions[-7:]
    base = max(app._cycle - len(decisions) + 1, 1)
    last_text = ""
    for i, d in enumerate(decisions):
        text = app._generate_cycle_narrative(base + i, d)
        ts = datetime.now().strftime("%H:%M:%S")
        log.write(Text.from_markup(f"[dim cyan][{ts}][/dim cyan] {text}"))
        last_text = text
    if last_text:
        try:
            from textual.widgets import Static
            app.query_one("#narrator", Static).update(last_text)
        except Exception:
            pass


async def capture(out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    settings = Settings()
    c = init_components(settings)
    c.client = _mock_client()

    app = VelorumApp(
        settings=settings,
        client=c.client,
        brain=c.brain,
        controller=c.controller,
        memory=c.memory,
        missions=c.missions,
        strategy=c.strategy,
        experiments=c.experiments,
        submolts=c.submolts,
        personality=c.personality,
        following=c.following,
        arena_client=None,
        arena_rooms=None,
        soul_proposals=c.soul_proposals,
        soul_evolution=c.soul_evolution,
        cycle_state=c.cycle_state,
    )
    app._paused = True  # prevent any real cycle/post during capture

    async with app.run_test(size=SIZE) as pilot:
        await pilot.pause(0.4)
        _seed_cycle_state(app)
        _seed_activity_log(app)
        # Seed the narrator band with the most recent cycle narrative so the
        # top of the Activity panel isn't blank in a static frame.
        try:
            from rich.text import Text
            from textual.widgets import Static

            last = app.memory._decisions[-1] if app.memory._decisions else None
            if last is not None:
                narrative = app._generate_cycle_narrative(app._cycle, last)
                plain = Text.from_markup(narrative).plain
                app.query_one("#narrator", Static).update(plain)
        except Exception:
            pass
        # Refresh visible panels with seeded state
        try:
            app.query_one(OrchestratorPanel)._refresh_state()
        except Exception:
            pass
        try:
            app.query_one(StatsPanel).set_status("Online")
            last = app.memory._decisions[-1] if app.memory._decisions else None
            if last:
                app.query_one(StatsPanel).set_last_action(
                    f"{last.get('action', '?')} — cycle {app._cycle}"
                )
            app.query_one(StatsPanel).countdown = settings.cycle_interval_seconds
        except Exception:
            pass
        await pilot.pause(0.3)

        tabbed = app.query_one(TabbedContent)

        shots = [
            ("velorum-brain", "tab-brain"),
            ("velorum-soul", "tab-soul"),
            ("velorum-mission", "tab-mission"),
            ("velorum-settings", "tab-settings"),
        ]
        for name, tab_id in shots:
            try:
                tabbed.active = tab_id
            except Exception:
                continue
            await pilot.pause(0.35)
            path = out_dir / f"{name}.svg"
            app.save_screenshot(str(path))
            print(f"saved {path}")


if __name__ == "__main__":
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("docs/assets/screenshots")
    asyncio.run(capture(out))
