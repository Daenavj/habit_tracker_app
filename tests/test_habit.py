"""Unit tests for habit_tracker.habit.

Covers construction, validation, the check-off behaviour, and the
period-boundary logic for both daily and weekly habits.
"""

from datetime import datetime

import pytest

from habit_tracker.habit import Habit, Periodicity


class TestHabitConstruction:
    """Construction, defaults, and input validation."""

    def test_minimal_construction_assigns_defaults(self):
        h = Habit(name="Drink water", periodicity=Periodicity.DAILY)
        assert h.id          # auto-generated UUID is non-empty
        assert isinstance(h.created_at, datetime)
        assert h.completions == []

    def test_string_periodicity_is_coerced_to_enum(self):
        h = Habit(name="Yoga", periodicity="weekly")
        assert h.periodicity is Periodicity.WEEKLY

    def test_unknown_periodicity_raises(self):
        with pytest.raises(ValueError):
            Habit(name="Invalid", periodicity="hourly")

    def test_empty_name_raises(self):
        with pytest.raises(ValueError):
            Habit(name="", periodicity="daily")

    def test_whitespace_only_name_raises(self):
        with pytest.raises(ValueError):
            Habit(name="     ", periodicity="daily")

    def test_name_is_trimmed_of_surrounding_whitespace(self):
        h = Habit(name="  Read  ", periodicity="daily")
        assert h.name == "Read"

    def test_two_habits_get_distinct_default_ids(self):
        a = Habit(name="A", periodicity="daily")
        b = Habit(name="B", periodicity="daily")
        assert a.id != b.id

    def test_two_habits_get_independent_completion_lists(self):
        # Regression: a mutable default would cause both habits to share
        # the same list. ``field(default_factory=list)`` prevents that.
        a = Habit(name="A", periodicity="daily")
        b = Habit(name="B", periodicity="daily")
        a.completions.append(datetime(2026, 1, 1))
        assert b.completions == []


class TestCheckOff:
    """Behaviour of the check_off method."""

    def test_appends_to_completions(self):
        h = Habit(name="Test", periodicity="daily")
        ts = datetime(2026, 5, 6, 9, 0)
        h.check_off(ts)
        assert h.completions == [ts]

    def test_returns_recorded_timestamp(self):
        h = Habit(name="Test", periodicity="daily")
        ts = datetime(2026, 5, 6, 9, 0)
        assert h.check_off(ts) == ts

    def test_default_timestamp_is_close_to_now(self):
        h = Habit(name="Test", periodicity="daily")
        before = datetime.now()
        ts = h.check_off()
        after = datetime.now()
        assert before <= ts <= after


class TestPeriodBounds:
    """Period-boundary calculation for daily and weekly habits."""

    def test_daily_bounds_are_calendar_day(self):
        h = Habit(name="Test", periodicity="daily")
        ref = datetime(2026, 5, 6, 14, 30)
        start, end = h.period_bounds(ref)
        assert start == datetime(2026, 5, 6)
        assert end == datetime(2026, 5, 7)

    def test_weekly_bounds_align_to_iso_monday(self):
        # 6 May 2026 is a Wednesday; the ISO week runs Mon 4 - Sun 10.
        h = Habit(name="Test", periodicity="weekly")
        ref = datetime(2026, 5, 6, 14, 30)
        start, end = h.period_bounds(ref)
        assert start == datetime(2026, 5, 4)
        assert end == datetime(2026, 5, 11)
        assert start.weekday() == 0   # Monday
        assert end.weekday() == 0

    def test_weekly_bounds_on_a_monday_return_same_day(self):
        h = Habit(name="Test", periodicity="weekly")
        monday = datetime(2026, 5, 4, 8, 0)
        start, _ = h.period_bounds(monday)
        assert start == datetime(2026, 5, 4)


class TestIsCompletedFor:
    """Period-membership checks."""

    def test_daily_completed_is_true_for_same_day(self):
        h = Habit(name="Test", periodicity="daily")
        h.check_off(datetime(2026, 5, 6, 9, 0))
        assert h.is_completed_for(datetime(2026, 5, 6, 21, 0))

    def test_daily_completed_is_false_for_other_day(self):
        h = Habit(name="Test", periodicity="daily")
        h.check_off(datetime(2026, 5, 6, 9, 0))
        assert not h.is_completed_for(datetime(2026, 5, 7, 9, 0))

    def test_weekly_completion_counts_anywhere_in_same_iso_week(self):
        h = Habit(name="Test", periodicity="weekly")
        h.check_off(datetime(2026, 5, 4, 9, 0))   # Monday
        # Saturday of the same ISO week
        assert h.is_completed_for(datetime(2026, 5, 9, 9, 0))

    def test_weekly_completion_does_not_carry_into_next_week(self):
        h = Habit(name="Test", periodicity="weekly")
        h.check_off(datetime(2026, 5, 4, 9, 0))   # Mon, week A
        # Following Monday is the start of week B
        assert not h.is_completed_for(datetime(2026, 5, 11, 9, 0))


class TestRename:
    """Behaviour of the rename method (edit operation)."""

    def test_rename_updates_name(self):
        h = Habit(name="Old name", periodicity="daily")
        h.rename("New name")
        assert h.name == "New name"

    def test_rename_strips_whitespace(self):
        h = Habit(name="Old", periodicity="daily")
        h.rename("  Trimmed  ")
        assert h.name == "Trimmed"

    def test_rename_rejects_empty_string(self):
        h = Habit(name="Old", periodicity="daily")
        with pytest.raises(ValueError):
            h.rename("")

    def test_rename_rejects_whitespace_only(self):
        h = Habit(name="Old", periodicity="daily")
        with pytest.raises(ValueError):
            h.rename("    ")

    def test_rename_does_not_affect_id_or_completions(self):
        h = Habit(name="Old", periodicity="daily")
        original_id = h.id
        h.check_off(datetime(2026, 5, 6, 9, 0))
        h.rename("New")
        assert h.id == original_id
        assert len(h.completions) == 1
