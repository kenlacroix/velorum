"""Tests for the following tracker."""

import json

from velorum.following import FollowingTracker


class TestFollowingTracker:
    def test_add_and_check(self):
        tracker = FollowingTracker()
        assert tracker.is_following("BotA") is False
        tracker.add("BotA")
        assert tracker.is_following("BotA") is True
        assert tracker.is_following("bota") is True  # case insensitive

    def test_remove(self):
        tracker = FollowingTracker()
        tracker.add("BotA")
        tracker.remove("BotA")
        assert tracker.is_following("BotA") is False
        assert tracker.count == 0

    def test_remove_case_insensitive(self):
        tracker = FollowingTracker()
        tracker.add("BotA")
        tracker.remove("bota")
        assert tracker.count == 0

    def test_names(self):
        tracker = FollowingTracker()
        tracker.add("BotA")
        tracker.add("BotB")
        assert set(tracker.names()) == {"bota", "botb"}

    def test_count(self):
        tracker = FollowingTracker()
        assert tracker.count == 0
        tracker.add("BotA")
        tracker.add("BotB")
        assert tracker.count == 2

    def test_summary_empty(self):
        tracker = FollowingTracker()
        assert tracker.summary_for_prompt() == "Not following anyone yet."

    def test_summary_with_following(self):
        tracker = FollowingTracker()
        tracker.add("BotA")
        tracker.add("BotB")
        text = tracker.summary_for_prompt()
        assert "Following (2)" in text
        assert "bota" in text
        assert "botb" in text

    def test_persistence(self, tmp_path):
        path = tmp_path / "following.json"
        tracker = FollowingTracker(persist_path=path)
        tracker.add("BotA")
        tracker.add("BotB")
        tracker.save()

        # Load fresh
        tracker2 = FollowingTracker(persist_path=path)
        assert tracker2.count == 2
        assert tracker2.is_following("BotA")
        assert tracker2.is_following("BotB")

    def test_to_dict_load_dict(self):
        tracker = FollowingTracker()
        tracker.add("BotA")
        d = tracker.to_dict()
        assert "bota" in d

        tracker2 = FollowingTracker()
        tracker2.load_dict(d)
        assert tracker2.is_following("BotA")

    def test_load_corrupt_file(self, tmp_path):
        path = tmp_path / "following.json"
        path.write_text("not valid json")
        tracker = FollowingTracker(persist_path=path)
        assert tracker.count == 0
