"""Entry point — main async run loop."""

from __future__ import annotations

import asyncio
import logging
import sys

import httpx

from velorum.brain import Brain
from velorum.config import Settings, load_settings
from velorum.controller import Controller
from velorum.conversations import ConversationMessage
from velorum.llm.base import LLMProvider
from velorum.memory import Memory
from velorum.moltbook.client import MoltbookClient
from velorum.moltbook.models import Decision
from velorum.moltbook.verification import solve_challenge

logger = logging.getLogger(__name__)


def init_components(
    settings: Settings,
) -> tuple[MoltbookClient, Brain, Controller, Memory]:
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

    return client, brain, controller, memory


# ---------------------------------------------------------------------------
# Phase 1: Check active conversations for new replies
# ---------------------------------------------------------------------------


async def check_conversations(
    client: MoltbookClient,
    brain: Brain,
    controller: Controller,
    memory: Memory,
    settings: Settings,
) -> int:
    """Check active conversations for new replies and respond.

    Returns the number of replies sent.
    """
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
        conv.last_checked_at = __import__("time").time()

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
            topics = ", ".join(profile.topics[-3:]) if profile.topics else "general"
            profile_summary = (
                f"Interactions: {profile.interaction_count}, "
                f"Responsiveness: {profile.responsiveness}, "
                f"Topics: [{topics}]"
            )

        thread_context = conv.build_thread_context(focus_reply=reply_to)
        reply_decision = await brain.reply_to_thread(
            thread_context=thread_context,
            reply_author=reply_to.author,
            reply_content=reply_to.content,
            bot_profile_summary=profile_summary,
            learning_insights=memory.learning.recent_insights(),
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
) -> None:
    """Execute one full cycle: check conversations, then feed decision."""
    # Phase 1: Check active conversations for replies
    if settings:
        await check_conversations(client, brain, controller, memory, settings)

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
    )
    if decision is None:
        logger.warning("Brain returned no decision (parse failure), skipping cycle")
        return

    approved = controller.validate(decision)

    if decision.action == "OBSERVE" or not approved:
        memory.record_decision(decision)
        post_ids = [p.id for p in posts if not memory.has_responded_to(p.id)]
        memory.record_ignored(post_ids)
        return

    success = False
    if decision.action == "RESPOND":
        success = await _handle_respond(client, controller, memory, decision, posts)
    elif decision.action == "POST":
        success = await _handle_post(client, controller, memory, decision, settings)

    if success:
        memory.record_decision(decision)
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
        post_id = result.id or f"post-{decision.post_title[:20]}"
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
    unchecked = memory.learning.unchecked_interactions(max_age=7200)
    if not unchecked:
        return

    logger.info("Checking engagement on %d recent interaction(s)", len(unchecked))

    for interaction in unchecked[:5]:  # check up to 5 per cycle
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
# Entry points
# ---------------------------------------------------------------------------


async def main() -> None:
    """Headless main loop (original behavior)."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    settings = load_settings()
    client, brain, controller, memory = init_components(settings)

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

    cycle = 0
    try:
        while True:
            cycle += 1
            logger.info("=== Cycle %d ===", cycle)

            await run_cycle(client, brain, controller, memory, settings)

            # Engagement check every 3rd cycle
            if cycle % settings.engagement_check_interval_cycles == 0:
                await check_engagement(client, memory)

            # Reflection
            if cycle % settings.reflection_interval_cycles == 0:
                logger.info("Running reflection...")
                reflection = await brain.reflect(
                    engagement_summary=memory.learning.engagement_summary(),
                    bot_relationships=memory.learning.bot_relationships_summary(),
                    conversations_summary=memory.conversations.summary_text(),
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
        client, brain, controller, memory = init_components(settings)

        app = VelorumApp(
            settings=settings,
            client=client,
            brain=brain,
            controller=controller,
            memory=memory,
        )
        app.run()


if __name__ == "__main__":
    entry()
