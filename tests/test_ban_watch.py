"""Tests for ban detection and tracking in MoltbookClient."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from velorum.moltbook.client import MoltbookClient


@pytest.fixture
def client(tmp_path):
    """Create a MoltbookClient without making real HTTP connections."""
    c = MoltbookClient(
        base_url="https://example.com/api/v1",
        api_key="test-key",
        ban_file=tmp_path / "ban.json",
    )
    return c


class TestBanDetection:
    """Test _check_for_ban parses various response shapes."""

    def test_top_level_banned_until(self, client):
        data = {
            "banned_until": "2099-01-01T00:00:00Z",
            "reason": "challenge_no_answer",
        }
        client._check_for_ban(data)
        assert client.is_banned
        assert client.ban_reason == "challenge_no_answer"

    def test_nested_under_agent(self, client):
        data = {
            "agent": {
                "name": "TestBot",
                "banned_until": "2099-01-01T00:00:00Z",
                "ban_reason": "spam",
            }
        }
        client._check_for_ban(data)
        assert client.is_banned
        assert client.ban_reason == "spam"

    def test_status_banned(self, client):
        data = {
            "status": "banned",
            "banned_until": "2099-01-01T00:00:00Z",
            "reason": "abuse",
        }
        client._check_for_ban(data)
        assert client.is_banned
        assert client.ban_reason == "abuse"

    def test_ban_until_alternate_key(self, client):
        data = {"ban_until": "2099-01-01T00:00:00Z", "reason": "test"}
        client._check_for_ban(data)
        assert client.is_banned

    def test_no_ban_data(self, client):
        data = {"status": "active", "agent": {"name": "TestBot"}}
        client._check_for_ban(data)
        assert not client.is_banned

    def test_expired_ban_not_banned(self, client):
        """A ban in the past should not register as banned."""
        data = {
            "banned_until": "2020-01-01T00:00:00Z",
            "reason": "old_ban",
        }
        client._check_for_ban(data)
        assert not client.is_banned

    def test_malformed_timestamp_assumes_1h(self, client):
        """Unparseable timestamp should assume 1-hour ban."""
        data = {"banned_until": "not-a-date", "reason": "test"}
        client._check_for_ban(data)
        assert client.is_banned
        assert client.ban_remaining_seconds() > 3500  # ~1 hour

    def test_moltbook_timestamp_with_colon_millis(self, client):
        """Handle Moltbook's format: 2026-02-20T20:27:22:751Z."""
        future = datetime.now(timezone.utc) + timedelta(hours=10)
        # Format with colon instead of dot for millis (Moltbook quirk)
        ts = future.strftime("%Y-%m-%dT%H:%M:%S") + ":751Z"
        data = {"banned_until": ts, "reason": "test"}
        client._check_for_ban(data)
        assert client.is_banned
        assert client.ban_remaining_seconds() > 35000  # ~10 hours


class TestBanState:
    """Test is_banned, ban_remaining_seconds, clear_ban."""

    def test_not_banned_by_default(self, client):
        assert not client.is_banned
        assert client.ban_remaining_seconds() == 0.0
        assert client.ban_reason == ""

    def test_ban_remaining_seconds(self, client):
        client._ban_until = datetime.now(timezone.utc) + timedelta(hours=2)
        client._ban_reason = "test"
        remaining = client.ban_remaining_seconds()
        assert 7100 < remaining < 7300  # ~2 hours

    def test_is_banned_auto_clears_when_expired(self, client):
        client._ban_until = datetime.now(timezone.utc) - timedelta(seconds=1)
        client._ban_reason = "old"
        assert not client.is_banned
        assert client._ban_until is None
        assert client._ban_reason == ""

    def test_clear_ban(self, client):
        client._ban_until = datetime.now(timezone.utc) + timedelta(hours=1)
        client._ban_reason = "test"
        assert client.is_banned
        client.clear_ban()
        assert not client.is_banned
        assert client.ban_reason == ""

    def test_ban_reason_empty_when_not_banned(self, client):
        client._ban_until = None
        client._ban_reason = "leftover"
        assert client.ban_reason == ""


class TestBanStatusField:
    """Test status field 'banned' triggers ban detection."""

    def test_status_banned_no_expiry(self, client):
        """Status=banned with no timestamp should still set a ban."""
        data = {"status": "banned"}
        client._check_for_ban(data)
        assert client.is_banned
        # Should default to ~1h
        assert client.ban_remaining_seconds() > 3500

    def test_status_active_no_ban(self, client):
        data = {"status": "active"}
        client._check_for_ban(data)
        assert not client.is_banned
