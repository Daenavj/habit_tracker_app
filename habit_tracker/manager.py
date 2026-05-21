"""HabitManager - orchestration layer.

Bridges the user interface (CLI today, possibly Tkinter or Flask
later) with the storage and analytics modules. The manager:

    * validates input and raises typed exceptions on errors,
    * coordinates calls to the storage layer,
    * delegates pure computations to the analytics module,
    * never produces output - it returns data, the caller renders it.

Because the manager carries no UI state, the same instance can be
driven by any front-end without modification. This is the
architectural answer to the lecturer's question about supporting
additional user-interaction tools in the future.
"""

from __future__ import annotations

from datetime import datetime
from typing import List, Optional, Tuple, Union

from habit_tracker import analytics
from habit_tracker.fixtures import load_into as _load_fixtures
from habit_tracker.habit import Habit, Periodicity
from habit_tracker.storage import Storage


class HabitNotFoundError(LookupError):
    """Raised when an operation references a habit id that does not exist."""


class HabitManager:
    """High-level API for managing habits and querying analytics.

    Construct with a ``Storage`` instance. The manager does not own
    the storage's lifecycle - the caller is responsible for closing
    the storage when done (typically via a ``with`` block).

    Usage::

        with Storage("habits.db") as store:
            manager = HabitManager(store)
            manager.seed_if_empty()
            manager.create_habit("Drink water", "daily")
            manager.check_off(habit_id)
            print(manager.longest_streak())
    """

    def __init__(self, storage: Storage) -> None:
        """Construct a manager bound to an existing ``Storage`` instance.

        The manager does not own the storage's lifecycle - callers are
        responsible for closing the storage (typically via ``with``).
        """
        self._storage = storage

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------
    def seed_if_empty(self) -> bool:
        """Load the predefined fixture data when no habits exist yet.

        Returns:
            True if fixtures were inserted, False if habits already
            existed and the database was left untouched.
        """
        if self._storage.load_all_habits():
            return False
        _load_fixtures(self._storage)
        return True

    # ------------------------------------------------------------------
    # CRUD on habits
    # ------------------------------------------------------------------
    def create_habit(
        self,
        name: str,
        periodicity: Union[str, Periodicity],
    ) -> Habit:
        """Create a new habit and persist it.

        Validation is delegated to the ``Habit`` constructor: an
        empty name or unknown periodicity will raise ``ValueError``
        before the database is touched.
        """
        habit = Habit(name=name, periodicity=periodicity)
        self._storage.save_habit(habit)
        return habit

    def delete_habit(self, habit_id: str) -> None:
        """Delete a habit and all of its completions.

        Raises:
            HabitNotFoundError: if no habit with that id exists.
        """
        if not self._storage.delete_habit(habit_id):
            raise HabitNotFoundError(f"No habit with id {habit_id!r}.")

    def rename_habit(self, habit_id: str, new_name: str) -> Habit:
        """Change the display name of an existing habit.

        Validation is delegated to ``Habit.rename`` so empty or
        whitespace-only names raise ``ValueError``. Completion
        history is preserved (storage uses UPSERT, not
        delete-then-insert).

        Raises:
            HabitNotFoundError: if no habit with that id exists.
            ValueError:         if ``new_name`` is empty or whitespace-only.
        """
        habit = self._require_habit(habit_id)
        habit.rename(new_name)
        self._storage.save_habit(habit)
        return habit

    def check_off(
        self,
        habit_id: str,
        timestamp: Optional[datetime] = None,
    ) -> datetime:
        """Record a completion event for the given habit.

        Args:
            habit_id:  The habit being marked complete.
            timestamp: When the completion happened. Defaults to
                       ``datetime.now()`` - this is fine because the
                       manager sits in the imperative shell, not in
                       the pure analytics core.

        Returns:
            The timestamp that was recorded.

        Raises:
            HabitNotFoundError: if no habit with that id exists.
        """
        habit = self._require_habit(habit_id)
        if timestamp is None:
            timestamp = datetime.now()
        self._storage.save_completion(habit.id, timestamp)
        return timestamp

    # ------------------------------------------------------------------
    # Reads
    # ------------------------------------------------------------------
    def list_habits(self) -> List[Habit]:
        """Return every tracked habit with completions populated."""
        return self._storage.load_all_habits()

    def get_habit(self, habit_id: str) -> Habit:
        """Return one habit by id.

        Raises:
            HabitNotFoundError: if no habit with that id exists.
        """
        return self._require_habit(habit_id)

    def find_habit_by_name(self, name: str) -> Optional[Habit]:
        """Case-insensitive exact-match lookup by name.

        Returns the matching habit or ``None`` when no habit
        matches. Useful for CLI commands where the user types the
        habit's name rather than its id.
        """
        needle = name.strip().lower()
        if not needle:
            return None
        return next(
            (
                habit
                for habit in self._storage.load_all_habits()
                if habit.name.lower() == needle
            ),
            None,
        )

    # ------------------------------------------------------------------
    # Analytics passthroughs
    #
    # The CLI does not import analytics directly: every analytical
    # query is exposed here so the CLI's only dependency is the
    # manager. This keeps the public surface area small and means
    # the analytics module's signatures could change without rippling
    # into the UI layer.
    # ------------------------------------------------------------------
    def list_habits_by_periodicity(
        self,
        periodicity: Union[str, Periodicity],
    ) -> List[Habit]:
        """Return habits matching a given periodicity ('daily'/'weekly')."""
        if isinstance(periodicity, str):
            periodicity = Periodicity(periodicity)
        return analytics.filter_by_periodicity(
            self._storage.load_all_habits(), periodicity
        )

    def longest_streak(self) -> int:
        """Return the longest streak across every habit (0 if none)."""
        return analytics.longest_streak_overall(
            self._storage.load_all_habits()
        )

    def longest_streak_for(self, habit_id: str) -> int:
        """Return the longest streak for one habit by id."""
        return analytics.longest_streak_for_habit(self._require_habit(habit_id))

    def current_streak_for(
        self,
        habit_id: str,
        reference: Optional[datetime] = None,
    ) -> int:
        """Return the active streak for one habit ending at ``reference``."""
        habit = self._require_habit(habit_id)
        if reference is None:
            reference = datetime.now()
        return analytics.current_streak_for_habit(habit, reference)

    def habits_struggled_with(
        self,
        start: datetime,
        end: datetime,
        top_n: int = 3,
    ) -> List[Tuple[Habit, int]]:
        """Return the top-N habits with the most missed periods in a window."""
        return analytics.habits_struggled_with(
            self._storage.load_all_habits(), start, end, top_n
        )

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------
    def _require_habit(self, habit_id: str) -> Habit:
        """Load a habit or raise ``HabitNotFoundError`` if absent."""
        habit = self._storage.load_habit(habit_id)
        if habit is None:
            raise HabitNotFoundError(f"No habit with id {habit_id!r}.")
        return habit
