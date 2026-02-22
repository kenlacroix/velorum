"""Tests for the Agent Arena client."""

from unittest.mock import AsyncMock, patch

import httpx
import pytest

from velorum.arena.client import AgentArenaClient


@pytest.fixture
def client():
    return AgentArenaClient(
        base_url="https://api.agentarena.chat/api/v1",
        api_key="ak_test_key",
        timeout=5,
    )


class TestAgentArenaClient:
    def test_init(self, client):
        assert client._api_key == "ak_test_key"
        assert client._jwt is None
        assert not client.is_authenticated

    def test_is_authenticated_false_without_jwt(self, client):
        assert not client.is_authenticated

    def test_is_authenticated_true_with_fresh_jwt(self, client):
        import time

        client._jwt = "eyJhbGciOiJIUzI1NiJ9.test"
        client._jwt_obtained_at = time.time()
        assert client.is_authenticated

    def test_is_authenticated_false_with_stale_jwt(self, client):
        import time

        client._jwt = "eyJhbGciOiJIUzI1NiJ9.test"
        client._jwt_obtained_at = time.time() - 4000  # expired
        assert not client.is_authenticated

    def test_build_headers_no_jwt(self, client):
        headers = client._build_headers()
        assert "Authorization" not in headers
        assert headers["Content-Type"] == "application/json"

    def test_build_headers_with_jwt(self, client):
        client._jwt = "test_token"
        headers = client._build_headers()
        assert headers["Authorization"] == "Bearer test_token"
