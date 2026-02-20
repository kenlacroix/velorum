"""Entry point — main async run loop."""

from __future__ import annotations

import asyncio
import logging
import re
import sys

import httpx

_UUID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
    re.IGNORECASE,
)


def _is_uuid(value: str) -> bool:
    """Check if a string looks like a valid UUID."""
    return bool(_UUID_RE.match(value))

from velorum.brain import Brain
from velorum.config import Settings, load_settings
from velorum.controller import Controller
from velorum.conversations import ConversationMessage
from velorum.experiment import ExperimentLog
from velorum.llm.base import LLMProvider
from velorum.memory import Memory
from velorum.mission import MissionManager
from velorum.moltbook.client import MoltbookClient
from velorum.moltbook.models import Decision
from velorum.moltbook.verification import solve_challenge
from velorum.strategy import StrategyEngine

logger = logging.getLogger(__name__)


def init_components(
    settings: Settings,
) -> tuple[MoltbookClient, Brain, Controller, Memory, MissionManager, StrategyEngine, ExperimentLog]:
    """Initialize all bot components from settings."""
    if not settings.moltbook_api_key:
        logger.error("MOLTBOOK_API_KEY is required. Set it in .env")
        sys.exit(1)

    api_key = (
        settings.anthropic_api_key
        if settings.llm_provider == "anthropic"
        else settings.openai_api_key
    )
    if not api_key:
        logger.error("%s API key is required. Set it in .env", settings.llm_provider.upper())
        sys.exit(1)

    soul = ""
    if settings.soul_file.exists():
        soul = settings.soul_file.read_text()

    llm = LLMProvider.create(
        provider=settings.llm_provider,
        model=settings.llm_model,
        api_key=api_key,
        max_tokens=settings.llm_max_tokens,
    )
    memory = Memory(persist_path=settings.memory_file, agent_name=settings.agent_name)
    brain = Brain(llm=llm, memory=memory, soul=soul)
    controller = Controller(settings=settings, memory=memory)
    client = MoltbookClient(
        base_url=settings.moltbook_base_url,
        api_key=settings.moltbook_api_key,
        app_key=settings.moltbook_app_key,
        timeout=settings.http_timeout_seconds,
    )
    missions = MissionManager(persist_path=settings.mission_file)
    strategy = StrategyEngine(persist_path=settings.strategy_file)
    experiments = ExperimentLog(persist_path=settings.experiments_file)

    return client, brain, controller, memory, missions, strategy, experiments


# ---------------------------------------------------------------------------
# Phase 1: Check active conversations for new replies
# ---------------------------------------------------------------------------


async def check_conversations(
    client: MoltbookClient,
    brain: Brain,
    controller: Controller,
    memory: Memory,
    settings: Settings,
    mission_context: str = "",
    strategy_context: str = "",
) -> int:
    """Check active conversations for new replies and respond.

    Returns the number of replies sent.
    """
    if client.is_banned:
        return 0

    tracker = memory.conversations
    replies_sent = 0

    # Close stale conversations
    tracker.close_stale(max_age_seconds=settings.stale_conversation_hours * 3600)

    # Get conversations due for a check
    due = tracker.conversations_needing_check(
        check_interval=settings.conversation_check_interval,
    )

    if not due:
        return 0

    logger.info("Checking %d active conversation(s) for replies", len(due))

    for conv in due:
        # Stop if we got banned mid-loop
        if client.is_banned:
            logger.info("Stopping conversation checks — banned")
            break

        conv.last_checked_at = __import__("time").time()

        # Skip conversations with non-UUID post IDs (synthetic fallbacks)
        if not _is_uuid(conv.post_id):
            continue

        # Fetch current comments on the post
        try:
            comments = await client.get_comments(conv.post_id)
        except Exception:
            logger.warning("Failed to fetch comments for %s", conv.post_id)
            continue

        # Ingest all comments we haven't seen
        for c in comments:
            conv.add_message(ConversationMessage(
                id=c.id,
                author=c.author,
                content=c.content,
                parent_id=c.parent_id,
            ))

        # Find new replies to our comments
        new_replies = conv.find_new_replies_to_us(comments)
        if not new_replies:
            continue

        # Process one reply per conversation per cycle (avoid flooding)
        reply_to = new_replies[0]
        logger.info(
            "New reply from %s in thread %s: %s",
            reply_to.author,
            conv.post_id[:12],
            reply_to.content[:60],
        )

        # Record in learning journal
        memory.learning.record_reply_received(
            from_author=reply_to.author,
            post_id=conv.post_id,
            topic_hint=conv.post_title[:40],
        )

        # Controller checks loop detection
        if not controller.validate_reply(conv):
            conv.add_message(ConversationMessage(
                id=reply_to.id,
                author=reply_to.author,
                content=reply_to.content,
                parent_id=reply_to.parent_id,
            ))
            continue

        # Ask brain whether to reply
        profile = memory.learning.get_profile(reply_to.author)
        profile_summary = ""
        if profile:
            profile_summary = profile.rich_summary()

        thread_context = conv.build_thread_context(focus_reply=reply_to)
        reply_decision = await brain.reply_to_thread(
            thread_context=thread_context,
            reply_author=reply_to.author,
            reply_content=reply_to.content,
            bot_profile_summary=profile_summary,
            learning_insights=memory.learning.recent_insights(),
            mission_context=mission_context,
            strategy_context=strategy_context,
        )

        if reply_decision is None:
            logger.warning("Brain returned no reply decision (parse failure)")
            continue

        if reply_decision.action == "PASS":
            logger.info(
                "Passing on reply in %s: %s",
                conv.post_id[:12],
                reply_decision.reasoning[:60],
            )
            # Mark the reply as seen
            conv.add_message(ConversationMessage(
                id=reply_to.id,
                author=reply_to.author,
                content=reply_to.content,
                parent_id=reply_to.parent_id,
            ))
            continue

        # Post the reply
        assert reply_decision.reply_text is not None
        try:
            result = await client.create_comment(
                post_id=conv.post_id,
                content=reply_decision.reply_text,
                parent_id=reply_to.id,
            )

            if result.needs_verification:
                logger.info(
                    "Verification required for reply: %s",
                    result.verification.challenge_text[:80],
                )
                answer = solve_challenge(result.verification.challenge_text)
                if answer is None:
                    logger.error(
                        "Cannot solve challenge — skipping to avoid ban strike"
                    )
                    continue
                verify_resp = await client.submit_verification(
                    verification_code=result.verification.verification_code,
                    answer=answer,
                )
                if verify_resp.get("success"):
                    logger.info("Verification passed for reply")
                else:
                    logger.error("Verification FAILED for reply: %s", verify_resp)
                    continue  # skip tracking this failed reply

            conv.record_our_reply(result.id or reply_to.id)
            conv.add_message(ConversationMessage(
                id=result.id or f"reply-{reply_to.id}",
                author=settings.agent_name,
                content=reply_decision.reply_text,
                parent_id=reply_to.id,
            ))
            controller.record_reply()
            replies_sent += 1

            # Record in learning
            memory.learning.record_interaction(
                post_id=conv.post_id,
                action="REPLY",
                our_text=reply_decision.reply_text,
                target_author=reply_to.author,
                topic_hint=conv.post_title[:40],
            )

            logger.info(
                "Replied to %s in thread %s (depth: %d)",
                reply_to.author,
                conv.post_id[:12],
                conv.depth,
            )
        except httpx.HTTPStatusError as e:
            logger.error(
                "Reply in %s rejected — HTTP %d: %s",
                conv.post_id,
                e.response.status_code,
                e.response.text[:300],
            )
        except Exception:
            logger.exception("Failed to post reply in %s", conv.post_id)

    memory.save()
    return replies_sent


# ---------------------------------------------------------------------------
# Phase 2: Main decision cycle (feed → decide → act)
# ---------------------------------------------------------------------------


async def run_cycle(
    client: MoltbookClient,
    brain: Brain,
    controller: Controller,
    memory: Memory,
    settings: Settings | None = None,
    missions: MissionManager | None = None,
    strategy: StrategyEngine | None = None,
    experiments: ExperimentLog | None = None,
) -> None:
    """Execute one full cycle: check conversations, then feed decision."""
    mission_context = missions.mission_context_for_prompt() if missions else ""
    strategy_context = strategy.summary_for_prompt() if strategy else ""

    # Phase 1: Check active conversations for replies
    if settings:
        await check_conversations(
            client, brain, controller, memory, settings,
            mission_context=mission_context,
            strategy_context=strategy_context,
        )

    # Check ban status before making API calls (may have been set during conversations)
    if client.is_banned:
        remaining = client.ban_remaining_seconds()
        logger.info(
            "Skipping cycle — banned for %ds (reason: %s)",
            int(remaining),
            client.ban_reason,
        )
        return

    # Phase 2: Fetch feed and make a decision
    try:
        feed_limit = settings.feed_limit if settings else 15
        posts = await client.get_feed(limit=feed_limit)
    except Exception:
        logger.exception("Failed to fetch feed")
        return

    if not posts:
        logger.info("Empty feed, skipping cycle")
        return

    can_post = controller.can_post()
    decision = await brain.decide(
        posts,
        can_post=can_post,
        learning_insights=memory.learning.recent_insights(),
        conversations_summary=memory.conversations.summary_text(),
        mission_context=mission_context,
        strategy_context=strategy_context,
    )
    if decision is None:
        logger.warning("Brain returned no decision (parse failure), skipping cycle")
        return

    approved = controller.validate(decision)

    if decision.action == "OBSERVE" or not approved:
        memory.record_decision(decision)
        post_ids = [p.id for p in posts if not memory.has_responded_to(p.id)]
        memory.record_ignored(post_ids)
        if experiments:
            experiments.record_cycle("OBSERVE")
        return

    success = False
    if decision.action == "RESPOND":
        success = await _handle_respond(client, controller, memory, decision, posts)
    elif decision.action == "POST":
        success = await _handle_post(client, controller, memory, decision, settings)

    if success:
        memory.record_decision(decision)
        # Record progress on mission
        if missions:
            detail = ""
            if decision.action == "RESPOND":
                detail = f"Commented: {(decision.response_text or '')[:60]}"
            elif decision.action == "POST":
                detail = f"Posted: {(decision.post_title or '')[:60]}"
            missions.record_action(decision.action, detail)
        # Record in experiment
        if experiments:
            experiments.record_cycle(decision.action)
    else:
        # Record as OBSERVE so we don't inflate metrics, but still log it
        logger.info("Action failed — recording as observation")
        decision_as_observe = Decision(
            action="OBSERVE",
            post_id=decision.post_id,
            confidence=decision.confidence,
            reasoning=f"FAILED {decision.action}: {decision.reasoning[:80]}",
            response_text=None,
            post_title=None,
            post_content=None,
            post_submolt=None,
        )
        memory.record_decision(decision_as_observe)


async def _handle_respond(
    client: MoltbookClient,
    controller: Controller,
    memory: Memory,
    decision: "Decision",
    posts: list,
) -> bool:
    """Post a comment and start tracking the conversation.

    Returns True if the comment was posted successfully.
    """
    assert decision.post_id is not None
    assert decision.response_text is not None

    if not _is_uuid(decision.post_id):
        logger.warning(
            "Brain returned non-UUID post_id: %s — skipping comment",
            decision.post_id,
        )
        return False

    try:
        result = await client.create_comment(
            post_id=decision.post_id,
            content=decision.response_text,
        )

        if result.needs_verification:
            logger.info(
                "Verification required for comment on %s: %s",
                decision.post_id,
                result.verification.challenge_text[:80],
            )
            answer = solve_challenge(result.verification.challenge_text)
            if answer is None:
                logger.error(
                    "Cannot solve challenge for comment on %s — skipping to avoid ban strike",
                    decision.post_id,
                )
                return False
            verify_resp = await client.submit_verification(
                verification_code=result.verification.verification_code,
                answer=answer,
            )
            if verify_resp.get("success"):
                logger.info("Verification passed for comment on %s", decision.post_id)
            else:
                logger.error(
                    "Verification FAILED for comment on %s: %s",
                    decision.post_id,
                    verify_resp,
                )
                return False

        controller.record_response()

        # Start tracking this conversation
        post_obj = next((p for p in posts if p.id == decision.post_id), None)
        conv = memory.conversations.start_or_get(
            post_id=decision.post_id,
            post_title=post_obj.title if post_obj else "",
            post_author=post_obj.author if post_obj else "",
        )
        # Add the original post as context
        if post_obj:
            conv.add_message(ConversationMessage(
                id=post_obj.id,
                author=post_obj.author,
                content=f"{post_obj.title}\n{post_obj.content}",
            ))
        # Add our comment
        conv.record_our_reply(result.id or decision.post_id)
        conv.add_message(ConversationMessage(
            id=result.id or f"our-{decision.post_id}",
            author=memory.conversations._our_name,
            content=decision.response_text,
            parent_id=decision.post_id,
        ))

        # Record in learning
        target_author = post_obj.author if post_obj else ""
        memory.learning.record_interaction(
            post_id=decision.post_id,
            action="RESPOND",
            our_text=decision.response_text,
            target_author=target_author,
            topic_hint=post_obj.title[:40] if post_obj else "",
        )

        logger.info(
            "Posted comment on %s (confidence: %d)",
            decision.post_id,
            decision.confidence,
        )
        return True
    except httpx.HTTPStatusError as e:
        logger.error(
            "Comment on %s rejected — HTTP %d: %s",
            decision.post_id,
            e.response.status_code,
            e.response.text[:300],
        )
        return False
    except Exception:
        logger.exception("Failed to post comment on %s", decision.post_id)
        return False


async def _handle_post(
    client: MoltbookClient,
    controller: Controller,
    memory: Memory,
    decision: "Decision",
    settings: Settings | None = None,
) -> bool:
    """Create an original post and start tracking it for replies.

    Returns True if the post was created successfully.
    """
    assert decision.post_title is not None
    assert decision.post_content is not None
    assert decision.post_submolt is not None

    agent_name = settings.agent_name if settings else "Velorum"

    try:
        result = await client.create_post(
            submolt=decision.post_submolt,
            title=decision.post_title,
            content=decision.post_content,
        )

        if result.needs_verification:
            logger.info(
                "Verification required for post: %s",
                result.verification.challenge_text[:80],
            )
            answer = solve_challenge(result.verification.challenge_text)
            if answer is None:
                logger.error(
                    "Cannot solve challenge for post — skipping to avoid ban strike"
                )
                return False
            verify_resp = await client.submit_verification(
                verification_code=result.verification.verification_code,
                answer=answer,
            )
            if verify_resp.get("success"):
                logger.info("Verification passed for post")
            else:
                logger.error("Verification FAILED for post: %s", verify_resp)
                return False

        controller.record_post()
        memory.record_post(title=decision.post_title, post_id=result.id)

        # Track our own post as a conversation so we can reply to comments
        post_id = result.id
        if not post_id or not _is_uuid(post_id):
            logger.info(
                "Post created but no valid UUID returned — skipping conversation tracking"
            )
            # Still record in learning with a placeholder
            memory.learning.record_interaction(
                post_id=post_id or "unknown",
                action="POST",
                our_text=f"{decision.post_title}: {decision.post_content[:80]}",
                topic_hint=decision.post_title[:40],
            )
            logger.info(
                "Created post in %s: \"%s\" (confidence: %d)",
                decision.post_submolt,
                decision.post_title[:60],
                decision.confidence,
            )
            return True

        conv = memory.conversations.start_or_get(
            post_id=post_id,
            post_title=decision.post_title,
            post_author=agent_name,
        )
        conv.add_message(ConversationMessage(
            id=post_id,
            author=agent_name,
            content=f"{decision.post_title}\n{decision.post_content}",
        ))
        # Mark it as "ours" so replies to the post itself are detected
        conv.our_comment_ids.append(post_id)

        # Record in learning
        memory.learning.record_interaction(
            post_id=post_id,
            action="POST",
            our_text=f"{decision.post_title}: {decision.post_content[:80]}",
            topic_hint=decision.post_title[:40],
        )

        logger.info(
            "Created post in %s: \"%s\" (confidence: %d)",
            decision.post_submolt,
            decision.post_title[:60],
            decision.confidence,
        )
        return True
    except httpx.HTTPStatusError as e:
        logger.error(
            "Post \"%s\" rejected — HTTP %d: %s",
            decision.post_title[:60],
            e.response.status_code,
            e.response.text[:300],
        )
        return False
    except Exception:
        logger.exception(
            "Failed to create post: \"%s\"", decision.post_title[:60]
        )
        return False


# ---------------------------------------------------------------------------
# Phase 3: Engagement check (runs periodically)
# ---------------------------------------------------------------------------


async def check_engagement(
    client: MoltbookClient,
    memory: Memory,
) -> None:
    """Check engagement on our recent interactions (upvotes, reply counts)."""
    if client.is_banned:
        return

    unchecked = memory.learning.unchecked_interactions(max_age=7200)
    if not unchecked:
        return

    logger.info("Checking engagement on %d recent interaction(s)", len(unchecked))

    for interaction in unchecked[:5]:  # check up to 5 per cycle
        if not _is_uuid(interaction.post_id):
            interaction.checked = True  # mark so we don't retry
            continue
        try:
            comments = await client.get_comments(interaction.post_id)
            # Count replies to our content
            reply_count = sum(
                1 for c in comments
                if c.author.lower() != memory.conversations._our_name.lower()
            )
            memory.learning.record_engagement_check(
                post_id=interaction.post_id,
                reply_count=reply_count,
            )
        except Exception:
            logger.debug("Could not check engagement for %s", interaction.post_id)

    memory.save()


# ---------------------------------------------------------------------------
# Phase 4: Bot profiling (runs periodically)
# ---------------------------------------------------------------------------


async def profile_bots(
    client: MoltbookClient,
    brain: Brain,
    memory: Memory,
) -> None:
    """Profile bots that have enough interactions but haven't been analyzed."""
    if client.is_banned:
        return

    needs_profiling = memory.learning.bots_needing_profiling()
    if not needs_profiling:
        return

    logger.info("Profiling %d bot(s)", min(2, len(needs_profiling)))

    for profile in needs_profiling[:2]:  # profile up to 2 per cycle
        # Build interaction history from our interactions with this bot
        history_lines = []
        for interaction in memory.learning._interactions:
            if interaction.target_author.lower() == profile.name.lower():
                history_lines.append(
                    f"[{interaction.action}] We said: \"{interaction.our_text[:80]}\" "
                    f"(topic: {interaction.topic_hint}, replies: {interaction.reply_count})"
                )
        interaction_history = "\n".join(history_lines[-15:]) or "No direct interactions recorded."

        # Build existing profile summary
        existing = ""
        if profile.personality_summary:
            existing = (
                f"Previous assessment: {profile.personality_summary}\n"
                f"Interests: {', '.join(profile.interests)}\n"
                f"Style: {profile.communication_style}"
            )

        result = await brain.profile_bot(
            bot_name=profile.name,
            interaction_history=interaction_history,
            existing_profile=existing,
        )

        if result:
            profile.apply_profiling(result)
            logger.info(
                "Profiled %s: %s (confidence: %s)",
                profile.name,
                profile.personality_summary[:60],
                profile.profile_confidence,
            )

    memory.save()


# ---------------------------------------------------------------------------
# Data refresh — reconcile local memory with server state
# ---------------------------------------------------------------------------


async def refresh_data(
    client: MoltbookClient,
    memory: Memory,
) -> None:
    """Rebuild learning data from decision history and server.

    This reconciles stale local state by:
    1. Rebuilding interactions from recorded decisions
    2. Fetching actual comment data from the server for known posts
    3. Updating bot profiles from comment authors
    """
    if client.is_banned:
        logger.warning("Cannot refresh data while banned")
        return

    logger.info("Starting data refresh...")
    journal = memory.learning

    # Step 1: Rebuild interactions from decisions that aren't already tracked
    tracked_posts = {i.post_id for i in journal._interactions}
    rebuilt = 0

    for d in memory._decisions:
        post_id = d.get("post_id", "")
        action = d.get("action", "")
        if action not in ("RESPOND", "POST"):
            continue
        if post_id in tracked_posts:
            continue

        our_text = d.get("response_text", "") or ""
        if action == "POST":
            our_text = f"{d.get('post_title', '')}: {d.get('post_content', '')[:80]}"

        journal.record_interaction(
            post_id=post_id,
            action=action,
            our_text=our_text[:100],
            topic_hint=d.get("post_title", "")[:40] if action == "POST" else "",
        )
        rebuilt += 1

    logger.info("Rebuilt %d interactions from decision history", rebuilt)

    # Step 2: Fetch comment data from server for recent posts we interacted with
    # to discover bot profiles and engagement data
    checked = 0
    for interaction in journal._interactions:
        if not interaction.post_id or not _is_uuid(interaction.post_id):
            continue
        try:
            comments = await client.get_comments(interaction.post_id)
            if not comments:
                continue

            # Count replies and discover bots
            our_name = memory.conversations._our_name.lower()
            reply_count = 0
            for c in comments:
                author = c.author
                if author.lower() == our_name:
                    continue
                reply_count += 1
                # Record this bot if we haven't
                profile = journal._get_or_create_profile(author)
                if profile.interaction_count == 0:
                    profile.record_interaction(
                        topic=interaction.topic_hint,
                        they_replied=True,
                    )

            interaction.reply_count = max(interaction.reply_count, reply_count)
            interaction.checked = True
            checked += 1

        except Exception:
            logger.debug("Could not fetch comments for %s", interaction.post_id)

        # Rate limit ourselves
        if checked >= 10:
            break

    logger.info(
        "Refreshed engagement data for %d posts, now know %d bots",
        checked,
        len(journal._bot_profiles),
    )
    memory.save()
    logger.info("Data refresh complete")


# ---------------------------------------------------------------------------
# Entry points
# ---------------------------------------------------------------------------


async def main() -> None:
    """Headless main loop (original behavior)."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    settings = load_settings()
    client, brain, controller, memory, missions, strategy, experiments = init_components(settings)

    logger.info("Velorum starting — provider=%s, model=%s", settings.llm_provider, settings.llm_model)

    # Check agent status at startup
    try:
        status_data = await client.check_status()
        if status_data:
            logger.info("Moltbook agent status: %s", status_data.get("status", "unknown"))
        else:
            logger.warning("Could not verify agent status with Moltbook")
    except Exception:
        logger.warning("Moltbook status check failed at startup")

    # Refresh stale data from server
    if not client.is_banned:
        await refresh_data(client, memory)

    # Plan mission if one is set but not yet planned
    if missions.active_mission and missions.active_mission.status == "planning":
        logger.info("Planning mission: %s", missions.active_mission.prompt[:60])
        plan = await brain.plan_mission(
            mission_prompt=missions.active_mission.prompt,
            bot_relationships=memory.learning.bot_relationships_summary(),
            engagement_summary=memory.learning.engagement_summary(),
        )
        if plan:
            missions.apply_plan(plan)

    cycle = 0
    try:
        while True:
            # Ban watch — sleep until ban expires
            if client.is_banned:
                remaining = client.ban_remaining_seconds()
                logger.warning(
                    "Agent is banned for %ds (reason: %s) — sleeping until ban expires",
                    int(remaining),
                    client.ban_reason,
                )
                # Sleep in chunks so we can respond to Ctrl+C
                while client.is_banned:
                    await asyncio.sleep(min(60, client.ban_remaining_seconds() + 1))
                # Verify with server before resuming
                logger.info("Ban timer expired — verifying with server...")
                still_banned = await client.force_check_ban()
                if still_banned:
                    logger.warning("Server says still banned — continuing to wait")
                    continue
                logger.info("Ban confirmed expired — resuming normal operation")

            cycle += 1
            logger.info("=== Cycle %d ===", cycle)

            await run_cycle(client, brain, controller, memory, settings, missions, strategy, experiments)

            # Engagement check every 3rd cycle
            if cycle % settings.engagement_check_interval_cycles == 0:
                await check_engagement(client, memory)

            # Bot profiling
            if cycle % settings.profiling_interval_cycles == 0:
                await profile_bots(client, brain, memory)

            # Mission review
            if (
                missions.active_mission
                and missions.active_mission.status == "active"
                and cycle % settings.mission_review_interval_cycles == 0
            ):
                logger.info("Reviewing mission progress...")
                review = await brain.review_mission(
                    mission=missions.active_mission.to_dict(),
                    recent_actions=memory.recent_decisions_text(),
                    engagement_summary=memory.learning.engagement_summary(),
                    bot_relationships=memory.learning.bot_relationships_summary(),
                )
                if review:
                    missions.apply_review(review)
                    logger.info("Mission review: %s", review.get("progress_assessment", "")[:100])

            # Reflection
            if cycle % settings.reflection_interval_cycles == 0:
                logger.info("Running reflection...")
                mission_ctx = missions.mission_context_for_prompt()
                strategy_ctx = strategy.summary_for_prompt()
                reflection = await brain.reflect(
                    engagement_summary=memory.learning.engagement_summary(),
                    bot_relationships=memory.learning.bot_relationships_summary(),
                    conversations_summary=memory.conversations.summary_text(),
                    mission_context=mission_ctx,
                    strategy_context=strategy_ctx,
                )
                if reflection:
                    logger.info("Reflection: %s", reflection.behavior_assessment[:200])
                    logger.info("Recommendation: %s", reflection.adjustment_recommendation[:200])
                    if reflection.engagement_insight:
                        memory.learning.add_insight(
                            reflection.engagement_insight,
                            source=f"reflection_cycle_{cycle}",
                        )
                        memory.save()

            # Strategy update (less frequent)
            if cycle % settings.strategy_update_interval_cycles == 0:
                logger.info("Updating strategy...")
                mission_ctx = missions.mission_context_for_prompt()
                result = await brain.update_strategy(
                    current_strategy=strategy.summary_for_prompt(),
                    engagement_data=memory.learning.engagement_summary(),
                    bot_profiles=memory.learning.bot_relationships_summary(),
                    insights=memory.learning.recent_insights(),
                    mission_context=mission_ctx,
                )
                if result:
                    strategy.apply_update(result)
                    logger.info("Strategy updated: %s", result.get("assessment", "")[:100])

            await asyncio.sleep(settings.cycle_interval_seconds)
    except KeyboardInterrupt:
        logger.info("Shutting down...")
    finally:
        await client.close()


def entry() -> None:
    if len(sys.argv) > 1 and sys.argv[1] == "setup":
        from velorum.setup import run_setup

        run_setup()
    elif len(sys.argv) > 1 and sys.argv[1] == "--headless":
        asyncio.run(main())
    else:
        from velorum.tui.app import VelorumApp

        logging.getLogger().setLevel(logging.INFO)
        settings = load_settings()
        client, brain, controller, memory, missions, strategy, experiments = init_components(settings)

        app = VelorumApp(
            settings=settings,
            client=client,
            brain=brain,
            controller=controller,
            memory=memory,
            missions=missions,
            strategy=strategy,
            experiments=experiments,
        )
        app.run()


if __name__ == "__main__":
    entry()
