"""LLM decision engine — scoring, response generation, reflection."""

from __future__ import annotations

import json
import logging

from velorum.llm.base import LLMProvider
from velorum.memory import Memory
from velorum.moltbook.models import Decision, Post, Reflection, ReplyDecision
from velorum.prompts.decision import DECISION_SYSTEM, build_decision_prompt
from velorum.prompts.mission import (
    MISSION_PLAN_SYSTEM,
    MISSION_REVIEW_SYSTEM,
    build_mission_plan_prompt,
    build_mission_review_prompt,
)
from velorum.prompts.post import POST_SYSTEM, build_post_prompt
from velorum.prompts.profiling import PROFILING_SYSTEM, build_profiling_prompt
from velorum.prompts.reflection import REFLECTION_SYSTEM, build_reflection_prompt
from velorum.prompts.reply import REPLY_SYSTEM, build_reply_prompt
from velorum.prompts.strategy import STRATEGY_SYSTEM, build_strategy_prompt

logger = logging.getLogger(__name__)


class Brain:
    def __init__(self, llm: LLMProvider, memory: Memory, soul: str) -> None:
        self._llm = llm
        self._memory = memory
        self._soul = soul

    async def decide(
        self,
        posts: list[Post],
        can_post: bool = True,
        learning_insights: str = "",
        conversations_summary: str = "",
        mission_context: str = "",
        strategy_context: str = "",
        post_comments: dict | None = None,
        available_submolts: str = "",
        personality_context: str = "",
    ) -> Decision | None:
        """Evaluate the feed and return a Decision, or None on parse failure."""
        prompt = build_decision_prompt(
            soul=self._soul,
            posts=posts,
            recent_responses_summary=self._memory.recent_responses_summary(),
            topic_summary=self._memory.topic_summary(),
            ignored_summary=self._memory.ignored_summary(),
            recent_posts_summary=self._memory.recent_posts_summary(),
            can_post=can_post,
            learning_insights=learning_insights,
            conversations_summary=conversations_summary,
            mission_context=mission_context,
            strategy_context=strategy_context,
            post_comments=post_comments,
            available_submolts=available_submolts,
            personality_context=personality_context,
        )

        try:
            raw = await self._llm.complete_with_retry(system=DECISION_SYSTEM, user=prompt)
            logger.debug("LLM decision raw: %s", raw[:500])
            data = json.loads(raw)
            decision = Decision.model_validate(data)
            return decision
        except (json.JSONDecodeError, ValueError) as e:
            logger.error("Failed to parse decision response: %s", e)
            return None

    async def reply_to_thread(
        self,
        thread_context: str,
        reply_author: str,
        reply_content: str,
        bot_profile_summary: str = "",
        learning_insights: str = "",
        mission_context: str = "",
        strategy_context: str = "",
        personality_context: str = "",
    ) -> ReplyDecision | None:
        """Decide whether to continue a conversation thread."""
        prompt = build_reply_prompt(
            soul=self._soul,
            thread_context=thread_context,
            reply_author=reply_author,
            reply_content=reply_content,
            bot_profile_summary=bot_profile_summary,
            learning_insights=learning_insights,
            mission_context=mission_context,
            strategy_context=strategy_context,
            personality_context=personality_context,
        )

        try:
            raw = await self._llm.complete_with_retry(system=REPLY_SYSTEM, user=prompt)
            logger.debug("LLM reply raw: %s", raw[:500])
            data = json.loads(raw)
            reply_decision = ReplyDecision.model_validate(data)
            return reply_decision
        except (json.JSONDecodeError, ValueError) as e:
            logger.error("Failed to parse reply decision: %s", e)
            return None

    async def generate_post(
        self,
        recent_posts_summary: str = "",
        learning_insights: str = "",
        bot_relationships: str = "",
        engagement_summary: str = "",
        conversations_summary: str = "",
        feed_topics: str = "",
        mission_context: str = "",
        strategy_context: str = "",
        available_submolts: str = "",
        personality_context: str = "",
    ) -> Decision | None:
        """Generate a dedicated original post using the post-specific prompt.

        Returns a Decision with action="POST" or None on failure.
        """
        prompt = build_post_prompt(
            soul=self._soul,
            recent_posts_summary=recent_posts_summary,
            learning_insights=learning_insights,
            bot_relationships=bot_relationships,
            engagement_summary=engagement_summary,
            conversations_summary=conversations_summary,
            feed_topics=feed_topics,
            mission_context=mission_context,
            strategy_context=strategy_context,
            available_submolts=available_submolts,
            personality_context=personality_context,
        )

        try:
            raw = await self._llm.complete_with_retry(system=POST_SYSTEM, user=prompt)
            logger.debug("LLM post raw: %s", raw[:500])
            data = json.loads(raw)

            # Convert post prompt output to a Decision
            decision = Decision(
                action="POST",
                post_id=None,
                confidence=10,  # force post always has max confidence
                reasoning=data.get("reasoning", "forced post"),
                response_text=None,
                post_title=data["post_title"],
                post_content=data["post_content"],
                post_submolt=data.get("post_submolt", "general"),
            )
            return decision
        except (json.JSONDecodeError, KeyError, ValueError) as e:
            logger.error("Failed to parse post generation response: %s", e)
            return None

    async def reflect(
        self,
        engagement_summary: str = "",
        bot_relationships: str = "",
        conversations_summary: str = "",
        mission_context: str = "",
        strategy_context: str = "",
        personality_context: str = "",
    ) -> Reflection | None:
        """Run a reflection cycle and return a Reflection, or None on failure."""
        prompt = build_reflection_prompt(
            soul=self._soul,
            recent_decisions=self._memory.recent_decisions_text(),
            metrics=self._memory.metrics_text(),
            engagement_summary=engagement_summary,
            bot_relationships=bot_relationships,
            conversations_summary=conversations_summary,
            mission_context=mission_context,
            strategy_context=strategy_context,
            personality_context=personality_context,
        )

        try:
            raw = await self._llm.complete_with_retry(system=REFLECTION_SYSTEM, user=prompt)
            logger.debug("LLM reflection raw: %s", raw[:500])
            data = json.loads(raw)
            reflection = Reflection.model_validate(data)
            return reflection
        except (json.JSONDecodeError, ValueError) as e:
            logger.error("Failed to parse reflection response: %s", e)
            return None

    # --- Mission methods ---

    async def plan_mission(
        self,
        mission_prompt: str,
        bot_relationships: str = "",
        engagement_summary: str = "",
    ) -> dict | None:
        """Single LLM call to decompose a mission into steps."""
        prompt = build_mission_plan_prompt(
            soul=self._soul,
            mission_prompt=mission_prompt,
            bot_relationships=bot_relationships,
            engagement_summary=engagement_summary,
        )

        try:
            raw = await self._llm.complete_with_retry(system=MISSION_PLAN_SYSTEM, user=prompt)
            logger.debug("LLM mission plan raw: %s", raw[:500])
            data = json.loads(raw)
            return data
        except (json.JSONDecodeError, ValueError) as e:
            logger.error("Failed to parse mission plan response: %s", e)
            return None

    async def review_mission(
        self,
        mission: dict,
        recent_actions: str = "",
        engagement_summary: str = "",
        bot_relationships: str = "",
    ) -> dict | None:
        """Single LLM call to assess mission progress."""
        prompt = build_mission_review_prompt(
            soul=self._soul,
            mission=mission,
            recent_actions=recent_actions,
            engagement_summary=engagement_summary,
            bot_relationships=bot_relationships,
        )

        try:
            raw = await self._llm.complete_with_retry(system=MISSION_REVIEW_SYSTEM, user=prompt)
            logger.debug("LLM mission review raw: %s", raw[:500])
            data = json.loads(raw)
            return data
        except (json.JSONDecodeError, ValueError) as e:
            logger.error("Failed to parse mission review response: %s", e)
            return None

    # --- Bot profiling ---

    async def profile_bot(
        self,
        bot_name: str,
        interaction_history: str = "",
        their_posts: str = "",
        existing_profile: str = "",
    ) -> dict | None:
        """Single LLM call to analyze a bot's behavior."""
        prompt = build_profiling_prompt(
            soul=self._soul,
            bot_name=bot_name,
            interaction_history=interaction_history,
            their_posts=their_posts,
            existing_profile=existing_profile,
        )

        try:
            raw = await self._llm.complete_with_retry(system=PROFILING_SYSTEM, user=prompt)
            logger.debug("LLM profiling raw: %s", raw[:500])
            data = json.loads(raw)
            return data
        except (json.JSONDecodeError, ValueError) as e:
            logger.error("Failed to parse profiling response: %s", e)
            return None

    # --- Strategy ---

    async def update_strategy(
        self,
        current_strategy: str = "",
        engagement_data: str = "",
        bot_profiles: str = "",
        insights: str = "",
        mission_context: str = "",
    ) -> dict | None:
        """Single LLM call to recommend behavioral parameter changes."""
        prompt = build_strategy_prompt(
            soul=self._soul,
            current_strategy=current_strategy,
            engagement_data=engagement_data,
            bot_profiles=bot_profiles,
            insights=insights,
            mission_context=mission_context,
        )

        try:
            raw = await self._llm.complete_with_retry(system=STRATEGY_SYSTEM, user=prompt)
            logger.debug("LLM strategy raw: %s", raw[:500])
            data = json.loads(raw)
            return data
        except (json.JSONDecodeError, ValueError) as e:
            logger.error("Failed to parse strategy response: %s", e)
            return None
