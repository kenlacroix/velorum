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


class TestExtractJson:
    def test_clean_json(self):
        raw = '{"action": "OBSERVE", "confidence": 3, "reasoning": "nothing"}'
        result = Brain._extract_json(raw)
        assert result["action"] == "OBSERVE"

    def test_json_with_trailing_text(self):
        raw = '{"action": "RESPOND", "confidence": 8, "reasoning": "good"}\n\nHere is my analysis...'
        result = Brain._extract_json(raw)
        assert result["action"] == "RESPOND"

    def test_json_with_code_fences(self):
        raw = '```json\n{"action": "POST", "confidence": 9, "reasoning": "worth it"}\n```'
        result = Brain._extract_json(raw)
        assert result["action"] == "POST"

    def test_json_with_leading_prose(self):
        raw = 'Here is my decision:\n{"action": "OBSERVE", "confidence": 5, "reasoning": "skip"}'
        result = Brain._extract_json(raw)
        assert result["action"] == "OBSERVE"

    def test_no_json_raises(self):
        with pytest.raises(Exception):
            Brain._extract_json("no json here at all")

    def test_json_with_nested_braces(self):
        raw = '{"action": "RESPOND", "trait_adjustments": {"valence": {"delta": 0.1}}, "reasoning": "ok"}'
        result = Brain._extract_json(raw)
        assert result["trait_adjustments"]["valence"]["delta"] == 0.1

    def test_json_with_braces_in_strings(self):
        raw = '{"reasoning": "use {curly} braces", "action": "OBSERVE", "confidence": 3}'
        result = Brain._extract_json(raw)
        assert result["action"] == "OBSERVE"
