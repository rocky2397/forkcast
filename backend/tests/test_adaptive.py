"""What you burn, learned from meals and weigh-ins (D45)."""

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import adaptive, goals, main

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "eval" / "scripts"))
import sim_burn  # noqa: E402

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


def _stamp(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%d %H:%M:%S")


def _seed(con, kcal: float, days: int = 28, forgotten: tuple = (), per_day: float = 0.0,
          incomplete: tuple = (), unchecked: dict | None = None):
    """Four weeks of one meal a day, weigh-ins every other morning.

    forgotten: days ago with a small meal and no answer (under half the target).
    incomplete: days ago with a full meal the user marked "No, I missed some".
    unchecked: {days ago: kcal} eaten with no answer either way.
    """
    con.execute(
        """INSERT INTO profile (id, sex, age, height_cm, weight_kg, activity, goal)
           VALUES (1, 'm', 30, 180, 80, 'moderate', 'maintain')"""
    )
    unchecked = unchecked or {}
    today = datetime.now(timezone.utc).date()
    for ago in range(days, 0, -1):
        day = today - timedelta(days=ago)
        noon = datetime.combine(day, datetime.min.time()) + timedelta(hours=12)
        eaten = 400.0 if ago in forgotten else unchecked.get(ago, kcal)
        con.execute("INSERT INTO meal_log (logged_at, name, calories) VALUES (?, 'Day', ?)",
                    (_stamp(noon), eaten))
        if ago in incomplete:
            con.execute("INSERT INTO day_check (day, complete) VALUES (?, 0)", (day.isoformat(),))
        elif ago not in forgotten and ago not in unchecked:
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


def test_the_learned_burn_stays_within_15_percent_upwards_too():
    est = adaptive.estimate(FORMULA, [3600.0] * 24, _flat(80))
    assert est["measured"] == 3600 and est["limited"]
    assert est["burn"] == round(FORMULA * 1.15)


def test_noisy_weigh_ins_are_trusted_less():
    clean = _flat(80)
    noisy = [(d, kg + (0.9 if i % 2 else -0.9)) for i, (d, kg) in enumerate(clean)]
    assert adaptive.estimate(FORMULA, [2600.0] * 24, noisy)["trust"] < adaptive.estimate(
        FORMULA, [2600.0] * 24, clean)["trust"] - 0.1


def test_days_marked_incomplete_are_left_out(db):
    # Full days, but the user said "No, I missed some": they don't count.
    _seed(db, 2600, incomplete=(2, 5, 8, 11))
    est = adaptive.learn(db, db.execute("SELECT * FROM profile").fetchone())
    assert est["complete_days"] == 24


def test_today_and_weigh_ins_before_the_window_are_left_out(db):
    _seed(db, 2600)
    # Midnight today (UTC, tz=0): already today however early the test runs.
    today = datetime.combine(datetime.now(timezone.utc).date(), datetime.min.time())
    # A big half-day today, and a much heavier weigh-in today and two months ago.
    db.execute("INSERT INTO meal_log (logged_at, name, calories) VALUES (?, 'Today', 5000)", (_stamp(today),))
    db.execute("INSERT INTO weight_log (logged_at, weight_kg) VALUES (?, 86)", (_stamp(today),))
    db.execute("INSERT INTO weight_log (logged_at, weight_kg) VALUES (?, 90)",
               (_stamp(today - timedelta(days=60)),))
    db.commit()
    est = adaptive.learn(db, db.execute("SELECT * FROM profile").fetchone())
    assert est["complete_days"] == 28
    assert est["measured"] == pytest.approx(2600, abs=5)


def test_a_learned_burn_never_decides_which_days_count(db):
    # Steady at 1,900 a day: the burn is held at 85% of the formula (2,345),
    # half of which is 1,173. Three unanswered 1,300-kcal days are under half
    # the formula's target (1,380), so they stay out whatever was learned.
    _seed(db, 1900, unchecked={4: 1300, 9: 1300, 14: 1300})
    profile, est = adaptive.profile_with_burn(db)
    assert profile["burn_kcal"] == round(FORMULA * 0.85)
    again = adaptive.learn(db, profile)  # a profile that already carries the learned burn
    assert est["complete_days"] == again["complete_days"] == 25


def test_streaks_and_day_colours_use_the_learned_burn(db):
    _seed(db, 2600)
    client = TestClient(main.app)
    learned = client.get("/api/day?tz=0").json()["burn"]["burn"]
    progress = client.get("/api/progress?tz=0").json()["progress"]
    assert progress["burn"] == learned < round(FORMULA)
    # At 2,600 a day the formula (2,759) would call these deficit days; against
    # the learned burn they are maintenance.
    assert progress["totals"]["maintenance"] >= 27


def test_the_simulation_still_shows_learning_beats_the_formula():
    # A small run of eval stage 6, so a change to the estimator that undoes
    # its results fails here rather than only in the write-up.
    honest = sim_burn.report(300, 28, 0.0)
    assert honest["learned"] == 1.0
    assert honest["learned_median"] < 0.6 * honest["formula_median"]
    misses = sim_burn.report(300, 28, 0.10)
    assert misses["learned_plan"] < 0.6 * misses["formula_plan"]
