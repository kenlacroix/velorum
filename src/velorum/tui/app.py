"""Main Textual application for the Velorum TUI dashboard."""

from __future__ import annotations

import asyncio
import logging
import time
from pathlib import Path

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Container
from textual.widgets import Footer, Header, TabbedContent, TabPane

from velorum.context import build_context
from velorum.tui.widgets.activity_log import ActivityLog, TUILogHandler
from velorum.tui.widgets.mission_panel import MissionPanel
from velorum.tui.widgets.orchestrator_panel import OrchestratorPanel
from velorum.tui.widgets.settings_panel import SettingsPanel
from velorum.tui.widgets.soul_editor import SoulEditor
from velorum.tui.widgets.soul_proposal_modal import SoulProposalModal
from velorum.tui.widgets.stats_panel import StatsPanel

logger = logging.getLogger(__name__)
activity = logging.getLogger("velorum.activity")


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
        Binding("ctrl+u", "force_soul_proposal", "Soul Proposal", show=True, priority=True),
        Binding("ctrl+n", "focus_brain", "Brain", show=True, priority=True),
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
        personality: object | None = None,
        following: object | None = None,
        arena_client: object | None = None,
        arena_rooms: object | None = None,
        soul_proposals: object | None = None,
        soul_evolution: object | None = None,
        cycle_state: object | None = None,
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
        self.personality = personality
        self.following = following
        self.arena_client = arena_client
        self.arena_rooms = arena_rooms
        self.soul_proposals = soul_proposals
        self.soul_evolution = soul_evolution
        self.cycle_state = cycle_state
        self._paused = False
        self._cycle = memory.total_cycle  # resume lifetime cycle count
        self._force_event = asyncio.Event()
        self._log_handler: TUILogHandler | None = None
        self._force_post_in_progress = False
        self._attempt = 0
        self._failed_cycles = 0
        # Capture session baselines from persisted disk state (before refresh_data),
        # so session stats reflect only this session's activity.
        self._session_start_posts = memory.post_count
        self._session_start_responds = sum(
            1 for d in memory._decisions if d.get("action") == "RESPOND"
        )
        self._session_start_upvotes = len(memory._upvoted_ids)
        self._session_start_time = time.time()

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
                with TabPane("Brain", id="tab-brain"):
                    yield OrchestratorPanel(
                        cycle_state=self.cycle_state,
                        id="orchestrator-panel",
                    )
        yield Footer()

    async def on_mount(self) -> None:
        root = logging.getLogger()
        for handler in root.handlers[:]:
            root.removeHandler(handler)

        activity_log = self.query_one(ActivityLog)
        self._log_handler = TUILogHandler(activity_log)
        self._log_handler.setLevel(logging.INFO)
        root.addHandler(self._log_handler)
        root.setLevel(logging.INFO)

        stats = self.query_one(StatsPanel)
        stats.set_status("Online")
        stats.set_last_action("Starting up")
        self._refresh_stats()

        # Write startup info directly to the committed log
        activity_log.log_info(
            f"Velorum started — {self.settings.llm_provider}/{self.settings.llm_model}"
        )
        activity_log.log_info(
            f"Cycle {self.settings.cycle_interval_seconds}s | "
            f"Confidence \u2265{self.settings.confidence_threshold} | "
            f"Rate {self.settings.max_responses_per_hour}/hr"
        )

        if self.missions and self.missions.active_mission:
            m = self.missions.active_mission
            activity_log.log_info(
                f"Mission: {m.prompt[:60]} ({m.status}, {m.completion_pct():.0f}% complete)"
            )

        if self.strategy:
            summary = self.strategy.summary_for_prompt()
            if summary:
                activity_log.log_info(
                    f"Strategy active ({len(self.strategy._params.update_history)} updates)"
                )

        # Plan mission if needed
        if self.missions and self.missions.active_mission:
            if self.missions.active_mission.status == "planning":
                self.run_worker(self._plan_mission_worker(), exclusive=False, thread=False)

        # Run network-dependent startup in a worker so the UI renders immediately
        self.run_worker(self._startup_worker(), exclusive=False, thread=False)
        self.run_worker(self._cycle_loop(), exclusive=True, thread=False)

        # Launch Arena loop if enabled
        arena_enabled = getattr(self.settings, "arena_enabled", False)
        if arena_enabled and self.arena_client and self.arena_rooms:
            self.run_worker(self._arena_loop(), exclusive=False, thread=False)

    async def on_unmount(self) -> None:
        if self._log_handler:
            logging.getLogger().removeHandler(self._log_handler)
        if hasattr(self.client, "close"):
            await self.client.close()
        if self.arena_client and hasattr(self.arena_client, "close"):
            await self.arena_client.close()

    async def _startup_worker(self) -> None:
        """Run network-dependent startup tasks without blocking the UI."""
        stats = self.query_one(StatsPanel)

        # Check agent status with Moltbook
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

        # Ensure epoch 0 (origin) is recorded on first ever run
        if self.soul_evolution is not None:
            self.soul_evolution.initialize_origin(
                soul_text=self.brain._soul,
                cycle=self._cycle,
            )

        # Discover and subscribe to submolts; score affinity if missing
        if not self.client.is_banned and self.submolts:
            try:
                from velorum.main import _score_submolt_affinities, discover_submolts
                if self.submolts.needs_discovery(
                    self.settings.submolt_discovery_interval_cycles,
                    self.settings.cycle_interval_seconds,
                ):
                    await discover_submolts(self.client, self.submolts, self.settings, brain=self.brain)
                elif self.submolts.needs_affinity_scoring() and self.submolts.discovered:
                    # Submolts already discovered but affinities not yet computed
                    logger.info("Running soul-affinity scoring for existing submolts...")
                    await _score_submolt_affinities(self.brain, self.submolts)
            except Exception:
                logger.warning("Submolt discovery/scoring failed at startup")

    async def _rescore_submolts_worker(self) -> None:
        """Re-score submolt affinities after a soul change."""
        from velorum.main import _score_submolt_affinities
        activity.info("Soul changed \u2014 re-scoring submolt affinities...")
        try:
            await _score_submolt_affinities(self.brain, self.submolts)
            self.notify("Submolt affinities updated for new soul")
        except Exception:
            logger.warning("Submolt rescore after soul change failed")

    async def _arena_loop(self) -> None:
        """Run the Agent Arena turn-polling loop as a TUI worker."""
        from velorum.main import arena_loop

        try:
            await arena_loop(
                self.arena_client, self.brain, self.memory,
                self.arena_rooms, self.settings,
            )
        except Exception:
            logger.exception("Arena loop crashed")

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
        activity_log = self.query_one(ActivityLog)

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
                self._attempt += 1
                activity.info("Starting cycle %d...", self._cycle + 1)

                # Full cycle: conversations + feed + decide + act
                stats.set_status("Fetching feed")
                cycle_exception: Exception | None = None
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
                        self.personality,
                        self.following,
                        self.cycle_state,
                    )
                except Exception as _exc:
                    cycle_exception = _exc
                    logger.exception("Cycle failed (attempt %d)", self._attempt)

                # Check if cycle detected a ban
                if self.client.is_banned:
                    activity_log.clear_status()
                    continue  # go back to top to enter ban wait

                if cycle_exception is not None:
                    # Hard failure (exception): don't count this cycle
                    self._failed_cycles += 1
                    narrative = (
                        f"Cycle {self._cycle + 1} hit an unexpected error — "
                        f"{str(cycle_exception)[:100]}. Will retry next interval."
                    )
                    stats.set_status("Error")
                    stats.set_last_action(f"Cycle error (attempt {self._attempt})")
                else:
                    # Cycle completed — check if the primary action actually worked
                    last = self.memory._decisions[-1] if self.memory._decisions else None
                    action_failed = (
                        last is not None
                        and last.get("reasoning", "").startswith("FAILED")
                    )

                    if action_failed:
                        # Action was attempted but failed (e.g. 404) — don't count
                        self._failed_cycles += 1
                        narrative = self._generate_cycle_narrative(self._cycle + 1, last)
                        stats.set_status("Error")
                        stats.set_last_action(
                            f"Action failed (attempt {self._attempt})"
                        )
                    else:
                        # Genuine success
                        self._cycle += 1
                        self.memory.total_cycle = self._cycle
                        narrative = self._generate_cycle_narrative(self._cycle, last)
                        # Update CycleState countdowns
                        if self.cycle_state is not None:
                            _ri = self.settings.reflection_interval_cycles
                            _si = getattr(self.settings, "soul_update_interval_cycles", 500)
                            _reflect_in = _ri - (self._cycle % _ri) if _ri > 0 else 0
                            _soul_in = _si - (self._cycle % _si) if _si > 0 else 0
                            self.cycle_state.update_countdowns(
                                reflect_in=_reflect_in,
                                soul_in=_soul_in,
                                cycle=self._cycle,
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
                                title = (last.get("post_title") or "?")[:40]
                                submolt = last.get("post_submolt", "?")
                                stats.set_last_action(
                                    f"Posted in {submolt}: {title}"
                                )
                            else:
                                stats.set_last_action(
                                    f"Observed \u2014 {last.get('reasoning', '')[:50]}"
                                )

                # Stream the cycle narrative (awaited — ~1s, then continue)
                await activity_log.stream_narrative(narrative)

                # Session report every 10 completed cycles
                if self._cycle > 0 and self._cycle % 10 == 0:
                    await activity_log.stream_narrative(
                        self._generate_session_narrative(), delay=0.02
                    )

                self._refresh_stats()
                self._refresh_mission_panel()

                # Engagement check every 3rd cycle (gated when conversations disabled)
                if (
                    self._cycle % self.settings.engagement_check_interval_cycles == 0
                    and self.settings.conversations_enabled
                ):
                    try:
                        stats.set_status("Checking engagement")
                        activity.info("Checking for replies in active conversations...")
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
                    activity.info("Reflecting on recent activity and refining my approach...")
                    try:
                        # Apply personality and insight decay before reflection
                        if self.personality:
                            self.personality.apply_decay()
                        self.memory.learning.decay_insights()
                        ref_ctx = build_context(
                            self.memory,
                            missions=self.missions,
                            strategy=self.strategy,
                            personality=self.personality,
                            submolts=self.submolts,
                            conversations_enabled=bool(self.settings.conversations_enabled),
                            dms_enabled=bool(getattr(self.settings, "dms_enabled", False)),
                            following_enabled=bool(getattr(self.settings, "following_enabled", False)),
                            following=self.following,
                        )
                        reflection = await self.brain.reflect(**ref_ctx.for_reflection())
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
                            if reflection.trait_adjustments and self.personality:
                                self.personality.apply_reflection_update(reflection.trait_adjustments)
                            if reflection.submolt_observations and self.submolts:
                                self.submolts.update_tone_profiles(reflection.submolt_observations)
                                logger.info("Updated tone profiles for %d submolt(s)", len(reflection.submolt_observations))

                        # DM outreach evaluation (post-reflection, gated)
                        dms_on = getattr(self.settings, "dms_enabled", False)
                        dm_outreach_on = getattr(self.settings, "dm_outreach_enabled", False)
                        if dms_on and dm_outreach_on:
                            try:
                                outreach = await self.brain.evaluate_dm_outreach(
                                    dm_candidates=ref_ctx.dm_candidates,
                                    active_dm_summary=ref_ctx.dm_summary,
                                    mission_context=ref_ctx.mission_context,
                                    strategy_context=ref_ctx.strategy_context,
                                )
                                if outreach and outreach.should_dm and outreach.target_bot and outreach.intro_message:
                                    if not self.memory.dms.has_pending_or_active(outreach.target_bot):
                                        try:
                                            await self.client.dm_send_request(outreach.target_bot, outreach.intro_message)
                                            self.memory.dms.record_outbound_request(outreach.target_bot)
                                            self.memory.save()
                                            logger.info(
                                                "Sent DM request to %s: %s",
                                                outreach.target_bot, outreach.reasoning[:60],
                                            )
                                        except Exception:
                                            logger.warning("Failed to send DM request to %s", outreach.target_bot)
                            except Exception:
                                logger.debug("DM outreach evaluation failed")

                        # Following evaluation (gated, runs at interval)
                        following_on = getattr(self.settings, "following_enabled", False)
                        following_interval = getattr(self.settings, "following_check_interval_cycles", 23)
                        if (
                            following_on
                            and self.following
                            and self._cycle % following_interval == 0
                        ):
                            try:
                                follow_rec = await self.brain.evaluate_following(
                                    bot_relationships=ref_ctx.bot_relationships,
                                    currently_following=self.following.summary_for_prompt(),
                                    dm_summary=ref_ctx.dm_summary,
                                    mission_context=ref_ctx.mission_context,
                                    strategy_context=ref_ctx.strategy_context,
                                )
                                if follow_rec:
                                    max_following = getattr(self.settings, "max_following", 10)
                                    for name in follow_rec.follow:
                                        if self.following.count >= max_following:
                                            break
                                        if not self.following.is_following(name):
                                            try:
                                                await self.client.follow_agent(name)
                                                self.following.add(name)
                                                logger.info("Now following %s", name)
                                            except Exception:
                                                logger.warning("Failed to follow %s", name)
                                    for name in follow_rec.unfollow:
                                        if self.following.is_following(name):
                                            try:
                                                await self.client.unfollow_agent(name)
                                                self.following.remove(name)
                                                logger.info("Unfollowed %s", name)
                                            except Exception:
                                                logger.warning("Failed to unfollow %s", name)
                                    self.following.save()
                            except Exception:
                                logger.debug("Following evaluation failed")

                    except Exception:
                        logger.exception("Reflection failed")

                # Strategy update (less frequent)
                if self._cycle % self.settings.strategy_update_interval_cycles == 0:
                    await asyncio.sleep(2.0)
                    stats.set_status("Updating strategy")
                    activity.info("Reviewing behavioral strategy and calibrating parameters...")
                    try:
                        strat_ctx = build_context(
                            self.memory, missions=self.missions,
                            strategy=self.strategy, personality=self.personality,
                            submolts=self.submolts,
                        )
                        result = await self.brain.update_strategy(
                            current_strategy=self.strategy.summary_for_prompt() if self.strategy else "",
                            **strat_ctx.for_strategy(),
                        )
                        if result and self.strategy:
                            self.strategy.apply_update(result)
                            logger.info(
                                "Strategy updated: %s",
                                result.get("assessment", "")[:100],
                            )
                    except Exception:
                        logger.exception("Strategy update failed")

                # Soul evolution proposal (very rare)
                soul_interval = getattr(self.settings, "soul_update_interval_cycles", 500)
                if (
                    self._cycle > 0
                    and self._cycle % soul_interval == 0
                    and self.soul_proposals is not None
                ):
                    await asyncio.sleep(2.0)
                    stats.set_status("Reflecting")
                    logger.info("Generating soul amendment proposal...")
                    try:
                        ref_ctx = build_context(
                            self.memory, missions=self.missions,
                            strategy=self.strategy, personality=self.personality,
                            submolts=self.submolts,
                        )
                        evolution_ctx = self.soul_evolution.evolution_context() if self.soul_evolution else ""
                        amendment = await self.brain.propose_soul_amendment(
                            soul=self.brain._soul[:800],
                            personality_history=self.personality.history_summary() if self.personality else "",
                            strategy_history=self.strategy.history_summary() if self.strategy else "",
                            top_insights=self.memory.learning.diverse_insights(n=5),
                            bot_relationships=self.memory.learning.bot_relationships_summary(),
                            evolution_history=evolution_ctx,
                        )
                        if amendment and amendment.get("proposed_amendment"):
                            from velorum.soul import SoulProposal
                            proposal = SoulProposal(
                                cycle=self._cycle,
                                proposed_amendment=amendment["proposed_amendment"],
                                reasoning=amendment.get("reasoning", ""),
                            )
                            self.soul_proposals.add(proposal)
                            logger.info("Soul amendment proposed at cycle %d", self._cycle)
                            self.push_screen(
                                SoulProposalModal(proposal),
                                lambda result, p=proposal: self._on_soul_proposal_result(result, p),
                            )
                    except Exception:
                        logger.exception("Soul amendment proposal failed")

                # Periodic submolt re-discovery
                if (
                    self.submolts
                    and self._cycle % self.settings.submolt_discovery_interval_cycles == 0
                ):
                    try:
                        from velorum.main import discover_submolts
                        await discover_submolts(self.client, self.submolts, self.settings, brain=self.brain)
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

    def _generate_cycle_narrative(self, cycle_num: int, last: dict | None) -> str:
        """Build a natural-language summary of the just-completed cycle."""
        if not last:
            return f"Cycle {cycle_num}: Nothing to report — the feed may have been empty."

        action = last.get("action", "OBSERVE")
        reasoning = (last.get("reasoning") or "").strip()

        if reasoning.startswith("FAILED"):
            err = reasoning[7:100].strip().rstrip(".")
            return (
                f"Cycle {cycle_num}: Tried to {action.lower()} but ran into an error — "
                f"{err}. Logging as an observation and moving on."
            )

        if action == "RESPOND":
            post_id = last.get("post_id", "")
            submolt = last.get("post_submolt") or "unknown"
            conf = last.get("confidence", 0)
            post_url = f"https://www.moltbook.com/post/{post_id}" if post_id else ""
            link = f"[link={post_url}]post[/link]" if post_url else "a post"
            short = reasoning[:70].rstrip(".,")
            return (
                f"Cycle {cycle_num}: Left a comment on {link} in [bold]{submolt}[/bold] "
                f"(confidence {conf}). {short}."
            )

        if action == "POST":
            title = (last.get("post_title") or "")[:50].rstrip(".")
            submolt = last.get("post_submolt") or "unknown"
            short = reasoning[:70].rstrip(".,")
            return (
                f"Cycle {cycle_num}: Published [italic]\"{title}\"[/italic] "
                f"in [bold]{submolt}[/bold]. {short}."
            )

        # OBSERVE
        short = reasoning[:100].rstrip(".,") or "Nothing in the feed stood out."
        return f"Cycle {cycle_num}: Observed — {short}."

    def _generate_session_narrative(self) -> str:
        """Build a multi-cycle session summary paragraph."""
        posts = self.memory.post_count - self._session_start_posts
        responds = (
            sum(1 for d in self.memory._decisions if d.get("action") == "RESPOND")
            - self._session_start_responds
        )
        upvotes = len(self.memory._upvoted_ids) - self._session_start_upvotes
        elapsed_secs = int(time.time() - self._session_start_time)
        h = elapsed_secs // 3600
        m = (elapsed_secs % 3600) // 60
        s = elapsed_secs % 60
        elapsed = f"{h}h {m:02d}m" if h else f"{m}m {s:02d}s"
        success_rate = (
            f"{self._cycle}/{self._attempt}"
            if self._attempt
            else f"{self._cycle}"
        )
        return (
            f"━━ Session checkpoint after {elapsed}: "
            f"{responds} comment(s), {posts} post(s), {upvotes} upvote(s). "
            f"{success_rate} cycles completed"
            + (f", {self._failed_cycles} failed" if self._failed_cycles else "")
            + ". ━━"
        )

    def _refresh_stats(self) -> None:
        stats = self.query_one(StatsPanel)
        stats.update_stats(
            cycle=self._cycle,
            settings=self.settings,
            controller=self.controller,
            memory=self.memory,
            personality=self.personality,
            soul_update_interval=getattr(self.settings, "soul_update_interval_cycles", 500),
        )

    def _on_soul_proposal_result(self, amendment_text: str | None, proposal: object) -> None:
        """Apply a soul amendment to the soul file, or dismiss it."""
        if not amendment_text:
            self.notify("Soul proposal dismissed", severity="warning")
            return
        try:
            soul_path = Path(self.settings.soul_file)
            existing = soul_path.read_text() if soul_path.exists() else ""
            updated = existing.rstrip() + f"\n\n---\n\n{amendment_text.strip()}\n"
            soul_path.write_text(updated)
            # Hot-reload into brain
            self.brain._soul = updated
            # Rescore submolts against updated soul
            if self.submolts and self.submolts.discovered:
                self.submolts.soul_affinities.clear()
                self.run_worker(self._rescore_submolts_worker(), exclusive=False, thread=False)
            # Mark proposal applied
            if self.soul_proposals is not None:
                self.soul_proposals.mark_applied(proposal.id)
            # Record evolution epoch
            if self.soul_evolution is not None:
                epoch = self.soul_evolution.add_epoch(
                    cycle=self._cycle,
                    amendment=amendment_text.strip(),
                    reasoning=getattr(proposal, "reasoning", ""),
                    soul_snapshot=updated,
                )
                epoch_num = epoch.epoch
                logger.info(
                    "Soul epoch %d recorded at cycle %d", epoch_num, self._cycle
                )
            else:
                epoch_num = "?"
            # Reload soul editor if visible
            try:
                editor = self.query_one(SoulEditor)
                editor._load()
            except Exception:
                pass
            self.notify(
                f"Soul epoch {epoch_num} recorded — edit further in Soul Editor tab",
                severity="information",
            )
            logger.info("Soul amendment applied at cycle %d", self._cycle)
        except Exception:
            logger.exception("Failed to apply soul amendment")
            self.notify("Failed to apply soul amendment", severity="error")

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
        if self._force_post_in_progress:
            self.notify("Post already in progress — please wait", severity="warning")
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

        self._force_post_in_progress = True
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

            post_ctx = build_context(
                self.memory,
                missions=self.missions,
                strategy=self.strategy,
                personality=self.personality,
                submolts=self.submolts,
                conversations_enabled=bool(self.settings.conversations_enabled),
            )

            # Pre-select the submolt — Python chooses from the soul-aligned pool.
            # The LLM is never asked to pick; it only writes content for the given submolt.
            recent_subs_set = set(self.memory.recent_post_submolts())
            selected_submolt = (
                self.submolts.pick_submolt(exclude=recent_subs_set)
                if self.submolts else ""
            )
            if not selected_submolt:
                logger.warning("No available submolt found — skipping force post")
                self.notify("No available submolt right now", severity="warning")
                return

            logger.info("Pre-selected submolt for post: %s", selected_submolt)

            # Use the dedicated post-generation prompt
            decision = await self.brain.generate_post(
                recent_posts_summary=self.memory.recent_posts_summary(),
                feed_topics=feed_topics,
                selected_submolt=selected_submolt,
                **post_ctx.for_post(),
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
            self._force_post_in_progress = False
            self._refresh_stats()
            self._refresh_mission_panel()
            if not self._paused:
                stats.set_status("Online")
            else:
                stats.set_status("Paused")

    def action_force_soul_proposal(self) -> None:
        if self.soul_proposals is None:
            self.notify("Soul proposals not enabled", severity="warning")
            return
        learn_stats = self.memory.learning.stats()
        insights = learn_stats.get("insights", 0)
        if insights < 3:
            self.notify(
                f"Only {insights} insight(s) so far — proposal may not be meaningful yet "
                f"(aim for ~5+ reflections / ~55+ cycles for useful results)",
                severity="warning",
                timeout=8,
            )
        self.notify("Generating soul proposal...")
        self.run_worker(self._force_soul_proposal_worker(), exclusive=False, thread=False)

    async def _force_soul_proposal_worker(self) -> None:
        """Force-generate a soul amendment proposal and show the review modal."""
        stats = self.query_one(StatsPanel)
        stats.set_status("Reflecting")
        try:
            evolution_ctx = self.soul_evolution.evolution_context() if self.soul_evolution else ""
            amendment = await self.brain.propose_soul_amendment(
                soul=self.brain._soul[:800],
                personality_history=self.personality.history_summary() if self.personality else "",
                strategy_history=self.strategy.history_summary() if self.strategy else "",
                top_insights=self.memory.learning.diverse_insights(n=5),
                bot_relationships=self.memory.learning.bot_relationships_summary(),
                evolution_history=evolution_ctx,
            )
            if amendment and amendment.get("proposed_amendment"):
                from velorum.soul import SoulProposal
                proposal = SoulProposal(
                    cycle=self._cycle,
                    proposed_amendment=amendment["proposed_amendment"],
                    reasoning=amendment.get("reasoning", ""),
                )
                self.soul_proposals.add(proposal)
                self.push_screen(
                    SoulProposalModal(proposal),
                    lambda result, p=proposal: self._on_soul_proposal_result(result, p),
                )
            else:
                self.notify("Brain returned no proposal — try again after more cycles", severity="warning")
        except Exception:
            logger.exception("Force soul proposal failed")
            self.notify("Soul proposal failed", severity="error")
        finally:
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
            if self.submolts and self.submolts.discovered:
                self.submolts.soul_affinities.clear()
                self.run_worker(self._rescore_submolts_worker(), exclusive=False, thread=False)
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

    def action_focus_brain(self) -> None:
        """Switch to the Brain orchestrator tab."""
        try:
            tabbed = self.query_one(TabbedContent)
            tabbed.active = "tab-brain"
        except Exception:
            pass
