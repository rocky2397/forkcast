"""Weigh-ins, trend and projection (D41)."""

import random
from datetime import datetime, timedelta, timezone

import pytest

from app import weight

NOW = datetime(2026, 11, 15, 12)


def _series(rate_per_week: float, seed: int = 1, noise: float = 0.8, days: int = 30, step: int = 2):
    rnd = random.Random(seed)
    return [(NOW - timedelta(days=d), 82 + rate_per_week * (days - d) / 7 + rnd.uniform(-noise, noise))
            for d in range(days, -1, -step)]


def test_the_trend_smooths_a_single_jump():
    pts = [(NOW - timedelta(days=d), 80.0) for d in range(10, 0, -1)] + [(NOW, 82.0)]
    t = weight.trend(pts)
    assert t[-2] == pytest.approx(80.0) and 80.0 < t[-1] < 80.3  # a 2 kg jump moves it ~0.2 kg


def test_the_pace_is_unbiased_on_noisy_weigh_ins():
    for rate in (-0.5, -0.25, 0.3):
        ests = sorted(weight.weekly_rate(p, weight.trend(p), NOW) for p in (_series(rate, s) for s in range(100)))
        assert ests[50] == pytest.approx(rate, abs=0.05)


def test_too_little_data_gives_no_pace():
    pts = _series(-0.5, days=4)
    assert weight.weekly_rate(pts, weight.trend(pts), NOW) is None


PROFILE = "INSERT INTO profile (id,sex,age,height_cm,weight_kg,activity,goal,goal_weight_kg,pace) VALUES (1,'m',30,180,82,'moderate','cut',?,'steady')"


@pytest.fixture
def con(db):
    db.execute("DELETE FROM weight_log")
    db.execute("DELETE FROM profile")
    db.commit()
    return db


def _log_series(con, rate, goal=75.0, seed=1):
    con.execute(PROFILE, (goal,))
    now = datetime.now(timezone.utc)
    for when, kg in _series(rate, seed):
        stamp = (now - (NOW - when)).strftime("%Y-%m-%d %H:%M:%S")
        con.execute("INSERT INTO weight_log (logged_at, weight_kg) VALUES (?, ?)", (stamp, round(kg, 1)))
    con.commit()
    return con.execute("SELECT * FROM profile").fetchone()


def test_on_track_and_dates(con):
    profile = _log_series(con, -0.5)
    s = weight.summary(con, profile)
    assert s["status"] in ("on_track", "ahead") and s["projection"]["plan_date"]
    assert s["projection"]["actual_date"] is not None and s["too_fast"] is False


def test_stalled_when_nothing_moves(con):
    profile = _log_series(con, 0.0, seed=3)
    assert weight.summary(con, profile)["status"] in ("stalled", "behind")


def test_losing_too_fast_is_flagged(con):
    profile = _log_series(con, -1.5)
    assert weight.summary(con, profile)["too_fast"] is True


def test_without_a_goal_there_is_no_projection(con):
    con.execute(PROFILE, (None,))
    con.commit()
    weight.log(con, 80.0)
    s = weight.summary(con, con.execute("SELECT * FROM profile").fetchone())
    assert s["projection"] is None and s["trend_kg"] == 80.0


def test_a_weigh_in_moves_the_profile_to_the_trend(con):
    con.execute(PROFILE, (75.0,))
    con.commit()
    weight.log(con, 80.0)
    weight.log(con, 83.0)  # same day: moves the trend only a little
    prof = con.execute("SELECT weight_kg FROM profile").fetchone()
    assert 80.0 < prof["weight_kg"] < 81.0
    last = con.execute("SELECT id FROM weight_log ORDER BY id DESC").fetchone()["id"]
    weight.remove(con, last)
    assert con.execute("SELECT weight_kg FROM profile").fetchone()["weight_kg"] == 80.0
