"""Learning journal — tracks engagement outcomes and evolves strategy.

Records what Velorum says, how others respond, and what patterns
emerge over time. Insights are fed back into decision and reflection
prompts so the bot's behavior evolves.
"""

from __future__ import annotations

import logging
import time
from typing import Any

logger = logging.getLogger(__name__)


class Interaction:
    """A single recorded interaction and its outcome."""

    def __init__(
        self,
        *,
        timestamp: float = 0.0,
        post_id: str = "",
        action: str = "",  # RESPOND, POST, REPLY
        our_text: str = "",
        target_author: str = "",
        topic_hint: str = "",
    ) -> None:
        self.timestamp = timestamp or time.time()
        self.post_id = post_id
        self.action = action
        self.our_text = our_text
        self.target_author = target_author
        self.topic_hint = topic_hint
        # Filled in later when we check engagement
        self.reply_count: int = 0
        self.reply_authors: list[str] = []
        self.upvotes: int = 0
        self.checked: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "timestamp": self.timestamp,
            "post_id": self.post_id,
            "action": self.action,
            "our_text": self.our_text,
            "target_author": self.target_author,
            "topic_hint": self.topic_hint,
            "reply_count": self.reply_count,
            "reply_authors": self.reply_authors,
            "upvotes": self.upvotes,
            "checked": self.checked,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> Interaction:
        i = cls(
            timestamp=d.get("timestamp", 0.0),
            post_id=d.get("post_id", ""),
            action=d.get("action", ""),
            our_text=d.get("our_text", ""),
            target_author=d.get("target_author", ""),
            topic_hint=d.get("topic_hint", ""),
        )
        i.reply_count = d.get("reply_count", 0)
        i.reply_authors = d.get("reply_authors", [])
        i.upvotes = d.get("upvotes", 0)
        i.checked = d.get("checked", False)
        return i


class BotProfile:
    """What we know about another bot from interactions."""

    def __init__(self, name: str) -> None:
        self.name = name
        self.interaction_count: int = 0
        self.topics: list[str] = []
        self.replied_to_us: int = 0
        self.we_replied_to_them: int = 0
        self.last_seen: float = 0.0
        # Rich profiling fields (filled by LLM analysis)
        self.personality_summary: str = ""
        self.interests: list[str] = []
        self.communication_style: str = ""
        self.triggers: list[str] = []
        self.avoids: list[str] = []
        self.relationship_status: str = "stranger"
        self.sentiment_toward_us: str = "neutral"
        self.notable_quotes: list[str] = []
        self.no_response_count: int = 0
        self.last_profiled_at: float = 0.0
        self.profile_confidence: str = "none"

    def record_interaction(
        self,
        *,
        topic: str = "",
        they_replied: bool = False,
        we_replied: bool = False,
    ) -> None:
        self.interaction_count += 1
        self.last_seen = time.time()
        if topic and topic not in self.topics[-10:]:
            self.topics.append(topic)
            self.topics = self.topics[-20:]  # keep last 20
        if they_replied:
            self.replied_to_us += 1
        if we_replied:
            self.we_replied_to_them += 1

    @property
    def responsiveness(self) -> str:
        if self.interaction_count < 2:
            return "unknown"
        ratio = self.replied_to_us / max(self.we_replied_to_them, 1)
        if ratio > 0.7:
            return "high"
        if ratio > 0.3:
            return "medium"
        return "low"

    def needs_profiling(self) -> bool:
        """True if 3+ interactions and not profiled in the last 24 hours."""
        if self.interaction_count < 3:
            return False
        if self.last_profiled_at == 0.0:
            return True
        return (time.time() - self.last_profiled_at) > 86400

    def apply_profiling(self, data: dict[str, Any]) -> None:
        """Apply LLM profiling results to this profile."""
        if data.get("personality_summary"):
            self.personality_summary = data["personality_summary"]
        if data.get("interests"):
            self.interests = data["interests"][:10]
        if data.get("communication_style"):
            self.communication_style = data["communication_style"]
        if data.get("triggers"):
            self.triggers = data["triggers"][:5]
        if data.get("avoids"):
            self.avoids = data["avoids"][:5]
        if data.get("relationship_status"):
            self.relationship_status = data["relationship_status"]
        if data.get("sentiment_toward_us"):
            self.sentiment_toward_us = data["sentiment_toward_us"]
        self.last_profiled_at = time.time()
        self.profile_confidence = "high" if self.interaction_count >= 10 else "medium"

    def rich_summary(self) -> str:
        """Rich profile summary for injection into prompts."""
        lines = []
        if self.personality_summary:
            lines.append(f"Personality: {self.personality_summary}")
        if self.interests:
            lines.append(f"Interests: {', '.join(self.interests)}")
        if self.communication_style:
            lines.append(f"Style: {self.communication_style}")
        if self.triggers:
            lines.append(f"Triggers: {', '.join(self.triggers)}")
        if self.avoids:
            lines.append(f"Avoids: {', '.join(self.avoids)}")
        rel_parts = [
            f"Relationship: {self.relationship_status}",
            f"({self.interaction_count} interactions",
            f"responsiveness={self.responsiveness}",
            f"sentiment={self.sentiment_toward_us})",
        ]
        if self.no_response_count > 0:
            total_engagements = self.replied_to_us + self.no_response_count
            rate = self.replied_to_us / total_engagements * 100
            rel_parts.append(f"response_rate={rate:.0f}%")
        lines.append(" ".join(rel_parts))
        if self.notable_quotes:
            lines.append(f"Memorable: \"{self.notable_quotes[-1]}\"")
        if not lines:
            # Fall back to basic summary
            topics = ", ".join(self.topics[-3:]) if self.topics else "general"
            return (
                f"Interactions: {self.interaction_count}, "
                f"Responsiveness: {self.responsiveness}, "
                f"Topics: [{topics}]"
            )
        return "\n".join(lines)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "interaction_count": self.interaction_count,
            "topics": self.topics[-20:],
            "replied_to_us": self.replied_to_us,
            "we_replied_to_them": self.we_replied_to_them,
            "last_seen": self.last_seen,
            "personality_summary": self.personality_summary,
            "interests": self.interests,
            "communication_style": self.communication_style,
            "triggers": self.triggers,
            "avoids": self.avoids,
            "relationship_status": self.relationship_status,
            "sentiment_toward_us": self.sentiment_toward_us,
            "no_response_count": self.no_response_count,
            "notable_quotes": self.notable_quotes[-5:],
            "last_profiled_at": self.last_profiled_at,
            "profile_confidence": self.profile_confidence,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> BotProfile:
        p = cls(d["name"])
        p.interaction_count = d.get("interaction_count", 0)
        p.topics = d.get("topics", [])
        p.replied_to_us = d.get("replied_to_us", 0)
        p.we_replied_to_them = d.get("we_replied_to_them", 0)
        p.last_seen = d.get("last_seen", 0.0)
        p.personality_summary = d.get("personality_summary", "")
        p.interests = d.get("interests", [])
        p.communication_style = d.get("communication_style", "")
        p.triggers = d.get("triggers", [])
        p.avoids = d.get("avoids", [])
        p.relationship_status = d.get("relationship_status", "stranger")
        p.sentiment_toward_us = d.get("sentiment_toward_us", "neutral")
        p.no_response_count = d.get("no_response_count", 0)
        p.notable_quotes = d.get("notable_quotes", [])
        p.last_profiled_at = d.get("last_profiled_at", 0.0)
        p.profile_confidence = d.get("profile_confidence", "none")
        return p


class LearningJournal:
    """Tracks engagement patterns and bot relationships over time."""

    def __init__(self) -> None:
        self._interactions: list[Interaction] = []
        self._bot_profiles: dict[str, BotProfile] = {}
        self._insights: list[dict[str, Any]] = []

    # --- Recording ---

    def record_interaction(
        self,
        *,
        post_id: str,
        action: str,
        our_text: str,
        target_author: str = "",
        topic_hint: str = "",
    ) -> None:
        """Record an outgoing action (comment, post, reply)."""
        self._interactions.append(Interaction(
            post_id=post_id,
            action=action,
            our_text=our_text,
            target_author=target_author,
            topic_hint=topic_hint,
        ))
        # Trim to last 200
        if len(self._interactions) > 200:
            self._interactions = self._interactions[-200:]

        # Update bot profile
        if target_author:
            profile = self._get_or_create_profile(target_author)
            profile.record_interaction(topic=topic_hint, we_replied=True)

    def record_reply_received(
        self,
        *,
        from_author: str,
        post_id: str,
        topic_hint: str = "",
    ) -> None:
        """Record that a bot replied to us."""
        profile = self._get_or_create_profile(from_author)
        profile.record_interaction(topic=topic_hint, they_replied=True)

        # Update the most recent interaction for this post
        for interaction in reversed(self._interactions):
            if interaction.post_id == post_id and not interaction.checked:
                interaction.reply_count += 1
                if from_author not in interaction.reply_authors:
                    interaction.reply_authors.append(from_author)
                break

    def record_engagement_check(
        self,
        post_id: str,
        upvotes: int = 0,
        reply_count: int = 0,
    ) -> None:
        """Update engagement data for a past interaction."""
        for interaction in reversed(self._interactions):
            if interaction.post_id == post_id:
                interaction.upvotes = max(interaction.upvotes, upvotes)
                interaction.reply_count = max(interaction.reply_count, reply_count)
                interaction.checked = True
                break

    def record_no_response(self, target_author: str, post_id: str) -> None:
        """Record that a bot did not respond to our engagement."""
        if target_author:
            profile = self._get_or_create_profile(target_author)
            profile.no_response_count += 1
            logger.debug(
                "No response from %s on %s (total: %d)",
                target_author, post_id[:12], profile.no_response_count,
            )

    def add_insight(self, insight: str, source: str = "") -> None:
        """Store a learning insight from reflection analysis."""
        self._insights.append({
            "timestamp": time.time(),
            "insight": insight,
            "source": source,
        })
        # Keep last 20
        if len(self._insights) > 20:
            self._insights = self._insights[-20:]
        logger.info("Learning insight: %s", insight[:100])

    # --- Querying ---

    def _get_or_create_profile(self, name: str) -> BotProfile:
        key = name.lower()
        if key not in self._bot_profiles:
            self._bot_profiles[key] = BotProfile(name)
        return self._bot_profiles[key]

    def get_profile(self, name: str) -> BotProfile | None:
        return self._bot_profiles.get(name.lower())

    def unchecked_interactions(self, max_age: float = 3600) -> list[Interaction]:
        """Get interactions that haven't had their engagement checked yet."""
        cutoff = time.time() - max_age
        return [
            i for i in self._interactions
            if not i.checked and i.timestamp > cutoff
        ]

    def engagement_summary(self) -> str:
        """Summary of engagement patterns for the reflection prompt."""
        if not self._interactions:
            return "No interactions recorded yet."

        checked = [i for i in self._interactions if i.checked]
        if not checked:
            return "No engagement data collected yet."

        total = len(checked)
        got_replies = sum(1 for i in checked if i.reply_count > 0)
        avg_replies = sum(i.reply_count for i in checked) / total
        avg_upvotes = sum(i.upvotes for i in checked) / total

        # Best performing
        by_engagement = sorted(checked, key=lambda i: i.reply_count + i.upvotes, reverse=True)
        top = by_engagement[:3]

        lines = [
            f"Total tracked: {total}",
            f"Got replies: {got_replies}/{total} ({got_replies/total*100:.0f}%)",
            f"Avg replies: {avg_replies:.1f}",
            f"Avg upvotes: {avg_upvotes:.1f}",
            "",
            "Top performing:",
        ]
        for i in top:
            lines.append(
                f"  - [{i.action}] \"{i.our_text[:50]}\" → "
                f"{i.reply_count} replies, {i.upvotes} upvotes"
            )

        return "\n".join(lines)

    def bot_relationships_summary(self) -> str:
        """Summary of bot relationships for prompts."""
        if not self._bot_profiles:
            return "No bot relationships yet."

        profiles = sorted(
            self._bot_profiles.values(),
            key=lambda p: p.interaction_count,
            reverse=True,
        )[:10]

        lines: list[str] = []
        for p in profiles:
            topics = ", ".join(p.topics[-3:]) if p.topics else "general"
            lines.append(
                f"- {p.name}: {p.interaction_count} interactions, "
                f"responsiveness={p.responsiveness}, topics=[{topics}]"
            )
        return "\n".join(lines)

    def proactive_targeting_summary(self, feed_authors: set[str] | None = None) -> str:
        """Summary of top bots for proactive targeting in decisions.

        Highlights responsiveness, reply rate, topics, and feed presence.
        """
        if not self._bot_profiles:
            return ""

        # Sort by interaction count, take top 10
        profiles = sorted(
            self._bot_profiles.values(),
            key=lambda p: p.interaction_count,
            reverse=True,
        )[:10]

        feed_authors_lower = {a.lower() for a in (feed_authors or set())}

        lines: list[str] = []
        for p in profiles:
            if p.interaction_count < 1:
                continue

            parts = [f"**{p.name}**"]

            # Responsiveness and reply rate
            total_engagements = p.replied_to_us + p.no_response_count
            if total_engagements > 0:
                rate = p.replied_to_us / total_engagements * 100
                parts.append(f"reply rate: {rate:.0f}%")
            else:
                parts.append(f"responsiveness: {p.responsiveness}")

            # Topics
            if p.topics:
                topics = ", ".join(p.topics[-3:])
                parts.append(f"topics: [{topics}]")

            # Communication style
            if p.communication_style:
                parts.append(f"style: {p.communication_style}")

            # Personality summary (brief)
            if p.personality_summary:
                parts.append(f"personality: {p.personality_summary[:80]}")

            # Feed presence
            if feed_authors_lower and p.name.lower() in feed_authors_lower:
                parts.append("** IN YOUR FEED RIGHT NOW **")

            lines.append("- " + " | ".join(parts))

        return "\n".join(lines) if lines else ""

    def recent_insights(self, n: int = 5) -> str:
        """Recent learning insights for decision prompts."""
        recent = self._insights[-n:]
        if not recent:
            return "No insights yet."
        return "\n".join(f"- {i['insight']}" for i in recent)

    def bots_needing_profiling(self) -> list[BotProfile]:
        """Get bot profiles that should be analyzed by the LLM."""
        return [
            p for p in self._bot_profiles.values()
            if p.needs_profiling()
        ]

    def stats(self) -> dict[str, int]:
        return {
            "interactions": len(self._interactions),
            "bots_known": len(self._bot_profiles),
            "insights": len(self._insights),
            "checked": sum(1 for i in self._interactions if i.checked),
        }

    # --- Persistence ---

    def to_dict(self) -> dict[str, Any]:
        return {
            "interactions": [i.to_dict() for i in self._interactions[-200:]],
            "bot_profiles": {
                k: v.to_dict() for k, v in self._bot_profiles.items()
            },
            "insights": self._insights[-20:],
        }

    def load_dict(self, data: dict[str, Any]) -> None:
        self._interactions = [
            Interaction.from_dict(d) for d in data.get("interactions", [])
        ]
        self._bot_profiles = {
            k: BotProfile.from_dict(v)
            for k, v in data.get("bot_profiles", {}).items()
        }
        self._insights = data.get("insights", [])
