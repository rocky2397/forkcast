"""What you burn, learned from meals and weigh-ins (D45)."""

from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from app import adaptive, goals, main

MAN = dict(sex="m", age=30, height_cm=180, weight_kg=80, activity="moderate", goal="maintain")
FORMULA = goals.formula_burn(MAN)  # 2,759


def _flat(kg: float, days: int = 28, every: int = 2, per_day: float = 0.0):
    return [(float(d), kg + per_day * d) for d in range(0, days, every)]


def test_nothing_is_learned_from_too_little_data():
    est = adaptive.estimate(FORMULA, [2500.0] * 6, _flat(80, days=8))
    assert est["measured"] is None and est["burn"] == round(FORMULA)
    assert est["complete_days"] == 6 and est["needed_days"] == adaptive.MIN_COMPLETE_DAYS


def test_steady_weight_means_you_burn_what_you_eat():
    # 2,600 a day for four weeks and the weight didn't move: you burn about 2,600.
    est = adaptive.estimate(FORMULA, [2600.0] * 24, _flat(80))
    assert est["measured"] == 2600
    assert 2600 <= est["burn"] < 2640 and est["trust"] > 0.9 and not est["limited"]


def test_falling_weight_adds_the_lost_energy_back():
    # 2,300 a day while losing 0.05 kg a day (385 kcal): you burn about 2,685.
    est = adaptive.estimate(FORMULA, [2300.0] * 24, _flat(80, per_day=-0.05))
    assert est["measured"] == pytest.approx(2685, abs=2)


def test_less_data_leans_on_the_formula():
    two_weeks = adaptive.estimate(FORMULA, [2600.0] * 12, _flat(80, days=14, every=1))
    four_weeks = adaptive.estimate(FORMULA, [2600.0] * 24, _flat(80))
    assert two_weeks["trust"] < four_weeks["trust"]
    assert abs(two_weeks["burn"] - FORMULA) > 0 and two_weeks["burn"] > four_weeks["burn"]


def test_the_learned_burn_stays_within_15_percent_of_the_formula():
    # A log that says 1,800 a day at steady weight: probably meals are missing.
    est = adaptive.estimate(FORMULA, [1800.0] * 24, _flat(80))
    assert est["measured"] == 1800 and est["limited"]
    assert est["burn"] == round(FORMULA * 0.85)


def _seed(con, kcal: float, days: int = 28, forgotten: tuple = (), per_day: float = 0.0):
    con.execute(
        """INSERT INTO profile (id, sex, age, height_cm, weight_kg, activity, goal)
           VALUES (1, 'm', 30, 180, 80, 'moderate', 'maintain')"""
    )
    today = datetime.now(timezone.utc).date()
    for ago in range(days, 0, -1):
        day = today - timedelta(days=ago)
        noon = datetime.combine(day, datetime.min.time()) + timedelta(hours=12)
        eaten = 400.0 if ago in forgotten else kcal
        con.execute("INSERT INTO meal_log (logged_at, name, calories) VALUES (?, 'Day', ?)",
                    (noon.strftime("%Y-%m-%d %H:%M:%S"), eaten))
        if ago not in forgotten:
            con.execute("INSERT INTO day_check (day, complete) VALUES (?, 1)", (day.isoformat(),))
        if ago % 2 == 0:
            morning = noon - timedelta(hours=5)
            con.execute("INSERT INTO weight_log (logged_at, weight_kg) VALUES (?, ?)",
                        (morning.strftime("%Y-%m-%d %H:%M:%S"), 80 + per_day * (days - ago)))
    con.commit()


def test_forgotten_days_are_left_out(db):
    _seed(db, 2600, forgotten=(3, 9, 15))
    est = adaptive.learn(db, db.execute("SELECT * FROM profile").fetchone())
    assert est["complete_days"] == 25  # 28 days in the window, three forgotten
    assert est["measured"] == pytest.approx(2600, abs=5)


def test_targets_use_the_learned_burn(db):
    _seed(db, 2600)
    profile, est = adaptive.profile_with_burn(db)
    assert profile["burn_kcal"] == est["burn"] < round(FORMULA)
    assert goals.targets(profile)["calories"] == est["burn"]  # maintain: eat what you burn
    assert "burn_kcal" not in adaptive.public(profile)


def test_the_day_and_weight_endpoints_explain_it(db):
    _seed(db, 2600)
    client = TestClient(main.app)
    day = client.get("/api/day?tz=0").json()
    assert day["burn"]["measured"] == pytest.approx(2600, abs=5)
    assert day["targets"]["calories"] == day["burn"]["burn"]
    w = client.get("/api/weight?tz=0").json()
    assert w["burn"]["burn"] == day["burn"]["burn"]
    assert "burn_kcal" not in client.get("/api/profile?tz=0").json()["profile"]


def test_a_new_kitchen_uses_the_formula(db):
    db.execute(
        """INSERT INTO profile (id, sex, age, height_cm, weight_kg, activity, goal)
           VALUES (1, 'm', 30, 180, 80, 'moderate', 'maintain')"""
    )
    db.commit()
    profile, est = adaptive.profile_with_burn(db)
    assert "burn_kcal" not in profile and est["measured"] is None
    assert goals.targets(profile)["calories"] == round(FORMULA)
