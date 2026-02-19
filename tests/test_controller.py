"""Tests for the sovereign controller."""

from pathlib import Path
from unittest.mock import MagicMock

from velorum.config import Settings
from velorum.controller import Controller
from velorum.memory import Memory
from velorum.moltbook.models import Decision


def _make_controller(tmp_path: Path) -> tuple[Controller, Memory]:
    settings = Settings(
        confidence_threshold=7,
        max_responses_per_hour=2,
        memory_file=tmp_path / "memory.json",
    )
    memory = Memory(persist_path=settings.memory_file)
    controller = Controller(settings=settings, memory=memory)
    return controller, memory


def test_observe_always_passes(tmp_path):
    controller, _ = _make_controller(tmp_path)
    decision = Decision(
        action="OBSERVE", post_id=None, confidence=0,
        reasoning="Nothing interesting", response_text=None,
    )
    assert controller.validate(decision) is True


def test_low_confidence_blocked(tmp_path):
    controller, _ = _make_controller(tmp_path)
    decision = Decision(
        action="RESPOND", post_id="abc", confidence=5,
        reasoning="Meh", response_text="Hello",
    )
    assert controller.validate(decision) is False


def test_high_confidence_passes(tmp_path):
    controller, _ = _make_controller(tmp_path)
    decision = Decision(
        action="RESPOND", post_id="abc", confidence=8,
        reasoning="Good post", response_text="Great point!",
    )
    assert controller.validate(decision) is True


def test_dedup_blocks_repeat(tmp_path):
    controller, memory = _make_controller(tmp_path)
    first = Decision(
        action="RESPOND", post_id="abc", confidence=9,
        reasoning="Good", response_text="Hello",
    )
    memory.record_decision(first)

    second = Decision(
        action="RESPOND", post_id="abc", confidence=9,
        reasoning="Again", response_text="Hello again",
    )
    assert controller.validate(second) is False


def test_missing_response_text_blocked(tmp_path):
    controller, _ = _make_controller(tmp_path)
    decision = Decision(
        action="RESPOND", post_id="abc", confidence=9,
        reasoning="Good", response_text=None,
    )
    assert controller.validate(decision) is False


def test_rate_limit_blocks_after_max(tmp_path):
    controller, _ = _make_controller(tmp_path)
    # Simulate 2 prior responses
    controller.record_response()
    controller.record_response()

    decision = Decision(
        action="RESPOND", post_id="new", confidence=9,
        reasoning="Good", response_text="Hello",
    )
    assert controller.validate(decision) is False
