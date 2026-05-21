"""Habit domain class.

Defines the Habit object: an in-memory representation of one
recurring task. A Habit holds its own identity, metadata, and a
local copy of its completion event log, and exposes behaviour for
recording new completions and checking whether the habit was
fulfilled in a given period.

Persistence is delegated to ``storage.py``; aggregate analytics
(streaks, filters, summaries across habits) are computed by
``analytics.py``. Keeping streak and aggregation logic out of this
file lets those calculations be expressed as pure functions, in
line with the project's functional-programming brief.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import List, Optional, Tuple
from uuid import uuid4


class Periodicity(str, Enum):
    """Allowed habit periodicities.

    Inheriting from ``str`` gives us free string comparability
    (``Periodicity.DAILY == "daily"`` is True), which makes
    serialisation and database storage straightforward.
    """

    DAILY = "daily"
    WEEKLY = "weekly"


@dataclass
class Habit:
    """A single recurring task tracked by the application.

    Attributes:
        name:         Short human-readable description of the task.
        periodicity:  How often the task must be completed
                      (``Periodicity.DAILY`` or ``Periodicity.WEEKLY``).
        id:           Unique identifier. A UUID4 hex string is
                      generated automatically if none is supplied.
        created_at:   Timestamp the habit was created. Defaults to
                      the current time.
        completions:  Ordered list of completion timestamps. Treated
                      as an append-only event log: existing entries
                      are never modified, only appended.
    """

    name: str
    periodicity: Periodicity
    id: str = field(default_factory=lambda: uuid4().hex)
    created_at: datetime = field(default_factory=datetime.now)
    completions: List[datetime] = field(default_factory=list)

    # ------------------------------------------------------------------
    # Construction / validation
    # ------------------------------------------------------------------
    def __post_init__(self) -> None:
        """Validate and normalise the input passed to ``__init__``.

        Runs automatically after the dataclass-generated constructor
        finishes. Coerces a plain-string periodicity into the Enum,
        strips whitespace from the name, and rejects empty names.
        """
        if isinstance(self.periodicity, str):
            self.periodicity = Periodicity(self.periodicity)

        if not self.name or not self.name.strip():
            raise ValueError("Habit name cannot be empty.")
        self.name = self.name.strip()

    # ------------------------------------------------------------------
    # Behaviour
    # ------------------------------------------------------------------
    def check_off(self, timestamp: Optional[datetime] = None) -> datetime:
        """Record a completion event for this habit.

        Args:
            timestamp: When the task was completed. Defaults to the
                       current time when omitted.

        Returns:
            The timestamp that was actually recorded - useful for
            the caller to display back to the user or persist.
        """
        if timestamp is None:
            timestamp = datetime.now()
        self.completions.append(timestamp)
        return timestamp

    def is_completed_for(self, reference: datetime) -> bool:
        """Return True if the habit was completed in the period
        containing ``reference``.

        For a daily habit the period is the calendar day of
        ``reference``. For a weekly habit it is the ISO calendar
        week (Monday 00:00 up to but not including the following
        Monday 00:00).
        """
        start, end = self.period_bounds(reference)
        return any(start <= c < end for c in self.completions)

    def period_bounds(self, reference: datetime) -> Tuple[datetime, datetime]:
        """Return ``(start, end)`` of the period containing ``reference``.

        Bounds are derived from this habit's periodicity:

            DAILY  -> [00:00 that day, 00:00 the next day)
            WEEKLY -> [00:00 Monday of that ISO week, 00:00 next Monday)
        """
        day_start = datetime(reference.year, reference.month, reference.day)

        if self.periodicity is Periodicity.DAILY:
            return day_start, day_start + timedelta(days=1)

        # WEEKLY: ISO 8601 weeks start on Monday.
        # weekday() returns 0 for Monday ... 6 for Sunday.
        monday = day_start - timedelta(days=day_start.weekday())
        return monday, monday + timedelta(days=7)

    def rename(self, new_name: str) -> None:
        """Change this habit's display name.

        Applies the same validation as ``__post_init__``: the new
        name is rejected if empty or whitespace-only, and trimmed
        of surrounding whitespace otherwise. The habit's id,
        periodicity, created_at, and completion log are unaffected.
        """
        if not new_name or not new_name.strip():
            raise ValueError("Habit name cannot be empty.")
        self.name = new_name.strip()

    # ------------------------------------------------------------------
    # Display
    # ------------------------------------------------------------------
    def __str__(self) -> str:
        """Human-readable representation used by the CLI."""
        return f"{self.name} ({self.periodicity.value})"
