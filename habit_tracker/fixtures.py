"""Predefined habits and four-week test data.

Provides five predefined habits (three daily, two weekly) along
with 28 days of plausible completion timestamps. The same data
serves two purposes:

    1. Seeding a fresh database so a brand-new user can explore the
       app immediately without having to enter test data by hand.
    2. Acting as a deterministic fixture for the unit-test suite.

The fixture is anchored to a fixed reference date (Monday,
6 April 2026) rather than ``datetime.now()`` so tests can make
exact assertions about streak lengths and period boundaries on
every run.

Completion patterns are designed to exercise the streak logic:

    'Morning workout'   - perfect 28-day daily streak.
    'Drink 2L water'    - one missed day, breaks the streak.
    'Read 30 minutes'   - sporadic, several short streaks.
    'Weekly meal prep'  - perfect 4-week weekly streak.
    'Call family'       - one missed week, breaks the weekly streak.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import List, Tuple

from habit_tracker.habit import Habit, Periodicity
from habit_tracker.storage import Storage


# Anchor: Monday, 6 April 2026 at 00:00.
# The four-week window runs through Sunday, 3 May 2026 (day 27).
FIXTURE_START: datetime = datetime(2026, 4, 6)
FIXTURE_DAYS: int = 28


# ---------------------------------------------------------------------------
# Completion patterns
#
# Each entry is ``(day_offset_from_start, hour, minute)``. The patterns are
# kept declarative on purpose: the structure of the data is itself the
# documentation of what each fixture is meant to test.
# ---------------------------------------------------------------------------

# Daily, 9:00 every day - except day 16 (Wed 22 Apr), which is skipped.
# Streak history: 16 days, break, 11 days. Longest = 16, current = 11.
_WATER_PATTERN: List[Tuple[int, int, int]] = [
    (d, 9, 0) for d in range(FIXTURE_DAYS) if d != 16
]

# Daily, 6:30 every single day. A perfect 28-day streak.
_WORKOUT_PATTERN: List[Tuple[int, int, int]] = [
    (d, 6, 30) for d in range(FIXTURE_DAYS)
]

# Sporadic reading: five segments of varying length with gaps between.
# Segments: [0-3]=4, [6-9]=4, [11-15]=5, [18-22]=5, [25-27]=3.
# Total = 21/28. Longest segment = 5 days (occurs twice).
_READ_DAYS: List[int] = [
    0, 1, 2, 3,
    6, 7, 8, 9,
    11, 12, 13, 14, 15,
    18, 19, 20, 21, 22,
    25, 26, 27,
]
_READ_PATTERN: List[Tuple[int, int, int]] = [(d, 21, 0) for d in _READ_DAYS]

# Weekly habit, completed on the Sunday of each ISO week (days 6, 13, 20, 27).
# Perfect 4-week weekly streak.
_MEALPREP_PATTERN: List[Tuple[int, int, int]] = [
    (6,  17, 0),
    (13, 17, 0),
    (20, 17, 0),
    (27, 17, 0),
]

# Weekly habit. Week 3 is intentionally skipped, breaking the streak.
# Streak history: 2 weeks, break, 1 week. Longest = 2, current = 1.
_CALL_FAMILY_PATTERN: List[Tuple[int, int, int]] = [
    (6,  19, 30),  # Sunday week 1
    (12, 14, 0),   # Saturday week 2
    # week 3 (days 14-20) intentionally missed
    (27, 19, 30),  # Sunday week 4
]


def _build_completions(
    pattern: List[Tuple[int, int, int]],
) -> List[datetime]:
    """Convert ``(day_offset, hour, minute)`` tuples into datetimes.

    Each tuple is added to ``FIXTURE_START`` to produce an absolute
    timestamp. Returning a fresh list on every call means callers
    can mutate the result without affecting other callers.
    """
    return [
        FIXTURE_START + timedelta(days=d, hours=h, minutes=m)
        for d, h, m in pattern
    ]


def predefined_habits() -> List[Habit]:
    """Return the five predefined habits with completions populated.

    Habit objects are constructed fresh on every call so the
    returned list is safe to mutate. Each habit has a stable,
    human-readable id so test assertions can target it directly
    (e.g. ``"fixture-workout"``).
    """
    return [
        Habit(
            id="fixture-water",
            name="Drink 2L water",
            periodicity=Periodicity.DAILY,
            created_at=FIXTURE_START,
            completions=_build_completions(_WATER_PATTERN),
        ),
        Habit(
            id="fixture-workout",
            name="Morning workout",
            periodicity=Periodicity.DAILY,
            created_at=FIXTURE_START,
            completions=_build_completions(_WORKOUT_PATTERN),
        ),
        Habit(
            id="fixture-read",
            name="Read 30 minutes",
            periodicity=Periodicity.DAILY,
            created_at=FIXTURE_START,
            completions=_build_completions(_READ_PATTERN),
        ),
        Habit(
            id="fixture-mealprep",
            name="Weekly meal prep",
            periodicity=Periodicity.WEEKLY,
            created_at=FIXTURE_START,
            completions=_build_completions(_MEALPREP_PATTERN),
        ),
        Habit(
            id="fixture-call-family",
            name="Call family",
            periodicity=Periodicity.WEEKLY,
            created_at=FIXTURE_START,
            completions=_build_completions(_CALL_FAMILY_PATTERN),
        ),
    ]


def load_into(store: Storage) -> List[Habit]:
    """Insert all predefined habits and their completions into ``store``.

    Intended to be called against an empty database (e.g. on first
    launch). The caller is responsible for deciding whether seeding
    is appropriate; this function does not check for existing data.

    Returns:
        The list of habits that was loaded, useful for confirmation
        messages or subsequent operations.
    """
    habits = predefined_habits()
    for habit in habits:
        store.save_habit(habit)
        for completion in habit.completions:
            store.save_completion(habit.id, completion)
    return habits
