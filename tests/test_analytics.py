"""Unit tests for habit_tracker.analytics.

Every analytic function is exercised against the four-week
predefined fixture, where the expected outcomes were chosen at
design time:

    fixture-water         longest 16  current 11  missed 1
    fixture-workout       longest 28  current 28  missed 0
    fixture-read          longest  5  current  3  missed 7
    fixture-mealprep      longest  4  current  4  missed 0
    fixture-call-family   longest  2  current  1  missed 1

Tests pass an explicit reference timestamp wherever "now" matters,
so analytics is exercised as the pure function it is - no clocks
involved.
"""

from datetime import datetime, timedelta

import pytest

from habit_tracker.analytics import (
    count_missed_periods,
    current_streak_for_habit,
    filter_by_periodicity,
    habits_struggled_with,
    list_all_habits,
    longest_streak_for_habit,
    longest_streak_overall,
)
from habit_tracker.fixtures import FIXTURE_DAYS, FIXTURE_START
from habit_tracker.habit import Habit, Periodicity


# Reference timestamps that anchor the fixture data.
FIXTURE_END_EXCLUSIVE = FIXTURE_START + timedelta(days=FIXTURE_DAYS)
LAST_DAY_EVENING = FIXTURE_START + timedelta(days=FIXTURE_DAYS - 1, hours=23)


def _by_id(habits, habit_id):
    """Tiny lookup helper used throughout the file."""
    return next(h for h in habits if h.id == habit_id)


class TestListAllHabits:
    def test_returns_a_list(self, fixture_habits):
        result = list_all_habits(fixture_habits)
        assert isinstance(result, list)
        assert len(result) == 5

    def test_returns_an_independent_copy(self, fixture_habits):
        # Mutating the returned list must not affect the source.
        result = list_all_habits(fixture_habits)
        result.pop()
        assert len(fixture_habits) == 5

    def test_empty_input(self):
        assert list_all_habits([]) == []


class TestFilterByPeriodicity:
    def test_daily_returns_only_daily_habits(self, fixture_habits):
        daily = filter_by_periodicity(fixture_habits, Periodicity.DAILY)
        assert len(daily) == 3
        assert all(h.periodicity is Periodicity.DAILY for h in daily)

    def test_weekly_returns_only_weekly_habits(self, fixture_habits):
        weekly = filter_by_periodicity(fixture_habits, Periodicity.WEEKLY)
        assert len(weekly) == 2
        assert all(h.periodicity is Periodicity.WEEKLY for h in weekly)

    def test_no_match_returns_empty_list(self):
        assert filter_by_periodicity([], Periodicity.DAILY) == []


class TestLongestStreakForHabit:
    def test_no_completions_returns_zero(self):
        h = Habit(name="Empty", periodicity="daily")
        assert longest_streak_for_habit(h) == 0

    def test_perfect_28_day_streak(self, fixture_habits):
        # Morning workout: every day, no gaps.
        assert longest_streak_for_habit(_by_id(fixture_habits, "fixture-workout")) == 28

    def test_broken_streak_returns_longest_segment(self, fixture_habits):
        # Water: 16 days, missed day, 11 days. Longest = 16.
        assert longest_streak_for_habit(_by_id(fixture_habits, "fixture-water")) == 16

    def test_sporadic_returns_longest_segment(self, fixture_habits):
        # Reading: segments of 4, 4, 5, 5, 3.
        assert longest_streak_for_habit(_by_id(fixture_habits, "fixture-read")) == 5

    def test_perfect_weekly_streak(self, fixture_habits):
        assert longest_streak_for_habit(_by_id(fixture_habits, "fixture-mealprep")) == 4

    def test_broken_weekly_streak(self, fixture_habits):
        assert longest_streak_for_habit(_by_id(fixture_habits, "fixture-call-family")) == 2

    def test_multiple_completions_in_same_period_count_once(self):
        h = Habit(name="Multi", periodicity="daily")
        same_day = datetime(2026, 5, 6, 9, 0)
        h.check_off(same_day)
        h.check_off(same_day.replace(hour=15))
        h.check_off(same_day.replace(hour=21))
        assert longest_streak_for_habit(h) == 1


class TestLongestStreakOverall:
    def test_empty_input_returns_zero(self):
        assert longest_streak_overall([]) == 0

    def test_returns_max_across_all_habits(self, fixture_habits):
        # 28-day workout streak is the longest in the fixture.
        assert longest_streak_overall(fixture_habits) == 28


class TestCurrentStreakForHabit:
    def test_no_completions_returns_zero(self):
        h = Habit(name="Empty", periodicity="daily")
        assert current_streak_for_habit(h, datetime(2026, 5, 6)) == 0

    def test_perfect_streak_evaluated_at_end(self, fixture_habits):
        workout = _by_id(fixture_habits, "fixture-workout")
        assert current_streak_for_habit(workout, LAST_DAY_EVENING) == 28

    def test_after_break_only_post_break_streak_counts(self, fixture_habits):
        water = _by_id(fixture_habits, "fixture-water")
        # 11 days from day 17 through day 27 inclusive.
        assert current_streak_for_habit(water, LAST_DAY_EVENING) == 11

    def test_mid_period_grace_keeps_streak_alive(self):
        # Yesterday and the day before were completed; today is not yet.
        # The streak should still report 2, not 0.
        h = Habit(name="Test", periodicity="daily")
        h.check_off(datetime(2026, 5, 4, 9, 0))
        h.check_off(datetime(2026, 5, 5, 9, 0))
        assert current_streak_for_habit(h, datetime(2026, 5, 6, 14, 0)) == 2

    def test_two_day_gap_breaks_streak(self):
        # Today and yesterday both missed -> streak is 0.
        h = Habit(name="Test", periodicity="daily")
        h.check_off(datetime(2026, 5, 1, 9, 0))
        assert current_streak_for_habit(h, datetime(2026, 5, 6, 14, 0)) == 0


class TestCountMissedPeriods:
    def test_perfect_streak_has_zero_misses(self, fixture_habits):
        workout = _by_id(fixture_habits, "fixture-workout")
        assert count_missed_periods(workout, FIXTURE_START, FIXTURE_END_EXCLUSIVE) == 0

    def test_one_missed_day_in_window(self, fixture_habits):
        water = _by_id(fixture_habits, "fixture-water")
        assert count_missed_periods(water, FIXTURE_START, FIXTURE_END_EXCLUSIVE) == 1

    def test_sporadic_habit_missed_count(self, fixture_habits):
        # 28 expected periods, 21 completed -> 7 missed.
        read = _by_id(fixture_habits, "fixture-read")
        assert count_missed_periods(read, FIXTURE_START, FIXTURE_END_EXCLUSIVE) == 7

    def test_zero_length_range_is_zero(self):
        h = Habit(name="X", periodicity="daily")
        same = datetime(2026, 5, 6, 9, 0)
        assert count_missed_periods(h, same, same) == 0


class TestHabitsStruggledWith:
    def test_returns_top_n_sorted_by_missed_count(self, fixture_habits):
        result = habits_struggled_with(
            fixture_habits, FIXTURE_START, FIXTURE_END_EXCLUSIVE, top_n=3
        )
        assert len(result) == 3
        # Highest missed count first.
        assert result[0][0].id == "fixture-read"
        assert result[0][1] == 7

    def test_top_n_caps_results(self, fixture_habits):
        result = habits_struggled_with(
            fixture_habits, FIXTURE_START, FIXTURE_END_EXCLUSIVE, top_n=1
        )
        assert len(result) == 1
        assert result[0][0].id == "fixture-read"

    def test_empty_input_returns_empty_list(self):
        result = habits_struggled_with(
            [], FIXTURE_START, FIXTURE_END_EXCLUSIVE, top_n=3
        )
        assert result == []
