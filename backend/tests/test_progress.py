"""Streaks, day classes and the weekly recap (D40)."""

from datetime import datetime, timedelta, timezone

import pytest

from app import goals, progress

# A man, 30, 180 cm, 80 kg, moderately active: burns 2,759 kcal, keeps weight.
PROFILE = dict(sex="m", age=30, height_cm=180, weight_kg=80, activity="moderate", goal="maintain")
BURN = 2759.25
TARGET = goals.targets(PROFILE)["calories"]


def test_day_classes():
    minimum = goals.minimum_calories(PROFILE)
    assert progress.day_status(400, TARGET, BURN, minimum) == "not_logged"   # half the target missing
    assert progress.day_status(1600, TARGET, BURN, minimum) == "below_minimum"
    assert progress.day_status(2300, TARGET, BURN, minimum) == "deficit"
    assert progress.day_status(2800, TARGET, BURN, minimum) == "maintenance"
    assert progress.day_status(3100, TARGET, BURN, minimum) == "surplus"


def test_on_target_never_rewards_too_little():
    assert progress.on_target(TARGET * 0.95, TARGET, "maintenance")
    assert not progress.on_target(TARGET * 0.8, TARGET, "deficit")
    assert not progress.on_target(1400, 1450, "below_minimum")


def _log(db, days_ago: int, calories: float, recipe_id=None, liked=None, protein=150.0):
    when = datetime.now(timezone.utc) - timedelta(days=days_ago)
    db.execute(
        "INSERT INTO meal_log (recipe_id, logged_at, liked, name, calories, protein_g, carbs_g, fat_g)"
        " VALUES (?, ?, ?, 'meal', ?, ?, 0, 0)",
        (recipe_id, when.strftime("%Y-%m-%d %H:%M:%S"), liked, calories, protein),
    )


@pytest.fixture
def log(db):
    db.execute("DELETE FROM meal_log")
    db.commit()
    yield lambda *a, **k: (_log(db, *a, **k), db.commit())


def test_the_streak_counts_days_on_target(db, log):
    for days_ago in (1, 2, 3):
        log(days_ago, TARGET)
    log(4, TARGET * 1.4)  # a surplus day ends it
    s = progress.summary(db, PROFILE)
    assert s["streak"] == 3


def test_a_forgotten_day_neither_breaks_nor_extends_the_streak(db, log):
    log(1, TARGET)
    log(2, 300)  # forgot to log most of it
    log(3, TARGET)
    s = progress.summary(db, PROFILE)
    assert s["streak"] == 2
    assert s["totals"]["not_logged"] >= 1


def test_today_counts_once_it_is_on_target(db, log):
    log(1, TARGET)
    assert progress.summary(db, PROFILE)["streak"] == 1  # today still in progress
    log(0, TARGET)
    assert progress.summary(db, PROFILE)["streak"] == 2


def test_days_below_the_minimum_break_the_streak(db, log):
    log(1, TARGET)
    log(2, 1550)  # under the 1,780 kcal minimum
    log(3, TARGET)
    s = progress.summary(db, PROFILE)
    assert s["streak"] == 1 and s["totals"]["below_minimum"] == 1


def test_totals_and_strip(db, log):
    log(1, 2300)
    log(2, 2800)
    log(3, 3200)
    s = progress.summary(db, PROFILE)
    t = s["totals"]
    assert (t["deficit"], t["maintenance"], t["surplus"]) == (1, 1, 1)
    assert t["not_logged"] == 30 - 3 and t["days"] == 30
    assert len(s["strip"]) == 14 and s["strip"][-1]["status"] == "today"
    assert [d["status"] for d in s["strip"][-4:-1]] == ["surplus", "maintenance", "deficit"]


def test_the_weekly_recap(db, log):
    log(1, TARGET, recipe_id=1, liked=1)
    log(2, TARGET, recipe_id=2)
    log(3, TARGET, protein=50)
    log(10, TARGET, recipe_id=2)  # recipe 2 was cooked before: not new this week
    r = progress.summary(db, PROFILE)["recap"]
    assert r["cooked"] == 2 and r["typed"] == 1
    assert r["new_recipes"] == 1 and r["liked"] == 1
    assert r["days_logged"] == 3 and r["days_on_target"] == 3
    assert r["protein_days"] == 2


def test_days_are_local_days(db, log):
    # A meal at 23:30 UTC is the next day in Berlin (UTC+1).
    now = datetime.now(timezone.utc)
    late = (now - timedelta(days=1)).replace(hour=23, minute=30, second=0)
    db.execute("INSERT INTO meal_log (logged_at, name, calories, protein_g, carbs_g, fat_g) VALUES (?, 'late', ?, 150, 0, 0)",
               (late.strftime("%Y-%m-%d %H:%M:%S"), TARGET))
    db.commit()
    utc = {d["date"]: d["calories"] for d in progress.summary(db, PROFILE, 0)["strip"]}
    berlin = {d["date"]: d["calories"] for d in progress.summary(db, PROFILE, 60)["strip"]}
    assert utc[late.date().isoformat()] == round(TARGET)
    assert berlin[(late + timedelta(hours=1)).date().isoformat()] == round(TARGET)




# --- D42: the user's word on whether a day is complete ----------------------


def test_a_confirmed_day_counts_even_when_small(db, log):
    yesterday = (datetime.now(timezone.utc) - timedelta(days=1)).date().isoformat()
    log(1, 900)  # under half the target: would be "not logged"
    assert progress.summary(db, PROFILE)["strip"][-2]["status"] == "not_logged"
    progress.set_check(db, yesterday, True)
    day = progress.summary(db, PROFILE)["strip"][-2]
    assert day["status"] == "below_minimum" and day["confirmed"] is True


def test_a_day_marked_incomplete_never_counts(db, log):
    yesterday = (datetime.now(timezone.utc) - timedelta(days=1)).date().isoformat()
    log(1, TARGET)
    progress.set_check(db, yesterday, False)
    s = progress.summary(db, PROFILE)
    assert s["strip"][-2]["status"] == "not_logged" and s["streak"] == 0
    progress.set_check(db, yesterday, None)  # cleared
    assert progress.summary(db, PROFILE)["streak"] == 1


def test_confirming_today_makes_it_a_full_day(db, log):
    today = datetime.now(timezone.utc).date().isoformat()
    log(0, 2300)
    assert progress.summary(db, PROFILE)["strip"][-1]["status"] == "today"
    progress.set_check(db, today, True)
    assert progress.summary(db, PROFILE)["strip"][-1]["status"] == "deficit"


def test_the_weekly_balance(db, log):
    log(1, BURN - 500)
    log(2, BURN - 300)
    log(3, 400)  # forgotten: left out of the average
    b = progress.summary(db, PROFILE)["recap"]["balance"]
    assert b["days"] == 2 and b["avg_per_day"] == -400
    assert b["planned_per_day"] == 0 and b["est_kg"] == pytest.approx(-800 / 7700, abs=0.01)


def test_confirming_an_empty_day_changes_nothing(db, log):
    yesterday = (datetime.now(timezone.utc) - timedelta(days=1)).date().isoformat()
    progress.set_check(db, yesterday, True)
    assert progress.summary(db, PROFILE)["strip"][-2]["status"] == "not_logged"
