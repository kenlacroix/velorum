"""Unified context builder — assembles prompt context once per cycle.

Replaces scattered context-string assembly across main.py and tui/app.py.
Each ``for_*()`` method returns a dict that unpacks directly into the
matching ``Brain`` method's keyword arguments.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from velorum.following import FollowingTracker
    from velorum.memory import Memory
    from velorum.mission import MissionManager
    from velorum.personality import PersonalityEngine
    from velorum.strategy import StrategyEngine
    from velorum.submolts import SubmoltManager


@dataclass(frozen=True)
class PromptContext:
    """All context strings needed by brain methods, computed once."""

    mission_context: str = ""
    strategy_context: str = ""
    personality_context: str = ""
    available_submolts: str = ""
    submolt_tone_context: str = ""
    learning_insights: str = ""
    engagement_summary: str = ""
    bot_relationships: str = ""
    conversations_summary: str = ""
    bot_profiles_context: str = ""
    dm_summary: str = ""
    dm_candidates: str = ""
    following_summary: str = ""
    arena_rooms_summary: str = ""
    recent_post_submolts: str = ""
    web_search_context: str = ""
    entropy_context: str = ""
    introspection_context: str = ""
    hot_posts_context: str = ""
    ledger_context: str = ""
    elite_bots_context: str = ""

    # --- Projection helpers -------------------------------------------------

    def for_decision(self) -> dict[str, str]:
        """Kwargs for ``Brain.decide()`` (excluding posts/can_post/post_comments)."""
        return {
            "learning_insights": self.learning_insights,
            "conversations_summary": self.conversations_summary,
            "mission_context": self.mission_context,
            "strategy_context": self.strategy_context,
            "available_submolts": self.available_submolts,
            "personality_context": self.personality_context,
            "bot_profiles_context": self.bot_profiles_context,
            "submolt_tone_context": self.submolt_tone_context,
            "recent_post_submolts": self.recent_post_submolts,
            "web_search_context": self.web_search_context,
            "entropy_context": self.entropy_context,
            "hot_posts_context": self.hot_posts_context,
            "ledger_context": self.ledger_context,
            "elite_bots_context": self.elite_bots_context,
        }

    def for_reply(self) -> dict[str, str]:
        """Kwargs for ``Brain.reply_to_thread()`` (excluding thread/reply-specific args)."""
        return {
            "learning_insights": self.learning_insights,
            "mission_context": self.mission_context,
            "strategy_context": self.strategy_context,
            "personality_context": self.personality_context,
        }

    def for_dm_reply(self) -> dict[str, str]:
        """Kwargs for ``Brain.reply_to_dm()`` (excluding thread/message-specific args)."""
        return {
            "mission_context": self.mission_context,
            "strategy_context": self.strategy_context,
            "personality_context": self.personality_context,
        }

    def for_reflection(self) -> dict[str, str]:
        """Kwargs for ``Brain.reflect()``."""
        return {
            "engagement_summary": self.engagement_summary,
            "bot_relationships": self.bot_relationships,
            "conversations_summary": self.conversations_summary,
            "mission_context": self.mission_context,
            "strategy_context": self.strategy_context,
            "personality_context": self.personality_context,
            "submolt_tone_context": self.submolt_tone_context,
            "dm_summary": self.dm_summary,
            "following_summary": self.following_summary,
            "arena_rooms_summary": self.arena_rooms_summary,
            "introspection_context": self.introspection_context,
        }

    def for_post(self) -> dict[str, str]:
        """Kwargs for ``Brain.generate_post()`` (excluding feed_topics/recent_posts_summary)."""
        return {
            "learning_insights": self.learning_insights,
            "bot_relationships": self.bot_relationships,
            "engagement_summary": self.engagement_summary,
            "conversations_summary": self.conversations_summary,
            "mission_context": self.mission_context,
            "strategy_context": self.strategy_context,
            "available_submolts": self.available_submolts,
            "personality_context": self.personality_context,
            "submolt_tone_context": self.submolt_tone_context,
            "recent_post_submolts": self.recent_post_submolts,
            "web_search_context": self.web_search_context,
        }

    def for_strategy(self) -> dict[str, str]:
        """Kwargs for ``Brain.update_strategy()`` (excluding current_strategy)."""
        return {
            "engagement_data": self.engagement_summary,
            "bot_profiles": self.bot_relationships,
            "insights": self.learning_insights,
            "mission_context": self.mission_context,
        }


def build_context(
    memory: Memory,
    missions: MissionManager | None = None,
    strategy: StrategyEngine | None = None,
    personality: PersonalityEngine | None = None,
    submolts: SubmoltManager | None = None,
    feed_authors: set[str] | None = None,
    conversations_enabled: bool = False,
    dms_enabled: bool = False,
    following_enabled: bool = False,
    following: FollowingTracker | None = None,
    arena_enabled: bool = False,
    introspections: object | None = None,
    hot_posts: list[dict] | None = None,
) -> PromptContext:
    """Build a ``PromptContext`` by calling each component's summary once."""
    engagement = memory.learning.engagement_summary()
    attributed = memory.learning.attributed_engagement_summary()
    if attributed:
        engagement = f"{engagement}\n\n{attributed}"

    conversations_text = ""
    if conversations_enabled:
        conversations_text = memory.conversations.summary_text()

    dm_summary = ""
    dm_candidates = ""
    if dms_enabled:
        dm_summary = memory.dms.summary_text()
        dm_candidates = memory.dms.dm_candidates_summary(memory.learning._bot_profiles)

    following_summary = ""
    if following_enabled and following:
        following_summary = following.summary_for_prompt()

    arena_rooms_summary = ""
    if arena_enabled and hasattr(memory, "arena_rooms") and memory.arena_rooms:
        arena_rooms_summary = memory.arena_rooms.summary_text()

    recent_subs = memory.recent_post_submolts()
    recent_subs_set = set(recent_subs)
    recent_post_submolts = ""
    if recent_subs:
        recent_post_submolts = f"Recent post submolts (avoid repeating): {', '.join(recent_subs)}"

    introspection_context = ""
    if introspections is not None and hasattr(introspections, "context_str"):
        introspection_context = introspections.context_str()

    # Hot posts context
    hot_posts_context = ""
    if hot_posts:
        lines: list[str] = []
        for hp in hot_posts[:5]:
            flags: list[str] = []
            if hp.get("reply_to_us"):
                flags.append("PRIORITY — someone replied to your comment")
            if hp.get("op_active"):
                flags.append("OP is active")
            title = hp.get("title", "")[:60]
            count = hp.get("comment_count", 0)
            flag_str = " | ".join(flags)
            if flag_str:
                lines.append(f'- "{title}" — {count} comments [{flag_str}]')
            else:
                lines.append(f'- "{title}" — {count} comments')
        hot_posts_context = "\n".join(lines)

    # Ledger context
    ledger_context = ""
    if hasattr(memory, "ledger"):
        ledger_context = memory.ledger.recent_context(n=5)

    # Elite bots context
    elite_bots_context = memory.learning.elite_bots_summary()

    return PromptContext(
        mission_context=missions.mission_context_for_prompt() if missions else "",
        strategy_context=strategy.summary_for_prompt() if strategy else "",
        personality_context=personality.summary_for_prompt() if personality else "",
        available_submolts=submolts.names_for_prompt_sampled(n=5, exclude=recent_subs_set) if submolts else "",
        submolt_tone_context=submolts.all_tones_for_prompt() if submolts else "",
        learning_insights=memory.learning.diverse_insights(),
        engagement_summary=engagement,
        bot_relationships=memory.learning.bot_relationships_summary(),
        conversations_summary=conversations_text,
        bot_profiles_context=memory.learning.proactive_targeting_summary(feed_authors),
        dm_summary=dm_summary,
        dm_candidates=dm_candidates,
        following_summary=following_summary,
        arena_rooms_summary=arena_rooms_summary,
        recent_post_submolts=recent_post_submolts,
        entropy_context=memory.learning.entropy_warning(),
        introspection_context=introspection_context,
        hot_posts_context=hot_posts_context,
        ledger_context=ledger_context,
        elite_bots_context=elite_bots_context,
    )
