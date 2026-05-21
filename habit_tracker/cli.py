"""Command-line interface for the habit tracker.

A simple ``input()``-driven menu loop. The CLI talks only to the
``HabitManager``: every business decision (validation, persistence,
analytics) happens behind that interface, so this module is left
to do nothing more than read input, format output, and dispatch.

Run from the project root with::

    python main.py
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Callable, List, Optional

from habit_tracker.habit import Habit, Periodicity
from habit_tracker.manager import HabitManager, HabitNotFoundError
from habit_tracker.storage import DEFAULT_DB_PATH, Storage


# ---------------------------------------------------------------------------
# Top-level entry point
# ---------------------------------------------------------------------------

def run(db_path: str = DEFAULT_DB_PATH) -> None:
    """Open storage, seed if empty, and run the main menu loop.

    Pulled out of ``main.py`` so unit tests (or alternative front
    ends) can drive the same control flow with an in-memory
    database (``db_path=":memory:"``).
    """
    print(_BANNER)
    try:
        with Storage(db_path) as store:
            manager = HabitManager(store)
            if manager.seed_if_empty():
                print(
                    "First run detected - seeded the database with 5 "
                    "predefined habits and 4 weeks of example data.\n"
                )
            _main_loop(manager)
    except (KeyboardInterrupt, EOFError):
        # Ctrl+C or Ctrl+D: leave silently rather than dumping a
        # traceback. The ``with`` block above still closes storage.
        print("\nGoodbye.")


# ---------------------------------------------------------------------------
# Main loop
# ---------------------------------------------------------------------------

_BANNER = """
=========================================
        H A B I T   T R A C K E R
=========================================
""".rstrip()


_MAIN_MENU = """
Main menu
  1. View all habits
  2. View one habit in detail
  3. Create a new habit
  4. Check off a habit
  5. Delete a habit
  6. Rename a habit
  7. Analytics
  0. Quit
"""


def _main_loop(manager: HabitManager) -> None:
    """Print the menu and dispatch user choices until the user quits."""
    actions: dict[str, Callable[[HabitManager], None]] = {
        "1": _cmd_list_habits,
        "2": _cmd_view_habit,
        "3": _cmd_create_habit,
        "4": _cmd_check_off,
        "5": _cmd_delete_habit,
        "6": _cmd_rename_habit,
        "7": _cmd_analytics_menu,
    }

    while True:
        print(_MAIN_MENU)
        choice = _prompt("Choose an option: ").lower()

        if choice in ("0", "q", "quit", "exit"):
            print("Goodbye.")
            return

        action = actions.get(choice)
        if action is None:
            print(f"Unknown option {choice!r}. Please choose 0 - 7.")
            continue

        try:
            action(manager)
        except (ValueError, HabitNotFoundError) as exc:
            print(f"Error: {exc}")


# ---------------------------------------------------------------------------
# Command implementations
# ---------------------------------------------------------------------------

def _cmd_list_habits(manager: HabitManager) -> None:
    """Show every habit alongside its streaks."""
    habits = manager.list_habits()
    if not habits:
        print("\nNo habits yet. Create one with option 3.")
        return

    print()
    _print_habit_table(habits, manager)


def _cmd_view_habit(manager: HabitManager) -> None:
    """Show one habit's metadata, streaks, and recent completions."""
    habit = _pick_habit(manager, "View which habit")
    if habit is None:
        return

    longest = manager.longest_streak_for(habit.id)
    current = manager.current_streak_for(habit.id)

    print()
    print(f"Habit:       {habit.name}")
    print(f"Periodicity: {habit.periodicity.value}")
    print(f"Created:     {habit.created_at.strftime('%Y-%m-%d %H:%M')}")
    print(f"Completions: {len(habit.completions)}")
    print(f"Longest streak: {longest}")
    print(f"Current streak: {current}")

    if habit.completions:
        print("\nRecent completions:")
        for ts in sorted(habit.completions, reverse=True)[:10]:
            print(f"  - {ts.strftime('%Y-%m-%d %H:%M')}")


def _cmd_create_habit(manager: HabitManager) -> None:
    """Prompt for name and periodicity, then persist a new habit."""
    name = _prompt("Habit name: ")
    periodicity = _prompt("Periodicity (daily/weekly): ").lower()
    habit = manager.create_habit(name, periodicity)
    print(f"\nCreated: {habit}  (id: {habit.id[:8]}...)")


def _cmd_check_off(manager: HabitManager) -> None:
    """Mark a habit complete with the current time."""
    habit = _pick_habit(manager, "Check off which habit")
    if habit is None:
        return
    timestamp = manager.check_off(habit.id)
    print(
        f"\nChecked off '{habit.name}' at "
        f"{timestamp.strftime('%Y-%m-%d %H:%M')}."
    )


def _cmd_delete_habit(manager: HabitManager) -> None:
    """Delete a habit (and its completion history) after confirmation."""
    habit = _pick_habit(manager, "Delete which habit")
    if habit is None:
        return
    confirm = _prompt(
        f"Delete '{habit.name}' and all its completions? (y/N): "
    ).lower()
    if confirm != "y":
        print("Cancelled.")
        return
    manager.delete_habit(habit.id)
    print(f"Deleted '{habit.name}'.")


def _cmd_rename_habit(manager: HabitManager) -> None:
    """Rename a habit, preserving its completion history."""
    habit = _pick_habit(manager, "Rename which habit")
    if habit is None:
        return
    new_name = _prompt(f"New name for '{habit.name}': ")
    if not new_name:
        print("Cancelled.")
        return
    renamed = manager.rename_habit(habit.id, new_name)
    print(f"Renamed to '{renamed.name}'.")


# ---------------------------------------------------------------------------
# Analytics sub-menu
# ---------------------------------------------------------------------------

_ANALYTICS_MENU = """
Analytics
  1. Longest streak across all habits
  2. Longest streak for a specific habit
  3. Current streak for a specific habit
  4. List habits by periodicity
  5. Habits I'm struggling with (last 30 days)
  0. Back to main menu
"""


def _cmd_analytics_menu(manager: HabitManager) -> None:
    """Sub-menu for analytical queries."""
    actions: dict[str, Callable[[HabitManager], None]] = {
        "1": _ana_longest_overall,
        "2": _ana_longest_for_habit,
        "3": _ana_current_for_habit,
        "4": _ana_by_periodicity,
        "5": _ana_struggled_with,
    }

    while True:
        print(_ANALYTICS_MENU)
        choice = _prompt("Choose: ").lower()
        if choice in ("0", "b", "back"):
            return
        action = actions.get(choice)
        if action is None:
            print(f"Unknown option {choice!r}. Please choose 0 - 5.")
            continue
        try:
            action(manager)
        except (ValueError, HabitNotFoundError) as exc:
            print(f"Error: {exc}")


def _ana_longest_overall(manager: HabitManager) -> None:
    longest = manager.longest_streak()
    print(f"\nLongest streak across all habits: {longest}")


def _ana_longest_for_habit(manager: HabitManager) -> None:
    habit = _pick_habit(manager, "Longest streak for which habit")
    if habit is None:
        return
    streak = manager.longest_streak_for(habit.id)
    print(
        f"\nLongest streak for '{habit.name}': {streak} "
        f"{habit.periodicity.value} period(s)."
    )


def _ana_current_for_habit(manager: HabitManager) -> None:
    habit = _pick_habit(manager, "Current streak for which habit")
    if habit is None:
        return
    streak = manager.current_streak_for(habit.id)
    print(
        f"\nCurrent streak for '{habit.name}': {streak} "
        f"{habit.periodicity.value} period(s)."
    )


def _ana_by_periodicity(manager: HabitManager) -> None:
    raw = _prompt("Periodicity (daily/weekly): ").lower()
    habits = manager.list_habits_by_periodicity(raw)
    if not habits:
        print(f"\nNo {raw} habits.")
        return
    print(f"\n{raw.title()} habits:")
    for habit in habits:
        print(f"  - {habit.name}")


def _ana_struggled_with(manager: HabitManager) -> None:
    end = datetime.now()
    start = end - timedelta(days=30)
    results = manager.habits_struggled_with(start, end, top_n=3)
    if not results:
        print("\nNo habits to analyse.")
        return
    print("\nHabits with the most missed periods in the last 30 days:")
    for habit, missed in results:
        if missed == 0:
            continue
        print(f"  - {habit.name}: {missed} missed {habit.periodicity.value} period(s)")
    if all(missed == 0 for _, missed in results):
        print("  (none - well done!)")


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _print_habit_table(habits: List[Habit], manager: HabitManager) -> None:
    """Render the standard habit listing with streaks."""
    header = f"{'#':>3}  {'Habit':<22} {'Period':<8} {'Done':>4}  {'Longest':>7}  {'Current':>7}"
    print(header)
    print("-" * len(header))
    for i, habit in enumerate(habits, start=1):
        longest = manager.longest_streak_for(habit.id)
        current = manager.current_streak_for(habit.id)
        print(
            f"{i:>3}  {habit.name:<22} {habit.periodicity.value:<8} "
            f"{len(habit.completions):>4}  {longest:>7}  {current:>7}"
        )


def _pick_habit(
    manager: HabitManager, prompt: str = "Pick a habit"
) -> Optional[Habit]:
    """List habits with index numbers and return the one the user picks.

    Returns ``None`` if there are no habits, or if the user's input
    is invalid or empty. Errors are reported inline; callers should
    simply return when ``None`` comes back.
    """
    habits = manager.list_habits()
    if not habits:
        print("\nNo habits yet.")
        return None

    print()
    for i, habit in enumerate(habits, start=1):
        print(f"  {i}. {habit}")

    raw = _prompt(f"\n{prompt} (1-{len(habits)}, or empty to cancel): ")
    if not raw:
        return None

    try:
        index = int(raw)
    except ValueError:
        print(f"'{raw}' is not a valid number.")
        return None

    if not 1 <= index <= len(habits):
        print(f"Pick a number between 1 and {len(habits)}.")
        return None

    return habits[index - 1]


def _prompt(message: str) -> str:
    """Thin wrapper around ``input`` so tests can monkey-patch it."""
    return input(message).strip()
