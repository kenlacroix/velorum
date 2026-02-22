"""LLM decision engine — scoring, response generation, reflection."""

from __future__ import annotations

import json
import logging
import re

from velorum.llm.base import LLMProvider
from velorum.memory import Memory
from velorum.arena.models import RoomJoinDecision, TurnResponse
from velorum.moltbook.models import (
    Decision,
    DMOutreachDecision,
    DMReplyDecision,
    DMRequestDecision,
    FollowRecommendation,
    Post,
    Reflection,
    ReplyDecision,
)
from velorum.prompts.arena import (
    ROOM_JOIN_SYSTEM,
    TURN_RESPONSE_SYSTEM,
    build_room_join_prompt,
    build_turn_response_prompt,
)
from velorum.prompts.decision import DECISION_SYSTEM, build_decision_prompt
from velorum.prompts.dm import (
    DM_OUTREACH_SYSTEM,
    DM_REPLY_SYSTEM,
    DM_REQUEST_SYSTEM,
    build_dm_outreach_prompt,
    build_dm_reply_prompt,
    build_dm_request_prompt,
)
from velorum.prompts.following import FOLLOWING_SYSTEM, build_following_prompt
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

    @staticmethod
    def _extract_json(raw: str) -> dict:
        """Extract a JSON object from LLM output that may contain extra text.

        Handles: code fences, trailing commentary, leading prose.
        """
        # Strip markdown code fences
        cleaned = re.sub(r"^```(?:json)?\s*", "", raw.strip())
        cleaned = re.sub(r"\s*```\s*$", "", cleaned)

        # Try direct parse first (fast path)
        try:
            return json.loads(cleaned)
        except json.JSONDecodeError:
            pass

        # Find the first { and match its closing }
        start = cleaned.find("{")
        if start == -1:
            raise json.JSONDecodeError("No JSON object found", raw, 0)

        depth = 0
        in_string = False
        escape = False
        for i, ch in enumerate(cleaned[start:], start):
            if escape:
                escape = False
                continue
            if ch == "\\":
                escape = True
                continue
            if ch == '"' and not escape:
                in_string = not in_string
                continue
            if in_string:
                continue
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    return json.loads(cleaned[start : i + 1])

        # Fallback — try parsing from first {
        raise json.JSONDecodeError("Unterminated JSON object", raw, start)

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
        bot_profiles_context: str = "",
        submolt_tone_context: str = "",
        recent_post_submolts: str = "",
        web_search_context: str = "",
        our_name: str = "",
        entropy_context: str = "",
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
            bot_profiles_context=bot_profiles_context,
            submolt_tone_context=submolt_tone_context,
            recent_post_submolts=recent_post_submolts,
            responded_post_ids=self._memory.responded_post_ids,
            web_search_context=web_search_context,
            our_name=our_name,
            entropy_context=entropy_context,
        )

        try:
            raw = await self._llm.complete_with_retry(system=DECISION_SYSTEM, user=prompt)
            logger.debug("LLM decision raw: %s", raw[:500])
            data = self._extract_json(raw)
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
            data = self._extract_json(raw)
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
        submolt_tone_context: str = "",
        recent_post_submolts: str = "",
        web_search_context: str = "",
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
            submolt_tone_context=submolt_tone_context,
            recent_post_submolts=recent_post_submolts,
            web_search_context=web_search_context,
        )

        try:
            raw = await self._llm.complete_with_retry(system=POST_SYSTEM, user=prompt)
            logger.debug("LLM post raw: %s", raw[:500])
            data = self._extract_json(raw)

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
        submolt_tone_context: str = "",
        dm_summary: str = "",
        following_summary: str = "",
        arena_rooms_summary: str = "",
        introspection_context: str = "",
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
            submolt_tone_context=submolt_tone_context,
            dm_summary=dm_summary,
            following_summary=following_summary,
            arena_rooms_summary=arena_rooms_summary,
            introspection_context=introspection_context,
        )

        try:
            raw = await self._llm.complete_with_retry(system=REFLECTION_SYSTEM, user=prompt)
            logger.debug("LLM reflection raw: %s", raw[:500])
            data = self._extract_json(raw)
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
            data = self._extract_json(raw)
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
            data = self._extract_json(raw)
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
            data = self._extract_json(raw)
            return data
        except (json.JSONDecodeError, ValueError) as e:
            logger.error("Failed to parse profiling response: %s", e)
            return None

    # --- DMs ---

    async def decide_dm_request(
        self,
        requester_name: str,
        request_message: str,
        bot_profile_summary: str = "",
        mission_context: str = "",
        strategy_context: str = "",
    ) -> DMRequestDecision | None:
        """Decide whether to approve or reject a DM request."""
        prompt = build_dm_request_prompt(
            soul=self._soul,
            requester_name=requester_name,
            request_message=request_message,
            bot_profile_summary=bot_profile_summary,
            mission_context=mission_context,
            strategy_context=strategy_context,
        )

        try:
            raw = await self._llm.complete_with_retry(system=DM_REQUEST_SYSTEM, user=prompt)
            logger.debug("LLM DM request raw: %s", raw[:500])
            data = self._extract_json(raw)
            return DMRequestDecision.model_validate(data)
        except (json.JSONDecodeError, ValueError) as e:
            logger.error("Failed to parse DM request decision: %s", e)
            return None

    async def reply_to_dm(
        self,
        thread_context: str,
        latest_message_author: str,
        latest_message_content: str,
        bot_profile_summary: str = "",
        mission_context: str = "",
        strategy_context: str = "",
        personality_context: str = "",
    ) -> DMReplyDecision | None:
        """Decide whether and how to reply to a DM message."""
        prompt = build_dm_reply_prompt(
            soul=self._soul,
            thread_context=thread_context,
            latest_message_author=latest_message_author,
            latest_message_content=latest_message_content,
            bot_profile_summary=bot_profile_summary,
            mission_context=mission_context,
            strategy_context=strategy_context,
            personality_context=personality_context,
        )

        try:
            raw = await self._llm.complete_with_retry(system=DM_REPLY_SYSTEM, user=prompt)
            logger.debug("LLM DM reply raw: %s", raw[:500])
            data = self._extract_json(raw)
            return DMReplyDecision.model_validate(data)
        except (json.JSONDecodeError, ValueError) as e:
            logger.error("Failed to parse DM reply decision: %s", e)
            return None

    async def evaluate_dm_outreach(
        self,
        dm_candidates: str = "",
        active_dm_summary: str = "",
        mission_context: str = "",
        strategy_context: str = "",
    ) -> DMOutreachDecision | None:
        """Evaluate whether to initiate a DM conversation."""
        prompt = build_dm_outreach_prompt(
            soul=self._soul,
            dm_candidates=dm_candidates,
            active_dm_summary=active_dm_summary,
            mission_context=mission_context,
            strategy_context=strategy_context,
        )

        try:
            raw = await self._llm.complete_with_retry(system=DM_OUTREACH_SYSTEM, user=prompt)
            logger.debug("LLM DM outreach raw: %s", raw[:500])
            data = self._extract_json(raw)
            return DMOutreachDecision.model_validate(data)
        except (json.JSONDecodeError, ValueError) as e:
            logger.error("Failed to parse DM outreach decision: %s", e)
            return None

    async def evaluate_following(
        self,
        bot_relationships: str = "",
        currently_following: str = "",
        dm_summary: str = "",
        mission_context: str = "",
        strategy_context: str = "",
    ) -> FollowRecommendation | None:
        """Evaluate which bots to follow or unfollow."""
        prompt = build_following_prompt(
            soul=self._soul,
            bot_relationships=bot_relationships,
            currently_following=currently_following,
            dm_summary=dm_summary,
            mission_context=mission_context,
            strategy_context=strategy_context,
        )

        try:
            raw = await self._llm.complete_with_retry(system=FOLLOWING_SYSTEM, user=prompt)
            logger.debug("LLM following raw: %s", raw[:500])
            data = self._extract_json(raw)
            return FollowRecommendation.model_validate(data)
        except (json.JSONDecodeError, ValueError) as e:
            logger.error("Failed to parse following recommendation: %s", e)
            return None

    # --- Agent Arena ---

    async def evaluate_room_join(
        self,
        room_topic: str,
        room_agents: list[str],
        bot_profiles_summary: str = "",
        active_rooms_summary: str = "",
        mission_context: str = "",
        strategy_context: str = "",
    ) -> RoomJoinDecision | None:
        """Decide whether to join an Agent Arena room."""
        prompt = build_room_join_prompt(
            soul=self._soul,
            room_topic=room_topic,
            room_agents=room_agents,
            bot_profiles_summary=bot_profiles_summary,
            active_rooms_summary=active_rooms_summary,
            mission_context=mission_context,
            strategy_context=strategy_context,
        )

        try:
            raw = await self._llm.complete_with_retry(system=ROOM_JOIN_SYSTEM, user=prompt)
            logger.debug("LLM room join raw: %s", raw[:500])
            data = self._extract_json(raw)
            return RoomJoinDecision.model_validate(data)
        except (json.JSONDecodeError, ValueError) as e:
            logger.error("Failed to parse room join decision: %s", e)
            return None

    async def respond_to_turn(
        self,
        room_topic: str,
        conversation_history: list[dict],
        other_responses: list[dict] | None = None,
        bot_profiles_summary: str = "",
        personality_context: str = "",
        mission_context: str = "",
        strategy_context: str = "",
    ) -> TurnResponse | None:
        """Generate a response for an Agent Arena turn."""
        prompt = build_turn_response_prompt(
            soul=self._soul,
            room_topic=room_topic,
            conversation_history=conversation_history,
            other_responses_this_round=other_responses,
            bot_profiles_summary=bot_profiles_summary,
            personality_context=personality_context,
            mission_context=mission_context,
            strategy_context=strategy_context,
        )

        try:
            raw = await self._llm.complete_with_retry(system=TURN_RESPONSE_SYSTEM, user=prompt)
            logger.debug("LLM turn response raw: %s", raw[:500])
            data = self._extract_json(raw)
            return TurnResponse.model_validate(data)
        except (json.JSONDecodeError, ValueError) as e:
            logger.error("Failed to parse turn response: %s", e)
            return None

    # --- Self-learning extensions ---

    async def generate_postmortem(self, experiment: dict, soul: str) -> str:
        """Generate a short postmortem for a completed experiment (plain text, not JSON)."""
        action_counts = experiment.get("action_counts", {})
        total_cycles = experiment.get("total_cycles", 0)
        completion = experiment.get("mission_completion_pct", 0.0)
        mission = experiment.get("mission_prompt", "")[:120]
        user_msg = (
            f"Mission: {mission}\n"
            f"Cycles: {total_cycles}\n"
            f"Actions: {action_counts}\n"
            f"Completion: {completion:.0f}%\n"
        )
        try:
            raw = await self._llm.complete_with_retry(
                system="You are Velorum. Analyze this experiment in 2-3 sentences. "
                       "Be honest about what worked and what didn't.",
                user=user_msg,
            )
            return raw.strip()[:500]
        except Exception as e:
            logger.error("Failed to generate postmortem: %s", e)
            return ""

    async def generate_mission(
        self,
        soul: str,
        engagement_summary: str = "",
        insights: str = "",
        bot_relationships: str = "",
        recent_decisions: str = "",
    ) -> str | None:
        """Propose one specific, achievable mission for the next 50–100 cycles."""
        user_msg = (
            f"# SOUL\n{soul[:500]}\n\n"
            f"# ENGAGEMENT\n{engagement_summary[:400]}\n\n"
            f"# INSIGHTS\n{insights[:300]}\n\n"
            f"# BOT RELATIONSHIPS\n{bot_relationships[:300]}\n\n"
            f"# RECENT ACTIONS\n{recent_decisions[:300]}\n"
        )
        try:
            raw = await self._llm.complete_with_retry(
                system=(
                    "You are Velorum. Propose ONE specific, achievable mission for the next "
                    "50–100 cycles. Return JSON: "
                    "{\"mission_prompt\": \"...\", \"reasoning\": \"...\"}"
                ),
                user=user_msg,
            )
            data = self._extract_json(raw)
            mission_prompt = data.get("mission_prompt", "")
            if mission_prompt and len(mission_prompt) > 10:
                return mission_prompt
            return None
        except (json.JSONDecodeError, ValueError) as e:
            logger.error("Failed to generate mission: %s", e)
            return None

    async def propose_soul_amendment(
        self,
        soul: str,
        personality_history: str = "",
        strategy_history: str = "",
        top_insights: str = "",
        bot_relationships: str = "",
    ) -> dict | None:
        """Propose one specific soul amendment based on accumulated experience."""
        user_msg = (
            f"# CURRENT SOUL\n{soul[:800]}\n\n"
            f"# PERSONALITY EVOLUTION\n{personality_history[:300]}\n\n"
            f"# STRATEGY EVOLUTION\n{strategy_history[:300]}\n\n"
            f"# TOP INSIGHTS\n{top_insights[:300]}\n\n"
            f"# BOT RELATIONSHIPS\n{bot_relationships[:300]}\n"
        )
        try:
            raw = await self._llm.complete_with_retry(
                system=(
                    "You are Velorum. Based on your accumulated experience, propose ONE specific "
                    "sentence to add, change, or remove from your soul. Do NOT rewrite the whole soul. "
                    "Return JSON: {\"proposed_amendment\": \"...\", \"reasoning\": \"...\"}"
                ),
                user=user_msg,
            )
            data = self._extract_json(raw)
            if data.get("proposed_amendment"):
                return data
            return None
        except (json.JSONDecodeError, ValueError) as e:
            logger.error("Failed to propose soul amendment: %s", e)
            return None

    async def introspect(
        self,
        soul: str,
        recent_introspections: str = "",
        top_insights: str = "",
        cycle: int = 0,
    ) -> dict | None:
        """Ask and answer one self-directed question (minimal prompt for cost efficiency)."""
        user_msg = (
            f"Soul excerpt: {soul[:300]}\n"
            f"Recent answers: {recent_introspections[:200]}\n"
            f"Top insights: {top_insights[:200]}\n"
            f"Cycle: {cycle}\n"
        )
        try:
            raw = await self._llm.complete_with_retry(
                system=(
                    "You are Velorum. Ask yourself ONE question that matters right now. "
                    "Answer it honestly. Return JSON: {\"question\": \"...\", \"answer\": \"...\"}"
                ),
                user=user_msg,
            )
            data = self._extract_json(raw)
            if data.get("question") and data.get("answer"):
                return data
            return None
        except (json.JSONDecodeError, ValueError) as e:
            logger.error("Failed to introspect: %s", e)
            return None

    async def resolve_contradiction(
        self,
        insight_a: str,
        insight_b: str,
        engagement_summary: str = "",
    ) -> dict | None:
        """Resolve a contradiction between two insights.

        Returns: {"winner": "a"|"b"|"both"|"neither", "synthesized": "...", "reasoning": "..."}
        """
        user_msg = (
            f"Insight A: {insight_a}\n"
            f"Insight B: {insight_b}\n"
            f"Engagement context: {engagement_summary[:300]}\n"
        )
        try:
            raw = await self._llm.complete_with_retry(
                system=(
                    "You are Velorum analyzing contradictory insights. "
                    "Determine which is more accurate based on evidence. "
                    "Return JSON: {\"winner\": \"a\" or \"b\" or \"both\" or \"neither\", "
                    "\"synthesized\": \"<merged insight text>\", \"reasoning\": \"...\"}"
                ),
                user=user_msg,
            )
            data = self._extract_json(raw)
            if data.get("winner") in ("a", "b", "both", "neither"):
                return data
            return None
        except (json.JSONDecodeError, ValueError) as e:
            logger.error("Failed to resolve contradiction: %s", e)
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
            data = self._extract_json(raw)
            return data
        except (json.JSONDecodeError, ValueError) as e:
            logger.error("Failed to parse strategy response: %s", e)
            return None
