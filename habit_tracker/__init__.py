"""Habit Tracker package.

A small backend for tracking daily and weekly habits, built for the
IU course "Object Oriented and Functional Programming with Python"
(DLBDSOOFPP01).

The package is organised into focused modules so each concern lives
in one place:

    habit       - The Habit domain class (object-oriented).
    storage     - SQLite persistence layer (database operations).
    analytics   - Pure functions for analysing habits (functional).
    manager     - Orchestration layer between the UI and storage.
    cli         - Command-line interface (input-driven menu loop).
    fixtures    - Five predefined habits and four weeks of test data.
"""

__version__ = "0.1.0"
