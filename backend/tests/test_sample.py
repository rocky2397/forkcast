"""The README's sample people (D43): realistic, never under the minimum."""

import sqlite3
from datetime import datetime, timezone

import pytest

from app import db, goals, progress, sample, weight


@pytest.mark.parametrize("persona, direction", [("lose", "lose"), ("gain", "gain")])
def test_a_sample_person_looks_like_a_real_one(tmp_path, persona, direction):
    con = db.connect(tmp_path / "u.db", attach_corpus=False)
    profile = sample.seed_history(con, persona, datetime.now(timezone.utc).replace(tzinfo=None))
    row = con.execute("SELECT * FROM profile").fetchone()
    s = progress.summary(con, row, 60)
    w = weight.summary(con, row, 60)
    assert goals.plan(profile)["direction"] == direction
    assert 5 <= s["streak"] <= 12  # human, not perfect
    assert s["totals"]["below_minimum"] == 0 and s["totals"]["not_logged"] >= 1
    assert w["status"] == "on_track" and not w["too_fast"]


def test_the_helper_leaves_the_recipe_corpus_visible(tmp_path):
    # The server makes the user tables; the helper must not add empty recipe
    # tables to the user file, or they hide the attached corpus.
    path = tmp_path / "forkcast.db"
    # Like the server's user file: user tables only, the corpus attached elsewhere.
    sqlite3.connect(path).executescript(db.USER_SCHEMA)
    names = "SELECT name FROM sqlite_master WHERE type='table'"
    before = {r[0] for r in sqlite3.connect(path).execute(names)}
    import subprocess
    import sys
    from pathlib import Path

    script = Path(__file__).resolve().parents[1] / "scripts" / "sample_history.py"
    subprocess.run([sys.executable, str(script), str(path), "lose"], check=True, capture_output=True)
    after = {r[0] for r in sqlite3.connect(path).execute(names)}
    assert after == before  # no tables of its own, so no empty recipe tables
    assert sqlite3.connect(path).execute("SELECT COUNT(*) FROM weight_log").fetchone()[0] > 15
