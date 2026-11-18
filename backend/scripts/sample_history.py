#!/usr/bin/env python
"""Write a sample person's six weeks of history into a Forkcast database (D43).

    python backend/scripts/sample_history.py <forkcast.db> lose|gain [days]

days keeps only the first days of the same six weeks, on the same dates, and
prints the day after the last one kept ("as of YYYY-MM-DD"): the README's "the
plan redraws itself" strip sets the app's clock to it
(scripts/serve_for_screenshots.py).

Replaces the profile, weigh-ins, past days' meals and day checks with the
persona's (app/sample.py); today's meals stay. Used by ops/screenshots.sh for
the README's progress GIF and stills. Sample data only: never point it at a
database with real history in it.
"""
import sqlite3
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import sample  # noqa: E402

if __name__ == "__main__":
    if len(sys.argv) not in (3, 4) or sys.argv[2] not in sample.PERSONAS:
        sys.exit(__doc__)
    upto = int(sys.argv[3]) if len(sys.argv) == 4 else None
    # A plain connection: the server already made the tables. db.connect() with
    # attach_corpus=False would also create empty recipe tables in this file,
    # which then hide the real corpus (SQLite looks in main first).
    con = sqlite3.connect(Path(sys.argv[1]))
    con.row_factory = sqlite3.Row
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    profile = sample.seed_history(con, sys.argv[2], now, upto=upto)
    as_of = now.date() - timedelta(days=sample.DAYS - upto) if upto else now.date()
    print(f"{sys.argv[2]}: {profile['weight_kg']} kg, goal {profile['goal_weight_kg']} kg, as of {as_of.isoformat()}")
