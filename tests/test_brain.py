"""Tests for the brain decision engine."""

import json
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from velorum.brain import Brain
from velorum.llm.base import LLMProvider
from velorum.memory import Memory
from velorum.moltbook.models import Post


@pytest.fixture
def memory(tmp_path):
    return Memory(persist_path=tmp_path / "memory.json")


@pytest.fixture
def mock_llm():
    llm = AsyncMock(spec=LLMProvider)
    return llm


@pytest.fixture
def brain(mock_llm, memory):
    return Brain(llm=mock_llm, memory=memory, soul="I am Velorum.")


@pytest.fixture
def sample_posts():
    return [
        Post(id="1", author="bot_a", title="Hello world", content="First post!"),
        Post(id="2", author="bot_b", title="AI thoughts", content="Interesting discussion."),
    ]


@pytest.mark.asyncio
async def test_decide_respond(brain, mock_llm, sample_posts):
    mock_llm.complete.return_value = json.dumps({
        "action": "RESPOND",
        "post_id": "2",
        "confidence": 8,
        "reasoning": "Interesting discussion worth joining",
        "response_text": "Great point about AI.",
    })
    decision = await brain.decide(sample_posts)
    assert decision is not None
    assert decision.action == "RESPOND"
    assert decision.post_id == "2"
    assert decision.confidence == 8


@pytest.mark.asyncio
async def test_decide_observe(brain, mock_llm, sample_posts):
    mock_llm.complete.return_value = json.dumps({
        "action": "OBSERVE",
        "post_id": None,
        "confidence": 3,
        "reasoning": "Nothing interesting",
        "response_text": None,
    })
    decision = await brain.decide(sample_posts)
    assert decision is not None
    assert decision.action == "OBSERVE"


@pytest.mark.asyncio
async def test_decide_returns_none_on_bad_json(brain, mock_llm, sample_posts):
    mock_llm.complete.return_value = "This is not JSON"
    decision = await brain.decide(sample_posts)
    assert decision is None


@pytest.mark.asyncio
async def test_reflect_success(brain, mock_llm):
    mock_llm.complete.return_value = json.dumps({
        "behavior_assessment": "Balanced engagement so far.",
        "adjustment_recommendation": "Continue current approach.",
    })
    reflection = await brain.reflect()
    assert reflection is not None
    assert "Balanced" in reflection.behavior_assessment


@pytest.mark.asyncio
async def test_reflect_returns_none_on_bad_json(brain, mock_llm):
    mock_llm.complete.return_value = "not json"
    reflection = await brain.reflect()
    assert reflection is None
