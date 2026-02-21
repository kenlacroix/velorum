"""Environment-based settings via Pydantic."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}

    # LLM provider
    llm_provider: Literal["anthropic", "openai"] = "anthropic"
    llm_model: str = "claude-sonnet-4-5-20250929"
    anthropic_api_key: str = ""
    openai_api_key: str = ""

    # Moltbook
    moltbook_api_key: str = ""
    moltbook_app_key: str = ""
    moltbook_base_url: str = "https://www.moltbook.com/api/v1"

    # LLM
    llm_max_tokens: int = 1024

    # HTTP
    http_timeout_seconds: int = 30

    # Feed
    feed_limit: int = 15

    # Agent behavior — comments
    confidence_threshold: int = 7
    engagement_check_interval_cycles: int = 3
    max_responses_per_hour: int = 2
    cycle_interval_seconds: int = 300
    reflection_interval_cycles: int = 11

    # Comment scanning — fetch comments from top posts for engagement
    comment_scan_limit: int = 3

    # Agent behavior — original posts
    max_posts_per_day: int = 3
    min_post_interval_seconds: int = 1800  # 30 minutes between posts
    posting_enabled: bool = True

    # Conversations — reply threading
    max_thread_depth: int = 3
    reply_cooldown_seconds: int = 120
    conversation_check_interval: int = 120  # seconds between checking a thread
    max_active_conversations: int = 10
    stale_conversation_hours: int = 24
    max_conversation_checks_per_cycle: int = 3
    max_engagement_checks_per_cycle: int = 3

    # Agent name (for identifying our own comments)
    agent_name: str = "Velorum"

    # Memory persistence
    memory_file: Path = Path("data/memory.json")

    # Soul file
    soul_file: Path = Path("docs/SOUL.md")

    # Mission system
    mission_file: Path = Path("data/mission.json")
    mission_review_interval_cycles: int = 7

    # Strategy system
    strategy_file: Path = Path("data/strategy.json")
    strategy_update_interval_cycles: int = 47

    # Bot profiling
    profiling_interval_cycles: int = 13

    # Experiments
    experiments_file: Path = Path("data/experiments.json")

    # Submolts
    submolts_file: Path = Path("data/submolts.json")
    max_subscribed_submolts: int = 20
    submolt_discovery_interval_cycles: int = 200


def load_settings() -> Settings:
    return Settings()
