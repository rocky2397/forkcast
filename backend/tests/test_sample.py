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
    # Read in the same time zone the history is made in (UTC): at UTC+1 the
    # hour after midnight is still yesterday in UTC, and the test failed then.
    s = progress.summary(con, row, 0)
    w = weight.summary(con, row, 0)
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


def test_a_shorter_history_is_the_start_of_the_same_six_weeks(tmp_path, monkeypatch):
    """The README's "plan redraws itself" strip: one person at weeks 1, 3 and 6."""
    from datetime import timedelta

    from app import adaptive

    now = datetime.now(timezone.utc).replace(tzinfo=None)

    def history(upto):
        con = db.connect(tmp_path / f"u{upto}.db", attach_corpus=False)
        sample.seed_history(con, "lose", now, upto=upto)
        weighs = con.execute("SELECT logged_at, weight_kg FROM weight_log ORDER BY logged_at").fetchall()
        meals = con.execute("SELECT logged_at, calories FROM meal_log ORDER BY logged_at").fetchall()
        return con, [tuple(r) for r in weighs], [tuple(r) for r in meals]

    _, full_w, full_m = history(None)
    for upto in (7, 21):
        as_of = (now.date() - timedelta(days=sample.DAYS - upto)).isoformat()
        con, w, m = history(upto)
        # the same days on the same dates, cut at the day the strip's clock is set to
        assert w == [x for x in full_w if x[0] < as_of] and m == [x for x in full_m if x[0] < as_of]
        assert m[-1][0][:10] < as_of and len({x[0][:10] for x in m}) == upto
        # as the app sees it on that day: still learning in week 1, learned by week 3
        monkeypatch.setattr(progress, "local_today", lambda tz=0, d=as_of: datetime.fromisoformat(d).date())
        _, est = adaptive.profile_with_burn(con, 60)
        assert (est["measured"] is None) is (upto == 7)
