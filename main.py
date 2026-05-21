"""Application entry point.

Run the habit tracker from the command line:

    python main.py

This script is intentionally tiny: it imports the CLI from the
habit_tracker package and starts it. All real logic lives inside
the package.
"""

from habit_tracker.cli import run


if __name__ == "__main__":
    run()
