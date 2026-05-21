"""Shared pytest fixtures for the habit tracker test suite.

A ``conftest.py`` placed in the ``tests`` directory is automatically
discovered by pytest, so any fixture defined here is available to
every test file in this directory without an explicit import.

The fixtures provided here keep tests fast, deterministic, and
isolated:

    storage          - a fresh in-memory SQLite database per test
    manager          - a HabitManager wrapping that empty storage
    seeded_storage   - storage pre-loaded with the 4-week fixture
    seeded_manager   - manager wrapping the seeded storage
    fixture_habits   - the predefined habits as plain Python objects
                       (no database involvement)
"""

from __future__ import annotations

import pytest

from habit_tracker.fixtures import predefined_habits, load_into
from habit_tracker.manager import HabitManager
from habit_tracker.storage import Storage


@pytest.fixture
def storage():
    """Yield a fresh in-memory SQLite Storage and close it after the test."""
    s = Storage(":memory:")
    try:
        yield s
    finally:
        s.close()


@pytest.fixture
def manager(storage):
    """A HabitManager wrapping an empty in-memory storage."""
    return HabitManager(storage)


@pytest.fixture
def seeded_storage(storage):
    """In-memory storage pre-loaded with the four-week fixture data."""
    load_into(storage)
    return storage


@pytest.fixture
def seeded_manager(seeded_storage):
    """A HabitManager backed by storage that already contains fixtures."""
    return HabitManager(seeded_storage)


@pytest.fixture
def fixture_habits():
    """The five predefined habits as in-memory Habit objects.

    Returned without touching any database, so analytics tests can
    exercise pure functions in complete isolation.
    """
    return predefined_habits()
