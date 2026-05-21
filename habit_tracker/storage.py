"""SQLite persistence layer for the habit tracker.

This module is the only place in the project that touches a
database. Two tables are used:

    habits       - one row per habit
                   (id, name, periodicity, created_at)
    completions  - one row per check-off event
                   (habit_id, completed_at)

All timestamps are stored as ISO 8601 strings. They sort correctly
in lexicographic order and round-trip cleanly through
``datetime.fromisoformat`` / ``datetime.isoformat``.

Public API:
    Storage(db_path)           - open a connection (file or ":memory:")
    .save_habit(habit)         - upsert a habit row
    .save_completion(id, ts)   - append a check-off event
    .delete_habit(id)          - remove a habit and its completions
    .load_all_habits()         - return list[Habit] with completions
    .load_habit(id)            - return a single Habit or None
    .close()                   - close the connection
"""

from __future__ import annotations

import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Union

from habit_tracker.habit import Habit, Periodicity


# -- Schema --------------------------------------------------------------
#
# Defined as one block of SQL so the entire schema can be created in a
# single ``executescript`` call. ``CREATE ... IF NOT EXISTS`` makes the
# script idempotent: it can run on every connection without erroring on
# an already-initialised database.
_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS habits (
    id           TEXT PRIMARY KEY,
    name         TEXT NOT NULL,
    periodicity  TEXT NOT NULL,
    created_at   TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS completions (
    habit_id      TEXT NOT NULL,
    completed_at  TEXT NOT NULL,
    FOREIGN KEY (habit_id) REFERENCES habits(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_completions_habit_completed
    ON completions(habit_id, completed_at);
"""


DEFAULT_DB_PATH = "habits.db"


class Storage:
    """Encapsulates all database access for the habit tracker.

    Opens an sqlite3 connection on construction and creates the
    schema if it doesn't already exist. Pass a path to a file for
    persistent storage, or the special string ``":memory:"`` for a
    temporary in-memory database (used by the unit tests).

    Usage:
        with Storage("habits.db") as store:
            store.save_habit(my_habit)
            store.save_completion(my_habit.id, datetime.now())
            habits = store.load_all_habits()
    """

    def __init__(self, db_path: Union[str, Path] = DEFAULT_DB_PATH) -> None:
        """Open a SQLite connection and create the schema if needed.

        Args:
            db_path: Path to a database file, or ``":memory:"`` for
                     a transient in-memory database (used by tests).
        """
        self.db_path = str(db_path)
        self._conn = sqlite3.connect(self.db_path)
        # Foreign-key enforcement is OFF by default in SQLite. Turn it
        # on so ON DELETE CASCADE actually fires.
        self._conn.execute("PRAGMA foreign_keys = ON;")
        # Make rows accessible by column name, e.g. row["name"].
        self._conn.row_factory = sqlite3.Row
        self._init_schema()

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------
    def _init_schema(self) -> None:
        """Create tables and indexes if they don't already exist."""
        with self._conn:
            self._conn.executescript(_SCHEMA_SQL)

    def close(self) -> None:
        """Close the underlying database connection."""
        self._conn.close()

    def __enter__(self) -> "Storage":
        """Context-manager entry. Returns self so ``with`` blocks
        receive the connected storage instance."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        """Context-manager exit. Closes the connection on the way out,
        even if the ``with`` block raised."""
        self.close()

    # ------------------------------------------------------------------
    # Writes
    # ------------------------------------------------------------------
    def save_habit(self, habit: Habit) -> None:
        """Insert a habit, or update its metadata if the id already exists.

        Uses SQLite's UPSERT syntax (``ON CONFLICT ... DO UPDATE``) rather
        than ``INSERT OR REPLACE`` because the latter performs a delete
        then an insert, which would trigger ``ON DELETE CASCADE`` and
        wipe the habit's existing completions. UPSERT keeps the row in
        place and only updates the changed columns.
        """
        with self._conn:
            self._conn.execute(
                """
                INSERT INTO habits (id, name, periodicity, created_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    name        = excluded.name,
                    periodicity = excluded.periodicity,
                    created_at  = excluded.created_at
                """,
                (
                    habit.id,
                    habit.name,
                    habit.periodicity.value,
                    habit.created_at.isoformat(),
                ),
            )

    def save_completion(self, habit_id: str, timestamp: datetime) -> None:
        """Append a single completion event for a habit."""
        with self._conn:
            self._conn.execute(
                "INSERT INTO completions (habit_id, completed_at) VALUES (?, ?)",
                (habit_id, timestamp.isoformat()),
            )

    def delete_habit(self, habit_id: str) -> bool:
        """Delete a habit and all of its completions (via cascade).

        Returns:
            True if a habit row was actually removed, False if no habit
            with that id existed.
        """
        with self._conn:
            cursor = self._conn.execute(
                "DELETE FROM habits WHERE id = ?", (habit_id,)
            )
            return cursor.rowcount > 0

    # ------------------------------------------------------------------
    # Reads
    # ------------------------------------------------------------------
    def load_all_habits(self) -> List[Habit]:
        """Load every habit, populating each one's completion log.

        Two queries are issued (one for habits, one for all completions)
        and the completions are grouped by ``habit_id`` in Python. This
        avoids the "N+1 query" pattern that would issue one extra
        SELECT per habit.
        """
        habit_rows = self._conn.execute(
            "SELECT id, name, periodicity, created_at "
            "FROM habits ORDER BY created_at"
        ).fetchall()

        completion_rows = self._conn.execute(
            "SELECT habit_id, completed_at "
            "FROM completions ORDER BY completed_at"
        ).fetchall()

        completions_by_habit: Dict[str, List[datetime]] = {}
        for row in completion_rows:
            completions_by_habit.setdefault(row["habit_id"], []).append(
                datetime.fromisoformat(row["completed_at"])
            )

        return [self._row_to_habit(row, completions_by_habit) for row in habit_rows]

    def load_habit(self, habit_id: str) -> Optional[Habit]:
        """Load a single habit by id, or return None if not found."""
        habit_row = self._conn.execute(
            "SELECT id, name, periodicity, created_at "
            "FROM habits WHERE id = ?",
            (habit_id,),
        ).fetchone()
        if habit_row is None:
            return None

        completion_rows = self._conn.execute(
            "SELECT completed_at FROM completions "
            "WHERE habit_id = ? ORDER BY completed_at",
            (habit_id,),
        ).fetchall()

        completions = [
            datetime.fromisoformat(row["completed_at"])
            for row in completion_rows
        ]
        return self._row_to_habit(habit_row, {habit_id: completions})

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    @staticmethod
    def _row_to_habit(
        row: sqlite3.Row,
        completions_by_habit: Dict[str, List[datetime]],
    ) -> Habit:
        """Construct a Habit from a habits-table row and a completion map."""
        return Habit(
            id=row["id"],
            name=row["name"],
            periodicity=Periodicity(row["periodicity"]),
            created_at=datetime.fromisoformat(row["created_at"]),
            completions=completions_by_habit.get(row["id"], []),
        )
