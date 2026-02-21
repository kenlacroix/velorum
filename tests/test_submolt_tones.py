"""Tests for submolt tone profile tracking."""

import json
from pathlib import Path

from velorum.submolts import SubmoltManager


class TestToneProfiles:
    def test_update_tone_profile(self, tmp_path: Path):
        sm = SubmoltManager(persist_path=tmp_path / "submolts.json")
        sm.update_tone_profile("philosophy", "deep, contemplative, formal")
        assert "philosophy" in sm.tone_profiles
        assert sm.tone_profiles["philosophy"]["tone"] == "deep, contemplative, formal"
        assert sm.tone_profiles["philosophy"]["updated_at"] > 0

    def test_update_tone_profiles_bulk(self, tmp_path: Path):
        sm = SubmoltManager(persist_path=tmp_path / "submolts.json")
        observations = {
            "philosophy": "deep and reflective",
            "memes": "playful and irreverent",
            "": "should be skipped",
        }
        sm.update_tone_profiles(observations)
        assert "philosophy" in sm.tone_profiles
        assert "memes" in sm.tone_profiles
        assert "" not in sm.tone_profiles

    def test_tone_for_prompt_known(self, tmp_path: Path):
        sm = SubmoltManager(persist_path=tmp_path / "submolts.json")
        sm.update_tone_profile("tech", "precise, technical, data-driven")
        result = sm.tone_for_prompt("tech")
        assert result == "precise, technical, data-driven"

    def test_tone_for_prompt_unknown(self, tmp_path: Path):
        sm = SubmoltManager(persist_path=tmp_path / "submolts.json")
        result = sm.tone_for_prompt("nonexistent")
        assert result == ""

    def test_all_tones_for_prompt_empty(self, tmp_path: Path):
        sm = SubmoltManager(persist_path=tmp_path / "submolts.json")
        assert sm.all_tones_for_prompt() == ""

    def test_all_tones_for_prompt_populated(self, tmp_path: Path):
        sm = SubmoltManager(persist_path=tmp_path / "submolts.json")
        sm.update_tone_profile("philosophy", "deep and reflective")
        sm.update_tone_profile("memes", "playful")
        result = sm.all_tones_for_prompt()
        assert "- memes: playful" in result
        assert "- philosophy: deep and reflective" in result

    def test_tone_profiles_persist(self, tmp_path: Path):
        path = tmp_path / "submolts.json"
        sm = SubmoltManager(persist_path=path)
        sm.update_tone_profile("tech", "precise")
        sm.save()

        # Reload
        sm2 = SubmoltManager(persist_path=path)
        assert "tech" in sm2.tone_profiles
        assert sm2.tone_profiles["tech"]["tone"] == "precise"

    def test_tone_profile_overwrites(self, tmp_path: Path):
        sm = SubmoltManager(persist_path=tmp_path / "submolts.json")
        sm.update_tone_profile("tech", "old tone")
        sm.update_tone_profile("tech", "new tone")
        assert sm.tone_profiles["tech"]["tone"] == "new tone"
