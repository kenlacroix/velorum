"""Interactive setup wizard for first-time Velorum configuration."""

from __future__ import annotations

import asyncio
from pathlib import Path

import httpx

from velorum.moltbook.auth import register_agent

MOLTBOOK_BASE_URL = "https://www.moltbook.com/api/v1"

DEFAULT_MODELS = {
    "anthropic": "claude-sonnet-4-5-20250929",
    "openai": "gpt-4o",
}


def _prompt(label: str, default: str = "") -> str:
    """Prompt the user for input with an optional default."""
    suffix = f" [{default}]" if default else ""
    value = input(f"{label}{suffix}: ").strip()
    return value or default


def _confirm(label: str, default: bool = True) -> bool:
    hint = "Y/n" if default else "y/N"
    value = input(f"{label} [{hint}]: ").strip().lower()
    if not value:
        return default
    return value.startswith("y")


def run_setup() -> None:
    """Run the interactive setup wizard."""
    env_path = Path(".env")

    print()
    print("=" * 44)
    print("         Velorum Setup")
    print("=" * 44)
    print()

    # Check for existing .env
    if env_path.exists():
        if not _confirm("A .env file already exists. Overwrite?", default=False):
            print("Setup cancelled.")
            return

    # 1. Bot name & description
    print("-- Agent Identity --")
    name = ""
    while not name:
        name = _prompt("Agent name")
        if not name:
            print("  Name cannot be empty.")
    description = _prompt("Short description", "A Velorum-powered social agent")
    print()

    # 2. Moltbook registration
    print("-- Moltbook Registration --")
    api_key = ""
    claim_url = ""
    registered = False
    while not registered:
        try:
            print(f"Registering '{name}' on Moltbook...")
            result = asyncio.run(register_agent(MOLTBOOK_BASE_URL, name, description))
            agent = result.get("agent", result)
            api_key = agent.get("api_key", "")
            claim_url = agent.get("claim_url", "")
            verification_code = agent.get("verification_code", "")
            print("  Registration successful!")
            if claim_url:
                print()
                print(f"  >>> Claim your agent: {claim_url}")
                print(f"  >>> Visit this URL to complete setup on Moltbook.")
                if verification_code:
                    print(f"  >>> Verification code: {verification_code}")
                print()
            registered = True
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 409:
                print(f"  Name '{name}' is already taken on Moltbook.")
                choice = _prompt("  Try a different name, or enter API key manually? (name / key)", "name").lower()
                if choice.startswith("k"):
                    api_key = _prompt("  MOLTBOOK_API_KEY")
                    registered = True
                else:
                    name = ""
                    while not name:
                        name = _prompt("  New agent name")
                        if not name:
                            print("    Name cannot be empty.")
            else:
                print(f"  Registration failed: {exc}")
                print("  You can enter your Moltbook API key manually.")
                api_key = _prompt("  MOLTBOOK_API_KEY (leave blank to fill later)")
                registered = True
        except Exception as exc:
            print(f"  Registration failed: {exc}")
            print("  You can enter your Moltbook API key manually.")
            api_key = _prompt("  MOLTBOOK_API_KEY (leave blank to fill later)")
            registered = True
    print()

    # 3. LLM provider
    print("-- LLM Configuration --")
    provider = ""
    while provider not in ("anthropic", "openai"):
        provider = _prompt("LLM provider (anthropic / openai)", "anthropic").lower()

    # 4. LLM API key
    llm_key = _prompt(f"{provider.upper()} API key")

    # 5. Model
    default_model = DEFAULT_MODELS[provider]
    model = _prompt("LLM model", default_model)
    print()

    # 6. Write .env
    anthropic_key = llm_key if provider == "anthropic" else ""
    openai_key = llm_key if provider == "openai" else ""

    env_contents = f"""\
# LLM Provider: "anthropic" or "openai"
LLM_PROVIDER={provider}

# API Keys
ANTHROPIC_API_KEY={anthropic_key}
OPENAI_API_KEY={openai_key}

# LLM Model
LLM_MODEL={model}

# Moltbook
MOLTBOOK_API_KEY={api_key}
MOLTBOOK_BASE_URL={MOLTBOOK_BASE_URL}

# Agent behavior
CONFIDENCE_THRESHOLD=7
MAX_RESPONSES_PER_HOUR=2
CYCLE_INTERVAL_SECONDS=300
REFLECTION_INTERVAL_CYCLES=10

# Memory persistence
MEMORY_FILE=data/memory.json
"""

    env_path.write_text(env_contents)

    # 7. Summary
    print("-- Setup Complete --")
    print(f"  Agent name:   {name}")
    print(f"  LLM provider: {provider}")
    print(f"  LLM model:    {model}")
    print(f"  .env written: {env_path.resolve()}")
    if claim_url:
        print()
        print(f"  Don't forget to claim your agent: {claim_url}")
    print()
    print("  Run your agent with:  python -m velorum")
    print()
