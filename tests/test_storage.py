"""Unit tests for habit_tracker.storage.

Exercises the SQLite layer in isolation. Every test runs against
a fresh in-memory database (provided by the ``storage`` fixture in
conftest.py) so tests cannot interfere with each other and no
files end up on disk.
"""

from datetime import datetime

from habit_tracker.habit import Habit, Periodicity


class TestRoundTrip:
    """Saved data should equal loaded data."""

    def test_save_and_load_single_habit(self, storage):
        h = Habit(name="Yoga", periodicity="weekly")
        storage.save_habit(h)
        loaded = storage.load_habit(h.id)
        assert loaded is not None
        assert loaded.id == h.id
        assert loaded.name == "Yoga"
        assert loaded.periodicity is Periodicity.WEEKLY

    def test_save_completion_round_trips(self, storage):
        h = Habit(name="Test", periodicity="daily")
        storage.save_habit(h)
        ts1 = datetime(2026, 5, 6, 9, 0)
        ts2 = datetime(2026, 5, 7, 10, 30)
        storage.save_completion(h.id, ts1)
        storage.save_completion(h.id, ts2)
        loaded = storage.load_habit(h.id)
        assert loaded.completions == [ts1, ts2]

    def test_load_all_groups_completions_per_habit(self, storage):
        a = Habit(name="A", periodicity="daily")
        b = Habit(name="B", periodicity="daily")
        storage.save_habit(a)
        storage.save_habit(b)
        storage.save_completion(a.id, datetime(2026, 5, 6, 9, 0))
        storage.save_completion(a.id, datetime(2026, 5, 7, 9, 0))
        storage.save_completion(b.id, datetime(2026, 5, 6, 10, 0))
        by_name = {h.name: h for h in storage.load_all_habits()}
        assert len(by_name["A"].completions) == 2
        assert len(by_name["B"].completions) == 1


class TestEmptyDatabase:
    """Behaviour when the database is empty."""

    def test_load_all_habits_returns_empty_list(self, storage):
        assert storage.load_all_habits() == []

    def test_load_habit_returns_none_for_unknown_id(self, storage):
        assert storage.load_habit("does-not-exist") is None


class TestDelete:
    """Deletion behaviour, including foreign-key cascade."""

    def test_delete_returns_true_on_success(self, storage):
        h = Habit(name="Test", periodicity="daily")
        storage.save_habit(h)
        assert storage.delete_habit(h.id) is True
        assert storage.load_habit(h.id) is None

    def test_delete_returns_false_for_missing_id(self, storage):
        assert storage.delete_habit("nope") is False

    def test_delete_cascades_to_completions(self, storage):
        h = Habit(name="Test", periodicity="daily")
        storage.save_habit(h)
        storage.save_completion(h.id, datetime(2026, 5, 6, 9, 0))
        storage.save_completion(h.id, datetime(2026, 5, 7, 9, 0))
        storage.delete_habit(h.id)
        # Foreign-key cascade should have wiped the completions table.
        cursor = storage._conn.execute(
            "SELECT COUNT(*) FROM completions"
        )
        assert cursor.fetchone()[0] == 0


class TestUpsertSemantics:
    """save_habit must be idempotent and preserve completions."""

    def test_double_save_does_not_lose_completions(self, storage):
        # Regression for the ``INSERT OR REPLACE`` -> cascade-delete bug
        # that motivated using SQLite's UPSERT syntax instead.
        h = Habit(name="Test", periodicity="daily")
        storage.save_habit(h)
        storage.save_completion(h.id, datetime(2026, 5, 6, 9, 0))
        storage.save_habit(h)   # second save, same id
        loaded = storage.load_habit(h.id)
        assert len(loaded.completions) == 1
