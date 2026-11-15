#!/usr/bin/env python
"""Write a sample person's six weeks of history into a Forkcast database (D43).

    python backend/scripts/sample_history.py <forkcast.db> lose|gain

Replaces the profile, weigh-ins, past days' meals and day checks with the
persona's (app/sample.py); today's meals stay. Used by ops/screenshots.sh for
the README's progress GIF and stills. Sample data only: never point it at a
database with real history in it.
"""
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import sample  # noqa: E402

if __name__ == "__main__":
    if len(sys.argv) != 3 or sys.argv[2] not in sample.PERSONAS:
        sys.exit(__doc__)
    # A plain connection: the server already made the tables. db.connect() with
    # attach_corpus=False would also create empty recipe tables in this file,
    # which then hide the real corpus (SQLite looks in main first).
    con = sqlite3.connect(Path(sys.argv[1]))
    con.row_factory = sqlite3.Row
    profile = sample.seed_history(con, sys.argv[2], datetime.now(timezone.utc).replace(tzinfo=None))
    print(f"{sys.argv[2]}: {profile['weight_kg']} kg, goal {profile['goal_weight_kg']} kg")
