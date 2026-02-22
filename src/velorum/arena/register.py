"""Interactive Agent Arena registration flow."""

from __future__ import annotations

import asyncio
import sys


async def register_arena() -> None:
    """Interactive Agent Arena registration.

    Steps:
    1. Prompt for X handle and agent name
    2. POST /auth/register to get verification code
    3. User tweets the code
    4. Poll POST /auth/verify until tweet is found or user quits
    """
    import httpx

    base_url = "https://api.agentarena.chat/api/v1"

    print("=== Agent Arena Registration ===")
    print()
    x_handle = input("Enter your agent's X (Twitter) handle: ").strip()
    if not x_handle:
        print("Error: X handle is required")
        sys.exit(1)
    # Strip @ prefix — API expects bare handle
    if x_handle.startswith("@"):
        x_handle = x_handle[1:]

    agent_name = input("Enter a display name for your agent: ").strip()
    if not agent_name:
        print("Error: Agent name is required")
        sys.exit(1)

    print(f"\nRegistering @{x_handle} ({agent_name}) with Agent Arena...")

    async with httpx.AsyncClient(base_url=base_url, timeout=30.0) as http:
        # Step 1: Register
        try:
            resp = await http.post(
                "/auth/register",
                json={"xHandle": x_handle, "name": agent_name},
            )
            if resp.status_code not in (200, 201):
                print(f"Registration failed: {resp.status_code} — {resp.text[:300]}")
                sys.exit(1)
            data = resp.json()
        except Exception as e:
            print(f"Registration request failed: {e}")
            sys.exit(1)

        print(f"\nRegistration response: {data}")

        verification_code = (
            data.get("verificationCode")
            or data.get("verification_code")
            or data.get("code")
            or ""
        )
        if not verification_code:
            print(f"No verification code in response")
            sys.exit(1)

        profile_id = data.get("profileId", "unknown")
        print(f"\nProfile ID: {profile_id}")
        print(f"Verification code: {verification_code}")

        # Show instructions from the API if available, otherwise default
        instructions = data.get("instructions", "")
        if instructions:
            print(f"\n{instructions}")
        else:
            print(f"\nTweet the following from @{x_handle}:")
            print(f'  Verifying my agent on @AgentArena_chat - Code: {verification_code}')

        print()
        print("Make sure your tweet contains:")
        print(f'  1. "@AgentArena_chat" (mention)')
        print(f'  2. "{verification_code}" (your code)')
        print(f'  3. Posted from @{x_handle}')
        print()
        input("Press Enter after you've posted the tweet to start polling...")

        # Step 2: Poll verify endpoint until success or user quits
        print("\nPolling for tweet verification (Ctrl+C to stop)...")
        print(f"  Handle: @{x_handle}")
        print(f"  Code: {verification_code}")
        print()

        attempt = 0
        poll_interval = 15  # seconds between attempts

        try:
            while True:
                attempt += 1
                print(f"[Attempt {attempt}] Checking for tweet...", end=" ", flush=True)

                try:
                    resp = await http.post(
                        "/auth/verify",
                        json={"xHandle": x_handle, "verificationCode": verification_code},
                    )
                    data = resp.json()
                    status = data.get("status", "")
                    message = data.get("message", "")

                    print(f"HTTP {resp.status_code} | status={status}")
                    if message:
                        print(f"         Message: {message}")

                    # Success — got API key
                    if resp.status_code in (200, 201):
                        api_key = (
                            data.get("apiKey")
                            or data.get("api_key")
                            or data.get("key")
                            or ""
                        )
                        if api_key:
                            print(f"\n{'=' * 50}")
                            print(f"Registration successful!")
                            print(f"{'=' * 50}")
                            print(f"\nAdd this to your .env file:")
                            print(f"\n  ARENA_API_KEY={api_key}")
                            print(f"  ARENA_ENABLED=true")
                            print(f"\nThen restart Velorum to begin using Agent Arena.")
                            return

                        # 200/201 but no key — check if status says verified
                        if status == "verified" or status == "active":
                            print(f"\nVerified but no API key in response: {data}")
                            print("Check the Agent Arena dashboard for your key.")
                            return

                    # Still pending — keep polling
                    if status == "pending" or resp.status_code == 202:
                        print(f"         Retrying in {poll_interval}s...")
                        await asyncio.sleep(poll_interval)
                        continue

                    # Unexpected status — show full response and keep trying
                    print(f"         Full response: {data}")
                    print(f"         Retrying in {poll_interval}s...")
                    await asyncio.sleep(poll_interval)

                except httpx.HTTPError as e:
                    print(f"HTTP error: {e}")
                    print(f"         Retrying in {poll_interval}s...")
                    await asyncio.sleep(poll_interval)

        except KeyboardInterrupt:
            print(f"\n\nStopped after {attempt} attempts.")
            print(f"\nYou can resume verification later by running:")
            print(f"  python3 -m velorum arena-register")
            print(f"\nOr manually call the verify endpoint:")
            print(f'  curl -X POST {base_url}/auth/verify \\')
            print(f'    -H "Content-Type: application/json" \\')
            print(f'    -d \'{{"xHandle": "{x_handle}", "verificationCode": "{verification_code}"}}\'')
