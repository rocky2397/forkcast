"""Targets (D12) and macro fit (D20) — pure functions, no DB, no embeddings."""

import pytest

from app import goals

PROFILE = {"sex": "m", "age": 30, "height_cm": 175, "weight_kg": 80, "activity": "light", "goal": "cut"}
TARGET = {"calories": 2400, "protein_g": 150, "carbs_g": 270, "fat_g": 67}


def test_targets_follow_mifflin_st_jeor():
    # 10*80 + 6.25*175 - 5*30 + 5 = 1748.75 BMR, x1.375 light, -15% cut
    t = goals.targets(PROFILE)
    assert t["calories"] == round(1748.75 * 1.375 * 0.85)
    assert t["protein_g"] == round(1.8 * 80)  # D12: 1.8 g/kg


def test_targets_differ_by_sex_and_goal():
    female = goals.targets({**PROFILE, "sex": "f"})
    assert female["calories"] < goals.targets(PROFILE)["calories"]
    assert goals.targets({**PROFILE, "goal": "bulk"})["calories"] > goals.targets(PROFILE)["calories"]


def test_remaining_never_goes_negative():
    eaten = {"calories": 3000, "protein_g": 200, "carbs_g": 300, "fat_g": 90}
    rem = goals.remaining(eaten, TARGET)
    assert all(v == 0.0 for v in rem.values())


def test_remaining_subtracts_what_was_eaten():
    rem = goals.remaining({"calories": 900, "protein_g": 40}, TARGET)
    assert rem["calories"] == 1500
    assert rem["protein_g"] == 110
    assert rem["carbs_g"] == 270  # absent key counts as nothing eaten


def test_protein_dish_beats_carb_dish_when_protein_is_behind():
    rem = goals.remaining({"calories": 1200, "protein_g": 40, "carbs_g": 180, "fat_g": 40}, TARGET)
    chicken = {"calories": 420, "protein_g": 55, "carbs_g": 6, "fat_g": 14}
    pasta = {"calories": 650, "protein_g": 14, "carbs_g": 110, "fat_g": 12}
    assert goals.macro_fit(chicken, rem) > goals.macro_fit(pasta, rem)


def test_fit_is_bounded_and_ignores_portion_size():
    """Cosine compares composition, so doubling a serving must not change it."""
    rem = goals.remaining({"calories": 500}, TARGET)
    single = {"calories": 400, "protein_g": 30, "carbs_g": 40, "fat_g": 10}
    assert 0.0 <= goals.macro_fit(single, rem) <= 1.0
    # Same composition, same calories: identical score.
    assert goals.macro_fit(single, rem) == goals.macro_fit({**single}, rem)


def test_overshooting_the_day_decays_the_score():
    rem = goals.remaining({"calories": 2000, "protein_g": 100, "carbs_g": 200, "fat_g": 50}, TARGET)
    composition = {"protein_g": 25, "carbs_g": 35, "fat_g": 8}
    fits = goals.macro_fit({**composition, "calories": 300}, rem)
    overshoots = goals.macro_fit({**composition, "calories": 3000}, rem)
    assert overshoots < fits
    # A decay, not a cliff: the dish is still scored.
    assert overshoots > 0.0


def test_unscorable_inputs_return_none_rather_than_zero():
    """None keeps a recipe neutral; 0.0 would rank it below every scored one."""
    rem = goals.remaining({"calories": 500}, TARGET)
    assert goals.macro_fit({"calories": 300}, rem) is None  # no macros at all
    assert goals.macro_fit({"calories": 300, "protein_g": 20}, {"calories": 0.0}) is None


def test_focus_names_the_macro_furthest_behind_as_a_share():
    # Fat is smaller in grams but further behind relative to its target.
    rem = goals.remaining({"calories": 500, "protein_g": 140, "carbs_g": 100, "fat_g": 0}, TARGET)
    assert goals.focus(rem, TARGET) == {"macro": "fat_g", "grams": 67}


def test_focus_is_none_once_everything_is_met():
    rem = goals.remaining({"calories": 2400, "protein_g": 150, "carbs_g": 270, "fat_g": 67}, TARGET)
    assert goals.focus(rem, TARGET) is None


# --- D39: goal weight -------------------------------------------------------

MAN = dict(sex="m", age=30, height_cm=180, weight_kg=80, activity="moderate", goal="maintain")


def test_a_goal_weight_below_sets_a_deficit_from_the_pace():
    # D44: steady is 0.75% of 80 kg a week, 0.6 kg: 660 kcal a day.
    p = goals.plan(MAN | {"goal_weight_kg": 72, "pace": "steady"})
    assert p["direction"] == "lose" and p["pace_share"] == 0.0075
    assert p["burn"] == 2759 and p["change"] == 660 and p["calories"] == 2099
    assert p["kg_per_week"] == 0.6 and p["limited"] is None
    assert goals.targets(MAN | {"goal_weight_kg": 72, "pace": "steady"})["calories"] == 2099


def test_the_timeline_allows_for_the_pace_shrinking():
    # 0.75% of a falling weight: 14 weeks, not 8 / 0.6 = 13.3.
    assert goals.plan(MAN | {"goal_weight_kg": 72, "pace": "steady"})["weeks"] == 14


def test_the_gentle_pace_is_two_thirds_of_steady_when_losing():
    p = goals.plan(MAN | {"goal_weight_kg": 72, "pace": "gentle"})
    assert p["pace_share"] == 0.005 and p["change"] == 440 and p["weeks"] == 22


def test_the_pace_scales_with_body_weight():
    # The same pace asks less of a lighter person: 0.5% is 0.3 kg at 60 kg, 0.5 kg at 100.
    light = goals.plan(MAN | {"weight_kg": 60, "height_cm": 165, "goal_weight_kg": 57, "pace": "gentle"})
    heavy = goals.plan(MAN | {"weight_kg": 100, "goal_weight_kg": 90, "pace": "gentle"})
    assert light["kg_per_week"] == 0.3 and heavy["kg_per_week"] == 0.5
    assert light["limited"] is None and heavy["limited"] is None


def test_a_goal_weight_above_sets_a_surplus():
    p = goals.plan(MAN | {"weight_kg": 60, "goal_weight_kg": 66, "pace": "gentle"})
    assert p["direction"] == "gain" and p["pace_share"] == 0.0025
    assert p["calories"] == p["burn"] + 165 and p["weeks"] == 39
    steady = goals.plan(MAN | {"weight_kg": 60, "goal_weight_kg": 66, "pace": "steady"})
    assert steady["pace_share"] == 0.005 and steady["kg_per_week"] == 0.3


def test_close_to_the_goal_keeps_weight():
    p = goals.plan(MAN | {"goal_weight_kg": 79.8})
    assert p["direction"] == "keep" and p["calories"] == p["burn"]


def test_without_a_goal_weight_the_old_goal_still_works():
    assert goals.plan(MAN) is None
    assert goals.targets(MAN | {"goal": "cut"})["calories"] == round(2759.25 * 0.85)


def test_the_deficit_never_goes_below_the_safe_minimum():
    small = dict(sex="f", age=30, height_cm=160, weight_kg=55, activity="sedentary", goal="maintain",
                 goal_weight_kg=50, pace="steady")
    p = goals.plan(small)
    floor = max(goals.bmr("f", 30, 160, 55), 1200)
    assert p["calories"] >= floor - 1
    assert p["change"] < 550 and "safe minimum" in p["limited"]


def test_the_deficit_is_capped_at_a_quarter_of_the_burn():
    # 0.75% of 120 kg would be 0.9 kg a week; a quarter of the burn allows less.
    big = dict(sex="m", age=40, height_cm=180, weight_kg=120, activity="light", goal="maintain",
               goal_weight_kg=95, pace="steady")
    p = goals.plan(big)
    assert p["change"] == round(0.25 * p["burn"]) and "a quarter" in p["limited"]
    assert p["weeks"] == round(25 / p["kg_per_week"] + 0.5)  # held back: a straight line


def test_no_deficit_when_the_burn_is_already_at_the_minimum():
    tiny = dict(sex="f", age=80, height_cm=150, weight_kg=50, activity="sedentary", goal="maintain",
                goal_weight_kg=45, pace="steady")
    p = goals.plan(tiny)
    assert p["change"] == 0 and p["weeks"] is None and "doctor or dietitian" in p["limited"]


def test_a_goal_below_a_healthy_weight_is_refused():
    assert "below a healthy weight" in goals.goal_problem(MAN | {"goal_weight_kg": 55})
    assert goals.plan(MAN | {"goal_weight_kg": 55}) is None


def test_weight_loss_goals_are_for_adults():
    assert "adults" in goals.goal_problem(MAN | {"age": 16, "goal_weight_kg": 72})
    assert goals.goal_problem(MAN | {"age": 16, "weight_kg": 60, "goal_weight_kg": 66}) is None  # gaining is fine


def test_the_healthy_range_follows_height():
    assert goals.healthy_range_kg(180) == (60.0, 81.0)


def test_weeks_to_goal_bends_with_a_share_and_runs_straight_without():
    # 0.75% of 80 kg is 0.6 kg a week: a straight line says 13.3 weeks, the
    # shrinking pace about 13.9; gaining, the growing pace gets there sooner.
    assert goals.weeks_to_goal(80, 72, 0.6, None) == pytest.approx(13.33, abs=0.01)
    assert goals.weeks_to_goal(80, 72, 0.6, 0.0075) == pytest.approx(13.9, abs=0.1)
    assert goals.weeks_to_goal(60, 66, 0.3, 0.005) < 6 / 0.3
    assert goals.weeks_to_goal(80, 72, 0.0, 0.0075) is None
