"""Analytics module - pure functional programming.

All functions in this module are pure: they take collections of
habits or completions, return computed results, and never modify
their inputs or perform any I/O. Streak and aggregation logic is
expressed using ``map``, ``filter``, ``reduce``, ``sorted`` and
``itertools.takewhile`` so each step's intent is named rather
than hidden inside a hand-written loop.

The brief specifies four required analytics; this module provides
those plus two further pure functions that answer the additional
questions raised in the brief ("what's my current streak?" and
"which habits did I struggle most with?").

Public functions:
    list_all_habits(habits)
    filter_by_periodicity(habits, periodicity)
    longest_streak_for_habit(habit)
    longest_streak_overall(habits)
    current_streak_for_habit(habit, reference=None)
    habits_struggled_with(habits, start, end, top_n=3)
"""

from __future__ import annotations

from datetime import datetime, timedelta
from functools import reduce
from itertools import count, takewhile
from typing import Iterable, List, Optional, Tuple

from habit_tracker.habit import Habit, Periodicity


# Lookup table mapping each periodicity to the timedelta separating
# adjacent periods. Defined once so streak logic can stay generic.
_PERIOD_LENGTH = {
    Periodicity.DAILY: timedelta(days=1),
    Periodicity.WEEKLY: timedelta(days=7),
}


# ---------------------------------------------------------------------------
# Listings
# ---------------------------------------------------------------------------

def list_all_habits(habits: Iterable[Habit]) -> List[Habit]:
    """Return every tracked habit as a list.

    Always returns a fresh list, so callers can sort or filter the
    result without affecting the source collection.
    """
    return list(habits)


def filter_by_periodicity(
    habits: Iterable[Habit],
    periodicity: Periodicity,
) -> List[Habit]:
    """Return only those habits whose periodicity matches.

    Implemented with the built-in ``filter`` plus a ``lambda`` to
    make the functional intent (selection without mutation)
    explicit.
    """
    return list(filter(lambda h: h.periodicity is periodicity, habits))


# ---------------------------------------------------------------------------
# Streaks
# ---------------------------------------------------------------------------

def longest_streak_for_habit(habit: Habit) -> int:
    """Return the length of the longest run of consecutive completed periods.

    A "period" is a calendar day for daily habits and an ISO calendar
    week for weekly habits. Multiple completions inside the same
    period count once.

    The implementation is a three-step pipeline:
        1. ``map`` each completion to its period-start datetime.
        2. Deduplicate (set) and sort the period starts.
        3. ``reduce`` the sorted sequence into the longest run of
           periods that are exactly one ``step`` apart.
    """
    if not habit.completions:
        return 0

    period_starts = map(
        lambda c: habit.period_bounds(c)[0],
        habit.completions,
    )
    unique_sorted = sorted(set(period_starts))
    step = _PERIOD_LENGTH[habit.periodicity]
    return _longest_consecutive_run(unique_sorted, step)


def longest_streak_overall(habits: Iterable[Habit]) -> int:
    """Return the longest streak across every habit, or 0 if there are none."""
    return max(
        map(longest_streak_for_habit, habits),
        default=0,
    )


def current_streak_for_habit(
    habit: Habit,
    reference: Optional[datetime] = None,
) -> int:
    """Return the active streak ending at or before ``reference``.

    "Active" means the chain of completed periods ending at the
    period containing ``reference``. If the period containing
    ``reference`` itself has no completion yet, the chain is
    counted from the previous period instead - so a daily habit
    whose user hasn't checked off today will still report a
    non-zero streak until midnight.

    Args:
        habit:     The habit to inspect.
        reference: The "now" timestamp the streak is evaluated
                   against. When None, the most recent completion
                   is used (so the function stays pure - no
                   ``datetime.now()`` is called).
    """
    if not habit.completions:
        return 0
    if reference is None:
        reference = max(habit.completions)

    step = _PERIOD_LENGTH[habit.periodicity]
    completed = frozenset(
        habit.period_bounds(c)[0] for c in habit.completions
    )
    anchor = habit.period_bounds(reference)[0]

    # Mid-period grace: if the user hasn't completed yet for the
    # period containing the reference, evaluate the streak ending
    # at the previous period.
    if anchor not in completed:
        anchor -= step

    # Walk backwards from the anchor until we hit the first
    # missing period, then count how many we walked through.
    candidate_starts = (anchor - step * i for i in count())
    streak_periods = takewhile(lambda p: p in completed, candidate_starts)
    return sum(1 for _ in streak_periods)


# ---------------------------------------------------------------------------
# Struggle analysis
# ---------------------------------------------------------------------------

def count_missed_periods(
    habit: Habit,
    start: datetime,
    end: datetime,
) -> int:
    """Count periods in ``[start, end)`` that have no completion.

    Periods are aligned to the habit's natural period boundaries
    (calendar day or ISO week). A period is considered missed if
    no completion falls inside it, regardless of when within the
    period the missed window happened.
    """
    if start >= end:
        return 0

    step = _PERIOD_LENGTH[habit.periodicity]
    completed = frozenset(
        habit.period_bounds(c)[0] for c in habit.completions
    )
    first_period = habit.period_bounds(start)[0]

    candidate_starts = (first_period + step * i for i in count())
    in_range = takewhile(lambda p: p < end, candidate_starts)
    missed = filter(lambda p: p not in completed, in_range)
    return sum(1 for _ in missed)


def habits_struggled_with(
    habits: Iterable[Habit],
    start: datetime,
    end: datetime,
    top_n: int = 3,
) -> List[Tuple[Habit, int]]:
    """Return the ``top_n`` habits with the most missed periods in ``[start, end)``.

    Each entry is ``(habit, missed_count)``. Ties are broken by the
    habit's natural ordering (newest last) so the result is stable.
    """
    scored = [(h, count_missed_periods(h, start, end)) for h in habits]
    return sorted(scored, key=lambda pair: -pair[1])[:top_n]


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _longest_consecutive_run(
    sorted_periods: List[datetime],
    step: timedelta,
) -> int:
    """Length of the longest run of periods exactly ``step`` apart.

    Implemented as a fold over the sorted period list. The
    accumulator is a 3-tuple ``(previous_period, current_run_length,
    longest_seen_so_far)`` - everything needed to extend or restart
    the run on each step.
    """
    if not sorted_periods:
        return 0

    def fold(acc, current):
        prev, run, longest = acc
        next_run = (
            run + 1
            if prev is not None and (current - prev) == step
            else 1
        )
        return (current, next_run, max(longest, next_run))

    _, _, longest = reduce(fold, sorted_periods, (None, 0, 0))
    return longest
