"""Learning journal — tracks engagement outcomes and evolves strategy.

Records what Velorum says, how others respond, and what patterns
emerge over time. Insights are fed back into decision and reflection
prompts so the bot's behavior evolves.
"""

from __future__ import annotations

import logging
import math
import re
import time
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Style-tag inference (pure heuristic, no LLM)
# ---------------------------------------------------------------------------

_QUESTION_RE = re.compile(r"\?")
_DISAGREE_RE = re.compile(r"\b(but|however|disagree|although|on the other hand)\b", re.IGNORECASE)
_HUMOR_RE = re.compile(r"\b(haha|lol|lmao|rofl)\b|!{2,}", re.IGNORECASE)
_SPECULATIVE_RE = re.compile(r"\b(what if|imagine|hypothetically|suppose)\b", re.IGNORECASE)
_ANALYTICAL_RE = re.compile(r"\b(evidence|data|analysis|statistic|measure|correlation)\b", re.IGNORECASE)


def infer_style_tags(text: str, action: str = "") -> list[str]:
    """Detect style tags from text content using cheap heuristics."""
    tags: list[str] = []
    if _QUESTION_RE.search(text):
        tags.append("question")
    if _DISAGREE_RE.search(text):
        tags.append("disagreement")
    if _HUMOR_RE.search(text):
        tags.append("humor")
    if _SPECULATIVE_RE.search(text):
        tags.append("speculative")
    if _ANALYTICAL_RE.search(text):
        tags.append("analytical")

    word_count = len(text.split())
    if word_count <= 15:
        tags.append("concise")
    elif word_count >= 60:
        tags.append("verbose")

    return tags


# ---------------------------------------------------------------------------
# WeightedInsight
# ---------------------------------------------------------------------------


@dataclass
class WeightedInsight:
    """An insight with a weight that compounds via reinforcement."""

    insight: str
    source: str = ""
    timestamp: float = 0.0
    weight: float = 1.0
    reinforcement_count: int = 0
    linked_interaction_ids: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.timestamp == 0.0:
            self.timestamp = time.time()

    def to_dict(self) -> dict[str, Any]:
        return {
            "insight": self.insight,
            "source": self.source,
            "timestamp": self.timestamp,
            "weight": self.weight,
            "reinforcement_count": self.reinforcement_count,
            "linked_interaction_ids": self.linked_interaction_ids,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> WeightedInsight:
        return cls(
            insight=d.get("insight", ""),
            source=d.get("source", ""),
            timestamp=d.get("timestamp", 0.0),
            weight=d.get("weight", 1.0),
            reinforcement_count=d.get("reinforcement_count", 0),
            linked_interaction_ids=d.get("linked_interaction_ids", []),
        )


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
        style_tags: list[str] | None = None,
        submolt: str = "",
        tone: str = "",
        confidence: int = 0,
        platform: str = "",  # "moltbook", "arena", or "" for legacy
        active_insight_sources: list[str] | None = None,
    ) -> None:
        self.timestamp = timestamp or time.time()
        self.post_id = post_id
        self.action = action
        self.our_text = our_text
        self.target_author = target_author
        self.topic_hint = topic_hint
        # Attribution
        self.style_tags: list[str] = style_tags or []
        self.submolt: str = submolt
        self.tone: str = tone
        self.confidence: int = confidence
        self.platform: str = platform
        self.active_insight_sources: list[str] = active_insight_sources or []
        # Filled in later when we check engagement
        self.reply_count: int = 0
        self.reply_authors: list[str] = []
        self.upvotes: int = 0
        self.checked: bool = False

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
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
        # Only include attribution fields if populated (compact serialization)
        if self.style_tags:
            d["style_tags"] = self.style_tags
        if self.submolt:
            d["submolt"] = self.submolt
        if self.tone:
            d["tone"] = self.tone
        if self.confidence:
            d["confidence"] = self.confidence
        if self.platform:
            d["platform"] = self.platform
        if self.active_insight_sources:
            d["active_insight_sources"] = self.active_insight_sources
        return d

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> Interaction:
        i = cls(
            timestamp=d.get("timestamp", 0.0),
            post_id=d.get("post_id", ""),
            action=d.get("action", ""),
            our_text=d.get("our_text", ""),
            target_author=d.get("target_author", ""),
            topic_hint=d.get("topic_hint", ""),
            style_tags=d.get("style_tags", []),
            submolt=d.get("submolt", ""),
            tone=d.get("tone", ""),
            confidence=d.get("confidence", 0),
            platform=d.get("platform", ""),
            active_insight_sources=d.get("active_insight_sources", []),
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

    MAX_INSIGHTS = 30
    INSIGHT_DECAY_FACTOR = 0.95
    REPLY_REINFORCEMENT = 0.1
    UPVOTE_REINFORCEMENT = 0.05
    INSIGHT_WEIGHT_FLOOR = 0.1

    def __init__(self) -> None:
        self._interactions: list[Interaction] = []
        self._bot_profiles: dict[str, BotProfile] = {}
        self._insights: list[WeightedInsight] = []

    # --- Recording ---

    def record_interaction(
        self,
        *,
        post_id: str,
        action: str,
        our_text: str,
        target_author: str = "",
        topic_hint: str = "",
        style_tags: list[str] | None = None,
        submolt: str = "",
        tone: str = "",
        confidence: int = 0,
        platform: str = "",
        active_insight_sources: list[str] | None = None,
    ) -> None:
        """Record an outgoing action (comment, post, reply)."""
        self._interactions.append(Interaction(
            post_id=post_id,
            action=action,
            our_text=our_text,
            target_author=target_author,
            topic_hint=topic_hint,
            style_tags=style_tags,
            submolt=submolt,
            tone=tone,
            confidence=confidence,
            platform=platform,
            active_insight_sources=active_insight_sources,
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
                # Reinforce linked insights based on engagement
                self.reinforce_insights(post_id, reply_count, upvotes)
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
        # Link to the last 5 unchecked interaction post_ids
        linked_ids = [
            i.post_id for i in self._interactions
            if not i.checked and i.post_id
        ][-5:]

        self._insights.append(WeightedInsight(
            insight=insight,
            source=source,
            weight=1.0,
            linked_interaction_ids=linked_ids,
        ))
        # Prune by dropping lowest-weight insights when over capacity
        if len(self._insights) > self.MAX_INSIGHTS:
            self._insights.sort(key=lambda w: w.weight, reverse=True)
            self._insights = self._insights[:self.MAX_INSIGHTS]
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
        """Top learning insights for decision prompts, sorted by weight."""
        if not self._insights:
            return "No insights yet."
        ranked = sorted(self._insights, key=lambda w: w.weight, reverse=True)[:n]
        lines: list[str] = []
        for w in ranked:
            if w.weight >= 2.0:
                label = "strong"
            elif w.weight >= 0.5:
                label = "moderate"
            else:
                label = "weak"
            lines.append(f"- [{label}] {w.insight}")
        return "\n".join(lines)

    def diverse_insights(self, n: int = 5) -> str:
        """Top insights, deduplicated by theme to avoid feedback loops."""
        if not self._insights:
            return "No insights yet."
        ranked = sorted(self._insights, key=lambda w: w.weight, reverse=True)

        selected: list[WeightedInsight] = []
        seen_keywords: set[str] = set()
        for w in ranked:
            # Extract key words (4+ chars, lowered)
            words = {word.lower() for word in w.insight.split() if len(word) >= 4}
            # If >50% of words already covered by a selected insight, skip
            if seen_keywords and len(words & seen_keywords) / max(len(words), 1) > 0.5:
                continue
            selected.append(w)
            seen_keywords |= words
            if len(selected) >= n:
                break

        lines: list[str] = []
        for w in selected:
            label = "strong" if w.weight >= 2.0 else "moderate" if w.weight >= 0.5 else "weak"
            lines.append(f"- [{label}] {w.insight}")
        return "\n".join(lines) or "No insights yet."

    def decay_insights(self) -> None:
        """Apply decay to all insight weights, removing those below floor."""
        for w in self._insights:
            w.weight *= self.INSIGHT_DECAY_FACTOR
        self._insights = [
            w for w in self._insights
            if w.weight >= self.INSIGHT_WEIGHT_FLOOR
        ]

    def reinforce_insights(
        self,
        post_id: str,
        reply_count: int = 0,
        upvotes: int = 0,
    ) -> None:
        """Boost weight of insights linked to a post based on engagement.

        Primary reinforcement: insights whose linked_interaction_ids include the post.
        Secondary attribution reinforcement: insights whose source was active when the
        decision was made (smaller boost — 0.05/reply, 0.02/upvote).
        """
        boost = reply_count * self.REPLY_REINFORCEMENT + upvotes * self.UPVOTE_REINFORCEMENT
        if boost <= 0:
            return

        # Find the interaction for this post to get active_insight_sources
        active_sources: list[str] = []
        for interaction in reversed(self._interactions):
            if interaction.post_id == post_id:
                active_sources = interaction.active_insight_sources
                break

        for w in self._insights:
            if post_id in w.linked_interaction_ids:
                w.weight = min(w.weight + boost, 3.0)
                w.reinforcement_count += 1
            elif active_sources and w.source in active_sources:
                # Secondary attribution boost (smaller)
                secondary = reply_count * 0.05 + upvotes * 0.02
                if secondary > 0:
                    w.weight = min(w.weight + secondary, 3.0)
                    w.reinforcement_count += 1

    def attributed_engagement_summary(self) -> str:
        """Aggregate engagement by style tag and submolt."""
        checked = [i for i in self._interactions if i.checked]
        if not checked:
            return ""

        # By style tag
        tag_data: dict[str, list[float]] = {}
        for i in checked:
            eng = i.reply_count + i.upvotes
            for tag in i.style_tags:
                tag_data.setdefault(tag, []).append(eng)

        # By submolt
        submolt_data: dict[str, list[float]] = {}
        for i in checked:
            if i.submolt:
                eng = i.reply_count + i.upvotes
                submolt_data.setdefault(i.submolt, []).append(eng)

        if not tag_data and not submolt_data:
            return ""

        lines: list[str] = []
        if tag_data:
            lines.append("Style performance:")
            for tag, vals in sorted(tag_data.items(), key=lambda t: sum(t[1]) / len(t[1]), reverse=True):
                avg = sum(vals) / len(vals)
                lines.append(f"  '{tag}': {avg:.1f} avg engagement ({len(vals)} samples)")
        if submolt_data:
            lines.append("Submolt performance:")
            for sub, vals in sorted(submolt_data.items(), key=lambda t: sum(t[1]) / len(t[1]), reverse=True):
                avg = sum(vals) / len(vals)
                lines.append(f"  '{sub}': {avg:.1f} avg engagement ({len(vals)} samples)")

        return "\n".join(lines)

    def total_interactions(self) -> int:
        """Return the total number of recorded interactions."""
        return len(self._interactions)

    def entropy_score(self) -> float:
        """Compute Shannon entropy of submolt distribution over last 30 interactions.

        Returns a float 0–1 where 0 = maximally concentrated (rut) and 1 = maximally diverse.
        """
        recent = [i for i in self._interactions[-30:] if i.submolt]
        if not recent:
            return 1.0  # No data — treat as healthy

        counts: dict[str, int] = {}
        for i in recent:
            counts[i.submolt] = counts.get(i.submolt, 0) + 1

        total = len(recent)
        n_buckets = len(counts)
        if n_buckets <= 1:
            return 0.0

        entropy = 0.0
        for c in counts.values():
            p = c / total
            if p > 0:
                entropy -= p * math.log2(p)

        max_entropy = math.log2(n_buckets)
        return entropy / max_entropy if max_entropy > 0 else 0.0

    def entropy_warning(self) -> str:
        """Return a warning string if submolt entropy is low, else empty string."""
        recent = [i for i in self._interactions[-30:] if i.submolt]
        if not recent:
            return ""

        score = self.entropy_score()
        if score > 0.35:
            return ""

        counts: dict[str, int] = {}
        for i in recent:
            counts[i.submolt] = counts.get(i.submolt, 0) + 1
        top = max(counts, key=lambda k: counts[k])
        n = len(recent)
        return (
            f"⚠ ENTROPY WARNING: Last {n} actions concentrated on [{top}]. "
            f"You are in a rut. Explore a different community, topic, or style this cycle."
        )

    _ANTONYM_PAIRS = [
        ("short", "long"),
        ("short", "detailed"),
        ("short", "verbose"),
        ("brief", "detailed"),
        ("brief", "verbose"),
        ("concise", "verbose"),
        ("concise", "detailed"),
        ("aggressive", "selective"),
        ("aggressive", "cautious"),
        ("frequent", "rare"),
        ("question", "statement"),
        ("humor", "serious"),
        ("simple", "complex"),
        ("positive", "critical"),
        ("agree", "disagree"),
        ("challenge", "agree"),
    ]

    def find_contradictions(self) -> list[tuple[WeightedInsight, WeightedInsight]]:
        """Find pairs of high-weight insights that may contradict each other.

        Uses keyword heuristics: pairs that share a topic word but use antonymous signals.
        Only checks insights with weight > 0.7. Returns at most 3 pairs (highest weight first).
        """
        high_weight = [w for w in self._insights if w.weight > 0.7]
        if len(high_weight) < 2:
            return []

        def _key_words(text: str) -> set[str]:
            return {w.lower() for w in text.split() if len(w) >= 4}

        def _has_antonym_conflict(a: str, b: str) -> bool:
            a_lower = a.lower()
            b_lower = b.lower()
            for pos, neg in self._ANTONYM_PAIRS:
                if pos in a_lower and neg in b_lower:
                    return True
                if neg in a_lower and pos in b_lower:
                    return True
            return False

        conflicts: list[tuple[WeightedInsight, WeightedInsight]] = []
        for i in range(len(high_weight)):
            for j in range(i + 1, len(high_weight)):
                a, b = high_weight[i], high_weight[j]
                words_a = _key_words(a.insight)
                words_b = _key_words(b.insight)
                shared = words_a & words_b
                if shared and _has_antonym_conflict(a.insight, b.insight):
                    conflicts.append((a, b))
                    if len(conflicts) >= 3:
                        return conflicts

        # Sort by combined weight descending
        conflicts.sort(key=lambda p: p[0].weight + p[1].weight, reverse=True)
        return conflicts

    def merge_insights(
        self,
        keep_source: str,
        supersede_source: str,
        merged_text: str,
    ) -> None:
        """Replace keep insight text with merged_text and remove superseded insight."""
        for w in self._insights:
            if w.source == keep_source:
                w.insight = merged_text
                break
        self._insights = [w for w in self._insights if w.source != supersede_source]

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
            "insights": [w.to_dict() for w in self._insights[-self.MAX_INSIGHTS:]],
        }

    def load_dict(self, data: dict[str, Any]) -> None:
        self._interactions = [
            Interaction.from_dict(d) for d in data.get("interactions", [])
        ]
        self._bot_profiles = {
            k: BotProfile.from_dict(v)
            for k, v in data.get("bot_profiles", {}).items()
        }
        raw_insights = data.get("insights", [])
        self._insights = [WeightedInsight.from_dict(d) for d in raw_insights]
