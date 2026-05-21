"""Unit tests for habit_tracker.manager.

Exercises the manager's orchestration role: validation, error
handling, and the analytics passthroughs. The ``manager`` and
``seeded_manager`` fixtures from conftest.py provide isolated
in-memory databases per test.
"""

from datetime import datetime, timedelta

import pytest

from habit_tracker.fixtures import FIXTURE_DAYS, FIXTURE_START
from habit_tracker.habit import Periodicity
from habit_tracker.manager import HabitNotFoundError


class TestSeeding:
    def test_first_call_returns_true(self, manager):
        assert manager.seed_if_empty() is True

    def test_subsequent_call_returns_false(self, manager):
        manager.seed_if_empty()
        assert manager.seed_if_empty() is False

    def test_seed_loads_five_habits(self, manager):
        manager.seed_if_empty()
        assert len(manager.list_habits()) == 5


class TestCreate:
    def test_create_persists_habit(self, manager):
        habit = manager.create_habit("Meditate", "daily")
        loaded = manager.get_habit(habit.id)
        assert loaded.name == "Meditate"
        assert loaded.periodicity is Periodicity.DAILY

    def test_create_rejects_empty_name(self, manager):
        with pytest.raises(ValueError):
            manager.create_habit("", "daily")

    def test_create_rejects_invalid_periodicity(self, manager):
        with pytest.raises(ValueError):
            manager.create_habit("Test", "monthly")


class TestCheckOff:
    def test_check_off_appends_completion(self, manager):
        habit = manager.create_habit("Test", "daily")
        manager.check_off(habit.id, datetime(2026, 5, 6, 9, 0))
        loaded = manager.get_habit(habit.id)
        assert len(loaded.completions) == 1

    def test_check_off_unknown_habit_raises(self, manager):
        with pytest.raises(HabitNotFoundError):
            manager.check_off("does-not-exist")


class TestDelete:
    def test_delete_removes_habit(self, manager):
        habit = manager.create_habit("Test", "daily")
        manager.delete_habit(habit.id)
        with pytest.raises(HabitNotFoundError):
            manager.get_habit(habit.id)

    def test_delete_unknown_raises(self, manager):
        with pytest.raises(HabitNotFoundError):
            manager.delete_habit("nope")


class TestRename:
    """Habit editing - the rename operation."""

    def test_rename_persists(self, manager):
        habit = manager.create_habit("Old name", "daily")
        manager.rename_habit(habit.id, "New name")
        assert manager.get_habit(habit.id).name == "New name"

    def test_rename_preserves_completions(self, manager):
        # Regression: the storage UPSERT must not cascade-delete the log.
        habit = manager.create_habit("Original", "daily")
        manager.check_off(habit.id, datetime(2026, 5, 6, 9, 0))
        manager.check_off(habit.id, datetime(2026, 5, 7, 9, 0))
        manager.rename_habit(habit.id, "Renamed")
        loaded = manager.get_habit(habit.id)
        assert loaded.name == "Renamed"
        assert len(loaded.completions) == 2

    def test_rename_rejects_empty_name(self, manager):
        habit = manager.create_habit("Original", "daily")
        with pytest.raises(ValueError):
            manager.rename_habit(habit.id, "")

    def test_rename_unknown_habit_raises(self, manager):
        with pytest.raises(HabitNotFoundError):
            manager.rename_habit("does-not-exist", "anything")


class TestLookups:
    def test_get_unknown_raises(self, manager):
        with pytest.raises(HabitNotFoundError):
            manager.get_habit("nope")

    def test_find_by_name_case_insensitive(self, seeded_manager):
        habit = seeded_manager.find_habit_by_name("DRINK 2L WATER")
        assert habit is not None
        assert habit.id == "fixture-water"

    def test_find_by_name_returns_none_for_no_match(self, seeded_manager):
        assert seeded_manager.find_habit_by_name("nonexistent") is None

    def test_find_by_name_empty_string_returns_none(self, seeded_manager):
        assert seeded_manager.find_habit_by_name("   ") is None


class TestAnalyticsPassthroughs:
    """Ensure the manager surfaces analytics correctly."""

    def test_longest_streak_overall(self, seeded_manager):
        assert seeded_manager.longest_streak() == 28

    def test_longest_streak_for_habit(self, seeded_manager):
        assert seeded_manager.longest_streak_for("fixture-water") == 16

    def test_current_streak_for_habit(self, seeded_manager):
        ref = FIXTURE_START + timedelta(days=FIXTURE_DAYS - 1, hours=23)
        assert seeded_manager.current_streak_for("fixture-water", ref) == 11

    def test_list_by_periodicity_daily(self, seeded_manager):
        daily = seeded_manager.list_habits_by_periodicity("daily")
        assert len(daily) == 3

    def test_list_by_periodicity_weekly(self, seeded_manager):
        weekly = seeded_manager.list_habits_by_periodicity("weekly")
        assert len(weekly) == 2

    def test_struggled_with_top_one(self, seeded_manager):
        end = FIXTURE_START + timedelta(days=FIXTURE_DAYS)
        result = seeded_manager.habits_struggled_with(
            FIXTURE_START, end, top_n=1
        )
        assert len(result) == 1
        assert result[0][0].id == "fixture-read"
