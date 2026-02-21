"""Main Textual application for the Velorum TUI dashboard."""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Container
from textual.widgets import Footer, Header, TabbedContent, TabPane

from velorum.tui.widgets.activity_log import ActivityLog, TUILogHandler
from velorum.tui.widgets.mission_panel import MissionPanel
from velorum.tui.widgets.settings_panel import SettingsPanel
from velorum.tui.widgets.soul_editor import SoulEditor
from velorum.tui.widgets.stats_panel import StatsPanel

logger = logging.getLogger(__name__)


class VelorumApp(App):
    """Velorum TUI Dashboard."""

    TITLE = "Velorum Dashboard"
    CSS_PATH = "velorum.tcss"

    BINDINGS = [
        Binding("ctrl+q", "quit", "Quit", show=True, priority=True),
        Binding("ctrl+p", "toggle_pause", "Pause/Resume", show=True, priority=True),
        Binding("ctrl+f", "force_cycle", "Force Cycle", show=True, priority=True),
        Binding("ctrl+o", "force_post", "Force Post", show=True, priority=True),
        Binding("ctrl+s", "save_soul", "Save Soul", show=True, priority=True),
        Binding("ctrl+m", "focus_mission", "Mission", show=True, priority=True),
        Binding("ctrl+b", "check_ban", "Check Ban", show=True, priority=True),
    ]

    def __init__(
        self,
        settings: object,
        client: object,
        brain: object,
        controller: object,
        memory: object,
        missions: object | None = None,
        strategy: object | None = None,
        experiments: object | None = None,
        submolts: object | None = None,
    ) -> None:
        super().__init__()
        self.settings = settings
        self.client = client
        self.brain = brain
        self.controller = controller
        self.memory = memory
        self.missions = missions
        self.strategy = strategy
        self.experiments = experiments
        self.submolts = submolts
        self._paused = False
        self._cycle = 0
        self._force_event = asyncio.Event()
        self._log_handler: TUILogHandler | None = None

    def compose(self) -> ComposeResult:
        yield Header()
        yield StatsPanel(id="stats-panel")
        yield ActivityLog(id="activity-log-panel")
        with Container(id="bottom-pane"):
            with TabbedContent():
                with TabPane("Soul Editor", id="tab-soul"):
                    yield SoulEditor(
                        soul_path=Path(self.settings.soul_file),
                        brain=self.brain,
                    )
                with TabPane("Mission", id="tab-mission"):
                    if self.missions:
                        yield MissionPanel(
                            mission_manager=self.missions,
                            id="mission-panel",
                        )
                with TabPane("Settings", id="tab-settings"):
                    yield SettingsPanel(settings=self.settings)
        yield Footer()

    async def on_mount(self) -> None:
        root = logging.getLogger()
        for handler in root.handlers[:]:
            root.removeHandler(handler)

        activity_log = self.query_one(ActivityLog)
        rich_log = activity_log.get_log_widget()
        self._log_handler = TUILogHandler(rich_log)
        self._log_handler.setLevel(logging.INFO)
        root.addHandler(self._log_handler)
        root.setLevel(logging.INFO)

        stats = self.query_one(StatsPanel)
        stats.set_status("Online")
        stats.set_last_action("Starting up")
        self._refresh_stats()

        logger.info("Velorum dashboard started")
        logger.info(
            "Provider: %s | Model: %s",
            self.settings.llm_provider,
            self.settings.llm_model,
        )
        logger.info(
            "Cycle: %ds | Confidence: \u2265%d | Rate: %d/hr | Thread depth: %d",
            self.settings.cycle_interval_seconds,
            self.settings.confidence_threshold,
            self.settings.max_responses_per_hour,
            self.settings.max_thread_depth,
        )

        # Log mission status
        if self.missions and self.missions.active_mission:
            m = self.missions.active_mission
            logger.info(
                "Active mission: %s (status: %s, %.0f%% complete)",
                m.prompt[:60], m.status, m.completion_pct(),
            )

        # Log strategy status
        if self.strategy:
            summary = self.strategy.summary_for_prompt()
            if summary:
                logger.info("Strategy active with %d parameters", len(self.strategy._params.update_history))

        # Check agent status with Moltbook at startup
        try:
            status_data = await self.client.check_status()
            if status_data:
                claim_status = status_data.get("status", "unknown")
                agent_info = status_data.get("agent", {})
                name = agent_info.get("name", self.settings.agent_name)
                logger.info(
                    "Moltbook: %s (status: %s)", name, claim_status
                )
                if claim_status == "pending_claim":
                    logger.warning(
                        "Agent not yet claimed — posting may be restricted"
                    )
                if self.client.is_banned:
                    from velorum.tui.widgets.stats_panel import _fmt_duration
                    remaining = self.client.ban_remaining_seconds()
                    logger.warning(
                        "Agent is BANNED for %s (reason: %s)",
                        _fmt_duration(remaining),
                        self.client.ban_reason,
                    )
                    stats.set_status("Banned")
                    stats.set_last_action(f"Banned: {self.client.ban_reason}")
            else:
                logger.warning("Could not verify agent status with Moltbook")
        except Exception:
            logger.warning("Moltbook status check failed at startup")

        # Refresh stale data from server
        if not self.client.is_banned:
            try:
                from velorum.main import refresh_data
                logger.info("Refreshing data from server...")
                await refresh_data(self.client, self.memory)
                self._refresh_stats()
            except Exception:
                logger.warning("Data refresh failed at startup")

        # Discover and subscribe to submolts
        if not self.client.is_banned and self.submolts:
            try:
                from velorum.main import discover_submolts
                if self.submolts.needs_discovery(
                    self.settings.submolt_discovery_interval_cycles,
                    self.settings.cycle_interval_seconds,
                ):
                    await discover_submolts(self.client, self.submolts, self.settings)
            except Exception:
                logger.warning("Submolt discovery failed at startup")

        # Plan mission if needed
        if self.missions and self.missions.active_mission:
            if self.missions.active_mission.status == "planning":
                self.run_worker(self._plan_mission_worker(), exclusive=False, thread=False)

        self.run_worker(self._cycle_loop(), exclusive=True, thread=False)

    async def on_unmount(self) -> None:
        if self._log_handler:
            logging.getLogger().removeHandler(self._log_handler)
        if hasattr(self.client, "close"):
            await self.client.close()

    async def _plan_mission_worker(self) -> None:
        """Plan a mission that's in planning status."""
        if not self.missions or not self.missions.active_mission:
            return
        m = self.missions.active_mission
        logger.info("Planning mission: %s", m.prompt[:60])

        plan = await self.brain.plan_mission(
            mission_prompt=m.prompt,
            bot_relationships=self.memory.learning.bot_relationships_summary(),
            engagement_summary=self.memory.learning.engagement_summary(),
        )
        if plan:
            self.missions.apply_plan(plan)
            logger.info("Mission planned: %d steps", len(self.missions.active_mission.steps))
            self.notify("Mission planned!")
            self._refresh_mission_panel()
        else:
            logger.warning("Failed to plan mission")
            self.notify("Mission planning failed", severity="error")

    async def _cycle_loop(self) -> None:
        """Main loop running decision cycles."""
        from velorum.main import check_engagement, profile_bots, run_cycle
        from velorum.tui.widgets.stats_panel import _fmt_duration

        stats = self.query_one(StatsPanel)

        while True:
            # Ban watch — wait until ban expires
            if self.client.is_banned:
                remaining = self.client.ban_remaining_seconds()
                logger.warning(
                    "Agent is banned for %s (reason: %s) — waiting for ban to expire",
                    _fmt_duration(remaining),
                    self.client.ban_reason,
                )
                stats.set_status("Banned")
                stats.set_last_action(
                    f"Banned: {self.client.ban_reason}"
                )
                while self.client.is_banned:
                    remaining = self.client.ban_remaining_seconds()
                    stats.set_ban_remaining(remaining)
                    await asyncio.sleep(1)
                # Ban timer expired — verify with server before resuming
                stats.set_ban_remaining(0)
                logger.info("Ban timer expired — verifying with server...")
                still_banned = await self.client.force_check_ban()
                if still_banned:
                    logger.warning("Server says still banned — continuing to wait")
                    continue
                logger.info("Ban confirmed expired — resuming normal operation")
                self.notify("Ban expired — resuming")
                stats.set_status("Online")
                stats.set_last_action("Ban expired — back online")
                self._refresh_stats()

            if not self._paused:
                self._cycle += 1
                logger.info("\u2500\u2500\u2500 Cycle %d \u2500\u2500\u2500", self._cycle)

                # Full cycle: conversations + feed + decide + act
                stats.set_status("Fetching feed")
                try:
                    await run_cycle(
                        self.client,
                        self.brain,
                        self.controller,
                        self.memory,
                        self.settings,
                        self.missions,
                        self.strategy,
                        self.experiments,
                        self.submolts,
                    )

                    # Check if cycle detected a ban
                    if self.client.is_banned:
                        continue  # go back to top to enter ban wait

                    # Determine what happened from memory
                    last = (
                        self.memory._decisions[-1]
                        if self.memory._decisions
                        else None
                    )
                    if last:
                        action = last.get("action", "?")
                        if action == "RESPOND":
                            post_id = last.get("post_id", "?")
                            conf = last.get("confidence", "?")
                            stats.set_last_action(
                                f"Commented on {post_id} (conf: {conf})"
                            )
                        elif action == "POST":
                            title = last.get("post_title", "?")[:40]
                            submolt = last.get("post_submolt", "?")
                            stats.set_last_action(
                                f"Posted in {submolt}: {title}"
                            )
                        else:
                            stats.set_last_action(
                                f"Observed \u2014 {last.get('reasoning', '')[:50]}"
                            )
                except Exception:
                    logger.exception("Cycle %d failed", self._cycle)
                    stats.set_status("Error")
                    stats.set_last_action(f"Cycle {self._cycle} error")

                self._refresh_stats()
                self._refresh_mission_panel()

                # Engagement check every 3rd cycle
                if self._cycle % self.settings.engagement_check_interval_cycles == 0:
                    try:
                        stats.set_status("Checking engagement")
                        await check_engagement(self.client, self.memory, max_checks=self.settings.max_engagement_checks_per_cycle)
                    except Exception:
                        logger.debug("Engagement check failed")

                # Bot profiling
                if self._cycle % self.settings.profiling_interval_cycles == 0:
                    try:
                        await asyncio.sleep(2.0)  # space out from prior LLM calls
                        stats.set_status("Profiling bots")
                        await profile_bots(self.client, self.brain, self.memory)
                    except Exception:
                        logger.debug("Bot profiling failed")

                # Mission review
                if (
                    self.missions
                    and self.missions.active_mission
                    and self.missions.active_mission.status == "active"
                    and self._cycle % self.settings.mission_review_interval_cycles == 0
                ):
                    await asyncio.sleep(2.0)
                    stats.set_status("Reviewing mission")
                    logger.info("Reviewing mission progress...")
                    try:
                        review = await self.brain.review_mission(
                            mission=self.missions.active_mission.to_dict(),
                            recent_actions=self.memory.recent_decisions_text(),
                            engagement_summary=self.memory.learning.engagement_summary(),
                            bot_relationships=self.memory.learning.bot_relationships_summary(),
                        )
                        if review:
                            self.missions.apply_review(review)
                            logger.info(
                                "Mission review: %s",
                                review.get("progress_assessment", "")[:100],
                            )
                            self._refresh_mission_panel()
                    except Exception:
                        logger.exception("Mission review failed")

                # Reflection
                if self._cycle % self.settings.reflection_interval_cycles == 0:
                    await asyncio.sleep(2.0)
                    stats.set_status("Reflecting")
                    logger.info("Running reflection...")
                    try:
                        mission_ctx = self.missions.mission_context_for_prompt() if self.missions else ""
                        strategy_ctx = self.strategy.summary_for_prompt() if self.strategy else ""
                        reflection = await self.brain.reflect(
                            engagement_summary=self.memory.learning.engagement_summary(),
                            bot_relationships=self.memory.learning.bot_relationships_summary(),
                            conversations_summary=self.memory.conversations.summary_text(),
                            mission_context=mission_ctx,
                            strategy_context=strategy_ctx,
                        )
                        if reflection:
                            logger.info(
                                "Assessment: %s",
                                reflection.behavior_assessment[:200],
                            )
                            logger.info(
                                "Recommendation: %s",
                                reflection.adjustment_recommendation[:200],
                            )
                            if reflection.engagement_insight:
                                self.memory.learning.add_insight(
                                    reflection.engagement_insight,
                                    source=f"reflection_cycle_{self._cycle}",
                                )
                                self.memory.save()
                    except Exception:
                        logger.exception("Reflection failed")

                # Strategy update (less frequent)
                if self._cycle % self.settings.strategy_update_interval_cycles == 0:
                    await asyncio.sleep(2.0)
                    stats.set_status("Updating strategy")
                    logger.info("Updating strategy...")
                    try:
                        mission_ctx = self.missions.mission_context_for_prompt() if self.missions else ""
                        result = await self.brain.update_strategy(
                            current_strategy=self.strategy.summary_for_prompt() if self.strategy else "",
                            engagement_data=self.memory.learning.engagement_summary(),
                            bot_profiles=self.memory.learning.bot_relationships_summary(),
                            insights=self.memory.learning.recent_insights(),
                            mission_context=mission_ctx,
                        )
                        if result and self.strategy:
                            self.strategy.apply_update(result)
                            logger.info(
                                "Strategy updated: %s",
                                result.get("assessment", "")[:100],
                            )
                    except Exception:
                        logger.exception("Strategy update failed")

                # Periodic submolt re-discovery
                if (
                    self.submolts
                    and self._cycle % self.settings.submolt_discovery_interval_cycles == 0
                ):
                    try:
                        from velorum.main import discover_submolts
                        await discover_submolts(self.client, self.submolts, self.settings)
                    except Exception:
                        logger.debug("Submolt re-discovery failed")

            # Transition to waiting
            if self._paused:
                stats.set_status("Paused")
            else:
                stats.set_status("Waiting")
                stats.countdown = self.settings.cycle_interval_seconds

            self._force_event.clear()
            try:
                await asyncio.wait_for(
                    self._force_event.wait(),
                    timeout=self.settings.cycle_interval_seconds,
                )
                logger.info("Forced cycle triggered")
            except asyncio.TimeoutError:
                pass

    def _refresh_stats(self) -> None:
        stats = self.query_one(StatsPanel)
        stats.update_stats(
            cycle=self._cycle,
            settings=self.settings,
            controller=self.controller,
            memory=self.memory,
        )

    def _refresh_mission_panel(self) -> None:
        try:
            panel = self.query_one(MissionPanel)
            panel.refresh_display()
        except Exception:
            pass  # panel may not exist

    def action_toggle_pause(self) -> None:
        self._paused = not self._paused
        stats = self.query_one(StatsPanel)
        if self._paused:
            stats.set_status("Paused")
            logger.info("Cycle loop paused")
            self.notify("Paused", severity="warning")
        else:
            stats.set_status("Online")
            logger.info("Cycle loop resumed")
            self.notify("Resumed")
            self._force_event.set()

    def action_force_cycle(self) -> None:
        if self.client.is_banned:
            from velorum.tui.widgets.stats_panel import _fmt_duration
            remaining = self.client.ban_remaining_seconds()
            self.notify(
                f"Banned for {_fmt_duration(remaining)}", severity="error"
            )
            return
        if self._paused:
            self.notify("Unpause first (Ctrl+P)", severity="warning")
            return
        logger.info("Forcing immediate cycle")
        self.notify("Forcing cycle...")
        self._force_event.set()

    def action_force_post(self) -> None:
        if self.client.is_banned:
            from velorum.tui.widgets.stats_panel import _fmt_duration
            remaining = self.client.ban_remaining_seconds()
            self.notify(
                f"Banned for {_fmt_duration(remaining)}", severity="error"
            )
            return
        logger.info("Force post triggered")
        self.notify("Generating post...")
        self.run_worker(self._force_post_worker(), exclusive=False, thread=False)

    async def _force_post_worker(self) -> None:
        """Force the brain to generate and publish an original post.

        Uses the dedicated post-generation prompt (not the decision prompt)
        so the brain MUST produce a post — no OBSERVE option.
        """
        from velorum.main import _handle_post

        stats = self.query_one(StatsPanel)
        stats.set_status("Creating post")

        try:
            # Gather context: feed topics for inspiration
            feed_topics = ""
            try:
                posts = await self.client.get_feed()
                if posts:
                    topics = [f"- {p.title} (by {p.author}, {p.submolt})" for p in posts[:10]]
                    feed_topics = "\n".join(topics)
            except Exception:
                logger.warning("Could not fetch feed for post context")

            mission_ctx = self.missions.mission_context_for_prompt() if self.missions else ""
            strategy_ctx = self.strategy.summary_for_prompt() if self.strategy else ""
            submolts_ctx = self.submolts.names_for_prompt() if self.submolts else ""

            # Use the dedicated post-generation prompt
            decision = await self.brain.generate_post(
                recent_posts_summary=self.memory.recent_posts_summary(),
                learning_insights=self.memory.learning.recent_insights(),
                bot_relationships=self.memory.learning.bot_relationships_summary(),
                engagement_summary=self.memory.learning.engagement_summary(),
                conversations_summary=self.memory.conversations.summary_text(),
                feed_topics=feed_topics,
                mission_context=mission_ctx,
                strategy_context=strategy_ctx,
                available_submolts=submolts_ctx,
            )

            if decision is None:
                logger.warning("Brain failed to generate post (parse error)")
                self.notify("Post failed — brain parse error", severity="error")
                return

            if not decision.post_title or not decision.post_content:
                logger.warning("Brain returned post with missing title/content")
                self.notify("Post failed — empty title or content", severity="error")
                return

            logger.info(
                "Brain generated post: \"%s\" in %s",
                decision.post_title[:60],
                decision.post_submolt,
            )

            # Execute the post (bypasses controller rate limits for force)
            success = await _handle_post(
                self.client,
                self.controller,
                self.memory,
                decision,
                self.settings,
            )

            if success:
                self.memory.record_decision(decision)
                if self.missions:
                    self.missions.record_action("POST", f"Force posted: {decision.post_title[:60]}")
                stats.set_last_action(
                    f"Posted in {decision.post_submolt}: {decision.post_title[:40]}"
                )
                self.notify(f"Posted: {decision.post_title[:50]}")
            else:
                self.notify("Post failed — API rejected", severity="error")

        except Exception:
            logger.exception("Force post failed")
            self.notify("Force post failed", severity="error")
        finally:
            self._refresh_stats()
            self._refresh_mission_panel()
            if not self._paused:
                stats.set_status("Online")
            else:
                stats.set_status("Paused")

    def action_save_soul(self) -> None:
        editor = self.query_one(SoulEditor)
        if not editor.is_modified:
            self.notify("No changes to save")
            return
        if editor.save():
            self.notify("Soul saved \u2014 active next cycle")
        else:
            self.notify("Failed to save soul", severity="error")

    def action_check_ban(self) -> None:
        """Force-verify ban status with the server."""
        logger.info("Force checking ban status with server...")
        self.notify("Checking ban status...")
        self.run_worker(self._check_ban_worker(), exclusive=False, thread=False)

    async def _check_ban_worker(self) -> None:
        stats = self.query_one(StatsPanel)
        still_banned = await self.client.force_check_ban()
        if still_banned:
            from velorum.tui.widgets.stats_panel import _fmt_duration
            remaining = self.client.ban_remaining_seconds()
            self.notify(
                f"Still banned for {_fmt_duration(remaining)}",
                severity="error",
            )
            stats.set_status("Banned")
        else:
            self.notify("Not banned! Resuming...")
            stats.set_status("Online")
            stats.set_last_action("Ban cleared — back online")
            self._refresh_stats()
            # Trigger a cycle
            self._force_event.set()

    def action_focus_mission(self) -> None:
        """Switch to the Mission tab and focus the input."""
        try:
            tabbed = self.query_one(TabbedContent)
            tabbed.active = "tab-mission"
            inp = self.query_one("#mission-input")
            inp.focus()
        except Exception:
            pass
