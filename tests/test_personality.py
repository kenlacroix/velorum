"""Tests for personality trait system."""

from __future__ import annotations

import json

from velorum.personality import (
    GUARDRAIL_THRESHOLD,
    HARD_CEILING,
    MAX_DELTA,
    MIN_DELTA,
    PersonalityEngine,
    PersonalityTraits,
    VISIBILITY_THRESHOLD,
)


def test_decay():
    """Verify 0.95 decay multiplication."""
    traits = PersonalityTraits()
    traits.valence = 0.5
    traits.assertiveness = -0.4
    traits.openness = 0.8
    traits.energy = -0.2

    traits.apply_decay(0.95)

    assert abs(traits.valence - 0.475) < 1e-9
    assert abs(traits.assertiveness - (-0.38)) < 1e-9
    assert abs(traits.openness - 0.76) < 1e-9
    assert abs(traits.energy - (-0.19)) < 1e-9


def test_adjustment_clamp():
    """Verify hard ceiling at ±0.85."""
    traits = PersonalityTraits()
    traits.valence = 0.8

    # Push past ceiling
    traits.apply_adjustment("valence", 0.2, "test")
    assert traits.valence == HARD_CEILING

    # Negative ceiling
    traits.assertiveness = -0.8
    traits.apply_adjustment("assertiveness", -0.2, "test")
    assert traits.assertiveness == -HARD_CEILING


def test_delta_clamp():
    """Verify single adjustment clamped to ±0.3."""
    traits = PersonalityTraits()
    traits.valence = 0.0

    # Try a delta of 0.5 — should be clamped to 0.3
    traits.apply_adjustment("valence", 0.5, "test")
    assert abs(traits.valence - MAX_DELTA) < 1e-9

    traits.energy = 0.0
    traits.apply_adjustment("energy", -0.5, "test")
    assert abs(traits.energy - (-MAX_DELTA)) < 1e-9


def test_small_delta_ignored():
    """Verify deltas < 0.05 are skipped by the engine."""
    engine = PersonalityEngine(persist_path=__import__("pathlib").Path("/tmp/test_personality_skip.json"))
    engine._traits.valence = 0.3

    engine.apply_reflection_update({
        "valence": {"delta": 0.04, "reasoning": "too small"},
        "energy": {"delta": 0.01, "reasoning": "tiny"},
    })

    # Neither should have changed
    assert engine._traits.valence == 0.3
    assert engine._traits.energy == 0.0


def test_guardrail_threshold():
    """Verify ±0.6 triggers warning in summary."""
    traits = PersonalityTraits()
    traits.valence = 0.7  # Above guardrail

    summary = traits.summary_for_prompt()
    assert "WARNING" in summary
    assert "valence" in summary.lower()

    # Below guardrail — no warning
    traits.valence = 0.3
    traits.assertiveness = 0.0
    traits.openness = 0.0
    traits.energy = 0.0
    summary = traits.summary_for_prompt()
    assert "WARNING" not in summary


def test_persistence_roundtrip():
    """Verify to_dict/from_dict preserves state."""
    traits = PersonalityTraits()
    traits.valence = 0.42
    traits.assertiveness = -0.33
    traits.openness = 0.1
    traits.energy = -0.7
    traits.update_history = [
        {"timestamp": 1.0, "trait": "valence", "delta": 0.1, "new_value": 0.42, "reasoning": "test"},
    ]

    d = traits.to_dict()
    restored = PersonalityTraits.from_dict(d)

    assert restored.valence == traits.valence
    assert restored.assertiveness == traits.assertiveness
    assert restored.openness == traits.openness
    assert restored.energy == traits.energy
    assert len(restored.update_history) == 1

    # Also test JSON round-trip
    json_str = json.dumps(d)
    from_json = PersonalityTraits.from_dict(json.loads(json_str))
    assert from_json.valence == traits.valence


def test_summary_hides_near_zero():
    """Verify traits with abs < 0.15 are not shown."""
    traits = PersonalityTraits()
    traits.valence = 0.1  # Below threshold
    traits.assertiveness = 0.05  # Below threshold
    traits.openness = -0.14  # Below threshold
    traits.energy = 0.0

    summary = traits.summary_for_prompt()
    assert summary == ""

    # One above threshold
    traits.valence = 0.2
    summary = traits.summary_for_prompt()
    assert "Valence" in summary
    assert "Assertiveness" not in summary
