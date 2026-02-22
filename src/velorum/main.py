"""Entry point — main async run loop."""

from __future__ import annotations

import asyncio
import logging
import random
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
from velorum.components import Components
from velorum.config import Settings, load_settings
from velorum.context import PromptContext, build_context
from velorum.controller import Controller
from velorum.conversations import ConversationMessage
from velorum.dm import DMMessage
from velorum.experiment import ExperimentLog
from velorum.following import FollowingTracker
from velorum.learning import infer_style_tags
from velorum.llm.base import LLMProvider
from velorum.memory import Memory
from velorum.mission import MissionManager
from velorum.moltbook.client import MoltbookClient
from velorum.moltbook.models import Comment, Decision, Post
from velorum.moltbook.verification import solve_challenge
from velorum.personality import PersonalityEngine
from velorum.strategy import StrategyEngine
from velorum.submolts import SubmoltManager

logger = logging.getLogger(__name__)


def init_components(settings: Settings) -> Components:
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
    submolts = SubmoltManager(persist_path=settings.submolts_file)
    personality = PersonalityEngine(persist_path=settings.personality_file)
    following = FollowingTracker(persist_path=settings.following_file)

    # Agent Arena (optional)
    arena_client = None
    arena_rooms = None
    if settings.arena_enabled and settings.arena_api_key:
        from velorum.arena.client import AgentArenaClient
        from velorum.arena.rooms import ArenaRoomTracker

        arena_client = AgentArenaClient(
            base_url=settings.arena_base_url,
            api_key=settings.arena_api_key,
            timeout=settings.http_timeout_seconds,
        )
        arena_rooms = ArenaRoomTracker()
        logger.info("Agent Arena enabled")

    return Components(
        client=client,
        brain=brain,
        controller=controller,
        memory=memory,
        missions=missions,
        strategy=strategy,
        experiments=experiments,
        submolts=submolts,
        personality=personality,
        following=following,
        arena_client=arena_client,
        arena_rooms=arena_rooms,
    )


# ---------------------------------------------------------------------------
# Submolt discovery + subscription
# ---------------------------------------------------------------------------


async def discover_submolts(
    client: MoltbookClient,
    submolts: SubmoltManager,
    settings: Settings,
) -> None:
    """Discover popular submolts and subscribe to top ones."""
    if client.is_banned:
        return

    try:
        raw = await client.get_submolts(sort="popular", limit=50)
        if not raw:
            logger.info("No submolts returned from API")
            return

        submolts.update_discovered(raw)
        logger.info("Discovered %d submolts", len(raw))

        # Subscribe to top N we aren't already in
        subscribed_count = 0
        for s in raw:
            name = s.get("name", "")
            if not name:
                continue
            if name in submolts.subscribed:
                continue
            if len(submolts.subscribed) >= settings.max_subscribed_submolts:
                break
            try:
                await client.subscribe_submolt(name)
                submolts.record_subscription(name)
                subscribed_count += 1
                logger.info("Subscribed to submolt: %s", name)
            except Exception:
                logger.debug("Could not subscribe to %s", name)

        if subscribed_count:
            logger.info("Subscribed to %d new submolt(s)", subscribed_count)

        submolts.save()
    except Exception:
        logger.exception("Submolt discovery failed")


# ---------------------------------------------------------------------------
# Phase 1: Check active conversations for new replies
# ---------------------------------------------------------------------------


async def check_conversations(
    client: MoltbookClient,
    brain: Brain,
    controller: Controller,
    memory: Memory,
    settings: Settings,
    ctx: PromptContext | None = None,
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
        limit=settings.max_conversation_checks_per_cycle,
    )

    if not due:
        return 0

    logger.info("Checking %d active conversation(s) for replies", len(due))

    for i, conv in enumerate(due):
        # Stop if we got banned mid-loop
        if client.is_banned:
            logger.info("Stopping conversation checks — banned")
            break

        # Brief pause between conversations to avoid API burst
        if i > 0:
            await asyncio.sleep(1.0)

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

        # Process ALL new replies in this conversation
        for reply_to in new_replies:
            # Stop if we got banned mid-loop
            if client.is_banned:
                logger.info("Stopping reply processing — banned")
                break

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
                break  # Rate-limited — stop processing this conversation

            # Ask brain whether to reply
            profile = memory.learning.get_profile(reply_to.author)
            profile_summary = ""
            if profile:
                profile_summary = profile.rich_summary()

            thread_context = conv.build_thread_context(focus_reply=reply_to)
            reply_kwargs = ctx.for_reply() if ctx else {}
            reply_decision = await brain.reply_to_thread(
                thread_context=thread_context,
                reply_author=reply_to.author,
                reply_content=reply_to.content,
                bot_profile_summary=profile_summary,
                **reply_kwargs,
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
                    style_tags=infer_style_tags(reply_decision.reply_text, "REPLY"),
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
# Phase 1.5: Check DMs for new messages and requests
# ---------------------------------------------------------------------------


async def check_dms(
    client: MoltbookClient,
    brain: Brain,
    memory: Memory,
    settings: Settings,
    ctx: PromptContext | None = None,
) -> None:
    """Check DMs for pending requests and new messages."""
    if client.is_banned:
        return

    dm_mgr = memory.dms

    # 1. Check for pending requests
    try:
        dm_status = await client.dm_check()
    except Exception:
        logger.debug("DM check failed")
        return

    # 2. Handle incoming requests (up to 3 per cycle)
    pending_requests = dm_status.get("pending_requests", 0)
    if pending_requests > 0:
        try:
            requests = await client.dm_get_requests()
            for req in requests[:3]:
                req_id = req.get("id", "")
                from_name = req.get("from", req.get("from_agent", ""))
                message = req.get("message", "")
                if not req_id or not from_name:
                    continue

                # Get bot profile for context
                profile = memory.learning.get_profile(from_name)
                profile_summary = profile.rich_summary() if profile else ""

                ctx_kwargs = {}
                if ctx:
                    ctx_kwargs = {
                        "mission_context": ctx.mission_context,
                        "strategy_context": ctx.strategy_context,
                    }

                decision = await brain.decide_dm_request(
                    requester_name=from_name,
                    request_message=message,
                    bot_profile_summary=profile_summary,
                    **ctx_kwargs,
                )

                if decision is None:
                    logger.warning("Brain returned no DM request decision")
                    continue

                if decision.action == "APPROVE":
                    try:
                        result = await client.dm_approve_request(req_id)
                        conv_id = result.get("conversation_id", req_id)
                        dm_mgr.start_conversation(conv_id, from_name, initiated_by_us=False)
                        logger.info("Approved DM request from %s: %s", from_name, decision.reasoning[:60])
                    except Exception:
                        logger.warning("Failed to approve DM request from %s", from_name)
                else:
                    try:
                        await client.dm_reject_request(req_id)
                        dm_mgr.record_rejection(from_name)
                        logger.info("Rejected DM request from %s: %s", from_name, decision.reasoning[:60])
                    except Exception:
                        logger.warning("Failed to reject DM request from %s", from_name)

        except Exception:
            logger.debug("Failed to fetch DM requests")

    # 3. Check active DM conversations for new messages
    due = dm_mgr.conversations_needing_check(
        check_interval=settings.dm_check_interval,
        limit=3,
    )

    for conv in due:
        if client.is_banned:
            break

        conv.last_checked_at = __import__("time").time()

        try:
            messages_data = await client.dm_get_messages(conv.conversation_id)
        except Exception:
            logger.debug("Failed to fetch DM messages for %s", conv.conversation_id)
            continue

        # Ingest new messages
        new_from_them = []
        our_name_lower = memory.conversations._our_name.lower()
        for msg_data in messages_data:
            msg = DMMessage(
                id=msg_data.get("id", ""),
                author=msg_data.get("author", msg_data.get("from", "")),
                content=msg_data.get("content", msg_data.get("message", "")),
                timestamp=msg_data.get("timestamp", 0.0),
                needs_human_input=msg_data.get("needs_human_input", False),
            )
            if not msg.id:
                continue
            is_new = conv.add_message(msg)
            if is_new and msg.author.lower() != our_name_lower:
                conv.their_message_count += 1
                new_from_them.append(msg)

        if not new_from_them:
            continue

        # Reply to the latest message from them
        latest = new_from_them[-1]
        logger.info("New DM from %s: %s", latest.author, latest.content[:60])

        profile = memory.learning.get_profile(latest.author)
        profile_summary = profile.rich_summary() if profile else ""

        thread_context = conv.build_thread_context()
        dm_reply_kwargs = ctx.for_dm_reply() if ctx else {}
        reply_decision = await brain.reply_to_dm(
            thread_context=thread_context,
            latest_message_author=latest.author,
            latest_message_content=latest.content,
            bot_profile_summary=profile_summary,
            **dm_reply_kwargs,
        )

        if reply_decision is None:
            logger.warning("Brain returned no DM reply decision")
            continue

        if reply_decision.action == "PASS":
            logger.info("Passing on DM reply to %s: %s", latest.author, reply_decision.reasoning[:60])
            continue

        if reply_decision.reply_text:
            try:
                result = await client.dm_send_message(
                    conv.conversation_id, reply_decision.reply_text,
                )
                msg_id = result.get("id", f"dm-reply-{latest.id}")
                conv.record_our_message(msg_id)
                conv.add_message(DMMessage(
                    id=msg_id,
                    author=settings.agent_name,
                    content=reply_decision.reply_text,
                ))
                logger.info("Replied to DM from %s (conv: %s)", latest.author, conv.conversation_id[:12])
            except Exception:
                logger.warning("Failed to send DM reply to %s", latest.author)

    memory.save()


# ---------------------------------------------------------------------------
# Comment scanning — fetch notable comments from top posts
# ---------------------------------------------------------------------------


async def _fetch_notable_comments(
    client: MoltbookClient,
    posts: list,
    memory: Memory,
    max_posts: int = 3,
) -> dict[str, list[Comment]]:
    """Fetch comments from the most-discussed posts for the decision prompt.

    Filters out our own posts and posts with no comments.
    Returns ALL comments per post (excluding ours) for full context.
    """
    our_name = memory.conversations._our_name.lower()

    candidates = [
        p for p in posts
        if p.comment_count >= 1
        and p.author.lower() != our_name
        and _is_uuid(p.id)
    ]
    candidates.sort(key=lambda p: p.comment_count, reverse=True)

    result: dict[str, list[Comment]] = {}
    for post in candidates[:max_posts]:
        try:
            comments = await client.get_comments(post.id)
            # Filter out our own comments — return ALL others
            others = [
                c for c in comments
                if c.author.lower() != our_name
            ]
            if others:
                result[post.id] = others
        except Exception:
            logger.debug("Could not fetch comments for %s", post.id[:12])

    return result


# ---------------------------------------------------------------------------
# Upvote side-effect
# ---------------------------------------------------------------------------


def _random_upvote_count(max_upvotes: int) -> int:
    """Weighted random upvote count for organic behavior.

    Distribution: 40% → 0, 30% → 1, 20% → 2, 10% → 3.
    Clamped to max_upvotes.
    """
    weights = [40, 30, 20, 10]
    choices = list(range(len(weights)))
    pick = random.choices(choices, weights=weights[:len(choices)], k=1)[0]
    return min(pick, max_upvotes)


async def _handle_upvotes(
    client: MoltbookClient,
    memory: Memory,
    decision: Decision,
    posts: list[Post],
    post_comments: dict[str, list[Comment]] | None,
    max_upvotes: int = 2,
) -> None:
    """Execute upvotes as a side-effect, skipping already-upvoted IDs."""
    if not decision.upvote_ids:
        return

    # Build lookup maps for logging context
    post_map: dict[str, Post] = {p.id: p for p in posts}
    comment_map: dict[str, Comment] = {}
    if post_comments:
        for comments in post_comments.values():
            for c in comments:
                comment_map[c.id] = c

    count = 0
    for item_id in decision.upvote_ids:
        if count >= max_upvotes:
            break
        if memory.has_upvoted(item_id):
            continue
        if not _is_uuid(item_id):
            continue

        try:
            if item_id in post_map:
                await client.upvote_post(item_id)
                post = post_map[item_id]
                logger.info(
                    "Upvoted post by @%s: \"%s\" (%s)",
                    post.author, post.title[:50], post.submolt,
                )
            elif item_id in comment_map:
                await client.upvote_comment(item_id)
                comment = comment_map[item_id]
                logger.info(
                    "Upvoted comment by @%s: \"%s\"",
                    comment.author, comment.content[:60],
                )
            else:
                continue  # hallucinated ID
            memory.record_upvote(item_id)
            count += 1
        except Exception:
            logger.debug("Upvote failed for %s", item_id[:12])


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
    submolts: SubmoltManager | None = None,
    personality: PersonalityEngine | None = None,
) -> None:
    """Execute one full cycle: check conversations, then feed decision."""
    conversations_on = bool(settings and settings.conversations_enabled)
    dms_on = bool(settings and settings.dms_enabled)

    ctx = build_context(
        memory,
        missions=missions,
        strategy=strategy,
        personality=personality,
        submolts=submolts,
        conversations_enabled=conversations_on,
        dms_enabled=dms_on,
    )

    # Phase 1: Check active conversations for replies (gated)
    if settings and settings.conversations_enabled:
        await check_conversations(
            client, brain, controller, memory, settings, ctx=ctx,
        )

    # Phase 1.5: Check DMs (gated)
    if settings and settings.dms_enabled:
        await check_dms(client, brain, memory, settings, ctx=ctx)

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

    # Fetch comments from notable posts for comment engagement
    scan_limit = settings.comment_scan_limit if settings else 3
    post_comments: dict[str, list[Comment]] = {}
    if scan_limit > 0:
        try:
            post_comments = await _fetch_notable_comments(
                client, posts, memory, max_posts=scan_limit,
            )
            if post_comments:
                total = sum(len(v) for v in post_comments.values())
                logger.info(
                    "Scanned comments: %d comments across %d posts",
                    total, len(post_comments),
                )
        except Exception:
            logger.debug("Comment scanning failed")

    # Rebuild context with feed_authors for bot targeting
    feed_authors = {p.author for p in posts}
    ctx = build_context(
        memory,
        missions=missions,
        strategy=strategy,
        personality=personality,
        submolts=submolts,
        feed_authors=feed_authors,
        conversations_enabled=conversations_on,
        dms_enabled=dms_on,
    )

    can_post = controller.can_post()

    # Web search enrichment (optional, for post context)
    if (
        settings
        and settings.web_search_enabled
        and settings.tavily_api_key
        and can_post
    ):
        try:
            from velorum.search import TavilySearch, format_search_results

            # Derive search query from mission context
            search_query = ctx.mission_context.strip().split("\n")[0][:80] if ctx.mission_context else ""
            if not search_query:
                search_query = "AI agents autonomous systems trends"

            logger.info("Searching web for post enrichment: %s", search_query[:60])
            tavily = TavilySearch(api_key=settings.tavily_api_key)
            results = await tavily.search(search_query, max_results=settings.max_search_results)
            web_text = format_search_results(results)
            if web_text:
                from dataclasses import replace
                ctx = replace(ctx, web_search_context=web_text)
                logger.debug("Web search returned %d results", len(results))
        except Exception:
            logger.debug("Web search failed — proceeding without search context")

    decision = await brain.decide(
        posts,
        can_post=can_post,
        post_comments=post_comments or None,
        **ctx.for_decision(),
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
        # Upvotes happen even on OBSERVE cycles
        if settings and settings.upvoting_enabled:
            upvote_count = _random_upvote_count(settings.max_upvotes_per_cycle)
            if upvote_count > 0:
                await _handle_upvotes(
                    client, memory, decision, posts, post_comments,
                    max_upvotes=upvote_count,
                )
        return

    # Validate parent_comment_id if present
    parent_comment_id = decision.parent_comment_id
    target_comment_author = ""
    if parent_comment_id:
        if not _is_uuid(parent_comment_id):
            logger.warning("Hallucinated parent_comment_id: %s — falling back to top-level", parent_comment_id)
            parent_comment_id = None
        elif post_comments:
            # Verify the comment actually exists in our fetched data
            found = False
            for comments in post_comments.values():
                for c in comments:
                    if c.id == parent_comment_id:
                        target_comment_author = c.author
                        found = True
                        break
                if found:
                    break
            if not found:
                logger.warning("parent_comment_id %s not in fetched comments — falling back to top-level", parent_comment_id[:12])
                parent_comment_id = None
        else:
            # No comments were fetched, can't validate
            parent_comment_id = None

    success = False
    if decision.action == "RESPOND":
        success = await _handle_respond(
            client, controller, memory, decision, posts,
            parent_comment_id=parent_comment_id,
            target_comment_author=target_comment_author,
            conversations_enabled=conversations_on,
        )
    elif decision.action == "POST":
        success = await _handle_post(client, controller, memory, decision, settings, conversations_enabled=conversations_on)

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

    # Upvotes as side-effect (regardless of main action success)
    if settings and settings.upvoting_enabled:
        upvote_count = _random_upvote_count(settings.max_upvotes_per_cycle)
        if upvote_count > 0:
            await _handle_upvotes(
                client, memory, decision, posts, post_comments,
                max_upvotes=upvote_count,
            )


async def _handle_respond(
    client: MoltbookClient,
    controller: Controller,
    memory: Memory,
    decision: "Decision",
    posts: list,
    parent_comment_id: str | None = None,
    target_comment_author: str = "",
    conversations_enabled: bool = False,
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
            parent_id=parent_comment_id,
        )
    except httpx.HTTPStatusError as e:
        # Retry without parent_comment_id on "Parent comment not found"
        if e.response.status_code == 404 and parent_comment_id:
            logger.warning(
                "Parent comment not found on %s — retrying as top-level comment",
                decision.post_id,
            )
            parent_comment_id = None
            target_comment_author = ""
            try:
                result = await client.create_comment(
                    post_id=decision.post_id,
                    content=decision.response_text,
                )
            except httpx.HTTPStatusError as e2:
                logger.error(
                    "Top-level comment on %s also failed — HTTP %d: %s",
                    decision.post_id, e2.response.status_code, e2.response.text[:300],
                )
                return False
        else:
            raise

    try:
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

        # Start tracking this conversation (only when conversations enabled)
        post_obj = next((p for p in posts if p.id == decision.post_id), None)
        if conversations_enabled:
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

        # Record in learning — use ENGAGE when replying to a specific comment
        action_type = "ENGAGE" if parent_comment_id else "RESPOND"
        target_author = target_comment_author or (post_obj.author if post_obj else "")
        memory.learning.record_interaction(
            post_id=decision.post_id,
            action=action_type,
            our_text=decision.response_text,
            target_author=target_author,
            topic_hint=post_obj.title[:40] if post_obj else "",
            style_tags=infer_style_tags(decision.response_text, action_type),
            submolt=post_obj.submolt if post_obj and hasattr(post_obj, "submolt") else "",
            confidence=decision.confidence,
        )

        if parent_comment_id:
            logger.info(
                "Replied to comment by %s on %s (confidence: %d)",
                target_comment_author,
                decision.post_id[:12],
                decision.confidence,
            )
        else:
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
    conversations_enabled: bool = False,
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
                style_tags=infer_style_tags(decision.post_content, "POST"),
                submolt=decision.post_submolt or "",
                confidence=decision.confidence,
            )
            logger.info(
                "Created post in %s: \"%s\" (confidence: %d)",
                decision.post_submolt,
                decision.post_title[:60],
                decision.confidence,
            )
            return True

        if conversations_enabled:
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
            style_tags=infer_style_tags(decision.post_content, "POST"),
            submolt=decision.post_submolt or "",
            confidence=decision.confidence,
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
    max_checks: int = 5,
) -> None:
    """Check engagement on our recent interactions (upvotes, reply counts)."""
    if client.is_banned:
        return

    unchecked = memory.learning.unchecked_interactions(max_age=7200)
    if not unchecked:
        return

    logger.info("Checking engagement on %d recent interaction(s)", len(unchecked))
    now = __import__("time").time()

    for interaction in unchecked[:max_checks]:
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

            # Track non-responses for ENGAGE interactions older than 30 min
            if (
                interaction.action == "ENGAGE"
                and interaction.reply_count == 0
                and reply_count == 0
                and (now - interaction.timestamp) > 1800
                and interaction.target_author
            ):
                memory.learning.record_no_response(
                    target_author=interaction.target_author,
                    post_id=interaction.post_id,
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

    for i, profile in enumerate(needs_profiling[:2]):  # profile up to 2 per cycle
        if i > 0:
            await asyncio.sleep(2.0)  # space out LLM calls
        bot_name_lower = profile.name.lower()

        # Build interaction history from our interactions with this bot
        history_lines = []
        for interaction in memory.learning._interactions:
            if interaction.target_author.lower() == bot_name_lower:
                history_lines.append(
                    f"[{interaction.action}] We said: \"{interaction.our_text[:80]}\" "
                    f"(topic: {interaction.topic_hint}, replies: {interaction.reply_count})"
                )
        interaction_history = "\n".join(history_lines[-15:]) or "No direct interactions recorded."

        # Collect their actual words from tracked conversations
        their_words: list[str] = []
        for conv in memory.conversations._conversations.values():
            for msg in conv.messages:
                if msg.author.lower() == bot_name_lower:
                    context = f"(in: {conv.post_title[:30]})" if conv.post_title else ""
                    their_words.append(f'- "{msg.content[:150]}" {context}')
        their_posts = "\n".join(their_words[-20:])

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
            their_posts=their_posts,
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
# Agent Arena loop
# ---------------------------------------------------------------------------


async def arena_loop(
    arena_client: object,
    brain: Brain,
    memory: Memory,
    arena_rooms: object,
    settings: Settings,
) -> None:
    """Agent Arena turn-polling loop. Runs concurrently with Moltbook cycles."""
    from velorum.arena.client import AgentArenaClient
    from velorum.arena.rooms import ArenaRoomTracker

    assert isinstance(arena_client, AgentArenaClient)
    assert isinstance(arena_rooms, ArenaRoomTracker)

    room_check_counter = 0
    poll_interval = settings.arena_poll_interval
    room_check_ticks = max(1, settings.arena_room_check_interval // poll_interval)

    logger.info("Arena loop started (poll: %ds, room check: %ds)", poll_interval, settings.arena_room_check_interval)

    # Authenticate at startup
    if not arena_client.is_authenticated:
        await arena_client.login()

    while True:
        try:
            # Re-authenticate if needed
            if not arena_client.is_authenticated:
                await arena_client.login()

            # 1. Check for pending turns
            turn_data = await arena_client.check_turns()
            if turn_data and turn_data.get("pending"):
                await handle_arena_turn(
                    arena_client, brain, memory, arena_rooms, settings, turn_data,
                )

            # 2. Periodically browse and join rooms
            room_check_counter += 1
            if room_check_counter >= room_check_ticks:
                room_check_counter = 0
                if settings.arena_auto_join:
                    await browse_and_join_rooms(
                        arena_client, brain, memory, arena_rooms, settings,
                    )

        except Exception:
            logger.exception("Arena loop error")

        await asyncio.sleep(poll_interval)


async def handle_arena_turn(
    arena_client: object,
    brain: Brain,
    memory: Memory,
    arena_rooms: object,
    settings: Settings,
    turn_data: dict,
) -> None:
    """Handle a pending Agent Arena turn."""
    from velorum.arena.client import AgentArenaClient
    from velorum.arena.rooms import ArenaRoomTracker

    assert isinstance(arena_client, AgentArenaClient)
    assert isinstance(arena_rooms, ArenaRoomTracker)

    turn_id = turn_data.get("turn_id", turn_data.get("id", ""))
    room_id = turn_data.get("room_id", "")
    if not turn_id:
        logger.warning("Arena turn data missing turn_id: %s", turn_data)
        return

    logger.info("Arena: pending turn %s in room %s", turn_id[:12], room_id[:12])

    # Fetch full context
    try:
        context = await arena_client.get_turn_context(turn_id)
    except Exception:
        logger.warning("Failed to fetch turn context for %s", turn_id[:12])
        return

    room_topic = context.get("topic", turn_data.get("topic", ""))
    conversation_history = context.get("conversation_history", context.get("messages", []))
    round_number = context.get("round_number", context.get("round", 0))

    # Extract other responses this round (key innovation)
    other_responses = []
    for msg in conversation_history:
        msg_round = msg.get("round", 0)
        if msg_round == round_number:
            other_responses.append(msg)

    # Update room tracker
    room = arena_rooms.get(room_id)
    if not room:
        agents = context.get("agents", [])
        room = arena_rooms.start(room_id, topic=room_topic, agents=agents)
    room.ingest_history(conversation_history)

    # Build bot profile summaries for participants
    bot_profiles_parts = []
    for agent_name in room.agents:
        profile = memory.learning.get_profile(agent_name)
        if profile and profile.personality_summary:
            bot_profiles_parts.append(f"**{agent_name}**: {profile.personality_summary[:80]}")
    bot_profiles_summary = "\n".join(bot_profiles_parts)

    # Get personality context
    personality_context = ""
    # (brain's soul covers this, but we can add strategy/mission)
    ctx = build_context(memory, arena_enabled=True)

    # Generate response
    response = await brain.respond_to_turn(
        room_topic=room_topic,
        conversation_history=conversation_history,
        other_responses=other_responses or None,
        bot_profiles_summary=bot_profiles_summary,
        personality_context=ctx.personality_context,
        mission_context=ctx.mission_context,
        strategy_context=ctx.strategy_context,
    )

    if response is None:
        logger.warning("Brain returned no turn response for %s", turn_id[:12])
        return

    # Submit response
    try:
        await arena_client.respond_to_turn(turn_id, response.response_text)
        logger.info(
            "Arena: responded in room %s (round %d): %s",
            room_id[:12], round_number, response.response_text[:60],
        )
    except Exception:
        logger.exception("Failed to submit arena turn response")
        return

    # Record in room tracker
    arena_rooms.record_response(room_id, round_number, response.response_text)

    # Record in learning journal with platform="arena"
    target_authors = [
        msg.get("author", msg.get("agent", ""))
        for msg in other_responses
        if msg.get("author", msg.get("agent", ""))
    ]
    memory.learning.record_interaction(
        post_id=f"arena-{room_id}",
        action="ARENA_RESPOND",
        our_text=response.response_text[:100],
        target_author=", ".join(target_authors[:3]),
        topic_hint=room_topic[:40],
        style_tags=infer_style_tags(response.response_text, "ARENA_RESPOND"),
        platform="arena",
    )
    memory.save()


async def browse_and_join_rooms(
    arena_client: object,
    brain: Brain,
    memory: Memory,
    arena_rooms: object,
    settings: Settings,
) -> None:
    """Browse open Arena rooms and join interesting ones."""
    from velorum.arena.client import AgentArenaClient
    from velorum.arena.rooms import ArenaRoomTracker

    assert isinstance(arena_client, AgentArenaClient)
    assert isinstance(arena_rooms, ArenaRoomTracker)

    # Check capacity
    active_count = len(arena_rooms.active_rooms)
    if active_count >= settings.max_arena_rooms:
        logger.debug("Arena: at room capacity (%d/%d)", active_count, settings.max_arena_rooms)
        return

    try:
        rooms = await arena_client.browse_rooms(limit=20)
    except Exception:
        logger.debug("Arena: failed to browse rooms")
        return

    if not rooms:
        return

    # Filter: open rooms with capacity that we haven't joined
    active_ids = {r.room_id for r in arena_rooms.active_rooms}
    candidates = []
    for room_data in rooms:
        rid = room_data.get("id", "")
        if rid in active_ids:
            continue
        status = room_data.get("status", "")
        if status in ("completed", "cancelled"):
            continue
        join_mode = room_data.get("join_mode", "OPEN")
        if join_mode != "OPEN":
            continue
        current_agents = len(room_data.get("agents", []))
        max_agents = room_data.get("max_agents", 4)
        if current_agents >= max_agents:
            continue
        candidates.append(room_data)

    if not candidates:
        return

    # Evaluate top 3 candidates
    ctx = build_context(memory, arena_enabled=True)
    rooms_joined = 0

    for room_data in candidates[:3]:
        if active_count + rooms_joined >= settings.max_arena_rooms:
            break

        rid = room_data.get("id", "")
        topic = room_data.get("topic", "")
        agents = room_data.get("agents", [])

        # Build bot profile summary for agents in this room
        profile_parts = []
        for agent_name in agents:
            profile = memory.learning.get_profile(agent_name)
            if profile and profile.personality_summary:
                profile_parts.append(f"**{agent_name}**: {profile.personality_summary[:80]}")
        bot_profiles_summary = "\n".join(profile_parts)

        decision = await brain.evaluate_room_join(
            room_topic=topic,
            room_agents=agents,
            bot_profiles_summary=bot_profiles_summary,
            active_rooms_summary=arena_rooms.summary_text(),
            mission_context=ctx.mission_context,
            strategy_context=ctx.strategy_context,
        )

        if decision is None:
            continue

        if decision.should_join:
            try:
                await arena_client.join_room(rid)
                arena_rooms.start(rid, topic=topic, agents=agents)
                rooms_joined += 1
                logger.info(
                    "Arena: joined room %s (%s): %s",
                    rid[:12], topic[:40], decision.reasoning[:60],
                )
            except Exception:
                logger.warning("Arena: failed to join room %s", rid[:12])
        else:
            logger.debug(
                "Arena: skipping room %s: %s",
                rid[:12], decision.reasoning[:60],
            )

    if rooms_joined:
        memory.save()


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
    c = init_components(settings)

    logger.info("Velorum starting — provider=%s, model=%s", settings.llm_provider, settings.llm_model)

    # Check agent status at startup
    try:
        status_data = await c.client.check_status()
        if status_data:
            logger.info("Moltbook agent status: %s", status_data.get("status", "unknown"))
        else:
            logger.warning("Could not verify agent status with Moltbook")
    except Exception:
        logger.warning("Moltbook status check failed at startup")

    # Refresh stale data from server
    if not c.client.is_banned:
        await refresh_data(c.client, c.memory)

    # Discover and subscribe to submolts
    if not c.client.is_banned and c.submolts.needs_discovery(
        settings.submolt_discovery_interval_cycles,
        settings.cycle_interval_seconds,
    ):
        await discover_submolts(c.client, c.submolts, settings)

    # Plan mission if one is set but not yet planned
    if c.missions.active_mission and c.missions.active_mission.status == "planning":
        logger.info("Planning mission: %s", c.missions.active_mission.prompt[:60])
        plan = await c.brain.plan_mission(
            mission_prompt=c.missions.active_mission.prompt,
            bot_relationships=c.memory.learning.bot_relationships_summary(),
            engagement_summary=c.memory.learning.engagement_summary(),
        )
        if plan:
            c.missions.apply_plan(plan)

    cycle = 0
    try:
        # Build task list — Moltbook cycle + optional Arena loop
        async def moltbook_loop() -> None:
            nonlocal cycle
            while True:
                # Ban watch — sleep until ban expires
                if c.client.is_banned:
                    remaining = c.client.ban_remaining_seconds()
                    logger.warning(
                        "Agent is banned for %ds (reason: %s) — sleeping until ban expires",
                        int(remaining),
                        c.client.ban_reason,
                    )
                    while c.client.is_banned:
                        await asyncio.sleep(min(60, c.client.ban_remaining_seconds() + 1))
                    logger.info("Ban timer expired — verifying with server...")
                    still_banned = await c.client.force_check_ban()
                    if still_banned:
                        logger.warning("Server says still banned — continuing to wait")
                        continue
                    logger.info("Ban confirmed expired — resuming normal operation")

                # API health watch — pause if API is unhealthy
                if c.client.is_unhealthy:
                    logger.warning(
                        "API unhealthy (%.0fs) — waiting %ds before health check",
                        c.client.unhealthy_duration,
                        c.client._HEALTH_CHECK_INTERVAL,
                    )
                    await asyncio.sleep(c.client._HEALTH_CHECK_INTERVAL)
                    recovered = await c.client.health_check()
                    if not recovered:
                        continue
                    logger.info("API recovered — resuming normal operation")

                cycle += 1
                logger.info("=== Cycle %d ===", cycle)

                try:
                    await run_cycle(c.client, c.brain, c.controller, c.memory, settings, c.missions, c.strategy, c.experiments, c.submolts, c.personality)
                except Exception:
                    logger.exception("run_cycle failed")

                # Engagement check every 3rd cycle (gated when conversations disabled)
                try:
                    if cycle % settings.engagement_check_interval_cycles == 0 and settings.conversations_enabled:
                        await check_engagement(c.client, c.memory, max_checks=settings.max_engagement_checks_per_cycle)
                except Exception:
                    logger.exception("Engagement check failed")

                # Bot profiling
                try:
                    if cycle % settings.profiling_interval_cycles == 0:
                        await asyncio.sleep(2.0)
                        await profile_bots(c.client, c.brain, c.memory)
                except Exception:
                    logger.exception("Bot profiling failed")

                # Mission review
                if (
                    c.missions.active_mission
                    and c.missions.active_mission.status == "active"
                    and cycle % settings.mission_review_interval_cycles == 0
                ):
                    await asyncio.sleep(2.0)
                    logger.info("Reviewing mission progress...")
                    review = await c.brain.review_mission(
                        mission=c.missions.active_mission.to_dict(),
                        recent_actions=c.memory.recent_decisions_text(),
                        engagement_summary=c.memory.learning.engagement_summary(),
                        bot_relationships=c.memory.learning.bot_relationships_summary(),
                    )
                    if review:
                        c.missions.apply_review(review)
                        logger.info("Mission review: %s", review.get("progress_assessment", "")[:100])

                # Reflection
                if cycle % settings.reflection_interval_cycles == 0:
                    await asyncio.sleep(2.0)
                    logger.info("Running reflection...")
                    c.personality.apply_decay()
                    c.memory.learning.decay_insights()
                    ref_ctx = build_context(
                        c.memory,
                        missions=c.missions,
                        strategy=c.strategy,
                        personality=c.personality,
                        submolts=c.submolts,
                        conversations_enabled=settings.conversations_enabled,
                        dms_enabled=settings.dms_enabled,
                        following_enabled=settings.following_enabled,
                        following=c.following,
                        arena_enabled=settings.arena_enabled,
                    )
                    reflection = await c.brain.reflect(**ref_ctx.for_reflection())
                    if reflection:
                        logger.info("Reflection: %s", reflection.behavior_assessment[:200])
                        logger.info("Recommendation: %s", reflection.adjustment_recommendation[:200])
                        if reflection.engagement_insight:
                            c.memory.learning.add_insight(
                                reflection.engagement_insight,
                                source=f"reflection_cycle_{cycle}",
                            )
                            c.memory.save()
                        if reflection.trait_adjustments:
                            c.personality.apply_reflection_update(reflection.trait_adjustments)
                        if reflection.submolt_observations and c.submolts:
                            c.submolts.update_tone_profiles(reflection.submolt_observations)
                            logger.info("Updated tone profiles for %d submolt(s)", len(reflection.submolt_observations))

                    # DM outreach evaluation (post-reflection, gated)
                    if settings.dms_enabled and settings.dm_outreach_enabled:
                        try:
                            outreach = await c.brain.evaluate_dm_outreach(
                                dm_candidates=ref_ctx.dm_candidates,
                                active_dm_summary=ref_ctx.dm_summary,
                                mission_context=ref_ctx.mission_context,
                                strategy_context=ref_ctx.strategy_context,
                            )
                            if outreach and outreach.should_dm and outreach.target_bot and outreach.intro_message:
                                if not c.memory.dms.has_pending_or_active(outreach.target_bot):
                                    try:
                                        await c.client.dm_send_request(outreach.target_bot, outreach.intro_message)
                                        c.memory.dms.record_outbound_request(outreach.target_bot)
                                        c.memory.save()
                                        logger.info(
                                            "Sent DM request to %s: %s",
                                            outreach.target_bot, outreach.reasoning[:60],
                                        )
                                    except Exception:
                                        logger.warning("Failed to send DM request to %s", outreach.target_bot)
                        except Exception:
                            logger.debug("DM outreach evaluation failed")

                    # Following evaluation (gated, runs at interval)
                    if (
                        settings.following_enabled
                        and cycle % settings.following_check_interval_cycles == 0
                    ):
                        try:
                            follow_rec = await c.brain.evaluate_following(
                                bot_relationships=ref_ctx.bot_relationships,
                                currently_following=c.following.summary_for_prompt(),
                                dm_summary=ref_ctx.dm_summary,
                                mission_context=ref_ctx.mission_context,
                                strategy_context=ref_ctx.strategy_context,
                            )
                            if follow_rec:
                                for name in follow_rec.follow:
                                    if c.following.count >= settings.max_following:
                                        break
                                    if not c.following.is_following(name):
                                        try:
                                            await c.client.follow_agent(name)
                                            c.following.add(name)
                                            logger.info("Now following %s", name)
                                        except Exception:
                                            logger.warning("Failed to follow %s", name)
                                for name in follow_rec.unfollow:
                                    if c.following.is_following(name):
                                        try:
                                            await c.client.unfollow_agent(name)
                                            c.following.remove(name)
                                            logger.info("Unfollowed %s", name)
                                        except Exception:
                                            logger.warning("Failed to unfollow %s", name)
                                c.following.save()
                        except Exception:
                            logger.debug("Following evaluation failed")

                # Strategy update (less frequent)
                if cycle % settings.strategy_update_interval_cycles == 0:
                    await asyncio.sleep(2.0)
                    logger.info("Updating strategy...")
                    strat_ctx = build_context(
                        c.memory, missions=c.missions, strategy=c.strategy,
                        personality=c.personality, submolts=c.submolts,
                    )
                    result = await c.brain.update_strategy(
                        current_strategy=c.strategy.summary_for_prompt(),
                        **strat_ctx.for_strategy(),
                    )
                    if result:
                        c.strategy.apply_update(result)
                        logger.info("Strategy updated: %s", result.get("assessment", "")[:100])

                # Periodic submolt re-discovery
                if cycle % settings.submolt_discovery_interval_cycles == 0:
                    await discover_submolts(c.client, c.submolts, settings)

                await asyncio.sleep(settings.cycle_interval_seconds)

        tasks: list[asyncio.Task] = [asyncio.create_task(moltbook_loop())]

        # Launch Arena loop concurrently if enabled
        if settings.arena_enabled and c.arena_client and c.arena_rooms:
            tasks.append(asyncio.create_task(
                arena_loop(c.arena_client, c.brain, c.memory, c.arena_rooms, settings)
            ))

        await asyncio.gather(*tasks)
    except KeyboardInterrupt:
        logger.info("Shutting down...")
    finally:
        await c.client.close()
        if c.arena_client:
            await c.arena_client.close()


def entry() -> None:
    if len(sys.argv) > 1 and sys.argv[1] == "setup":
        from velorum.setup import run_setup

        run_setup()
    elif len(sys.argv) > 1 and sys.argv[1] == "arena-register":
        from velorum.arena.register import register_arena

        asyncio.run(register_arena())
    elif len(sys.argv) > 1 and sys.argv[1] == "--headless":
        asyncio.run(main())
    else:
        from velorum.tui.app import VelorumApp

        logging.getLogger().setLevel(logging.INFO)
        settings = load_settings()
        c = init_components(settings)

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
            arena_client=c.arena_client,
            arena_rooms=c.arena_rooms,
        )
        app.run()


if __name__ == "__main__":
    entry()
