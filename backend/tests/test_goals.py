"""Targets (D12) and macro fit (D20) — pure functions, no DB, no embeddings."""

from app import goals

PROFILE = {"sex": "m", "age": 31, "height_cm": 179, "weight_kg": 92, "activity": "light", "goal": "cut"}
TARGET = {"calories": 2400, "protein_g": 150, "carbs_g": 270, "fat_g": 67}


def test_targets_follow_mifflin_st_jeor():
    # 10*92 + 6.25*179 - 5*31 + 5 = 1888.75 BMR, x1.375 light, -15% cut
    t = goals.targets(PROFILE)
    assert t["calories"] == round(1888.75 * 1.375 * 0.85)
    assert t["protein_g"] == round(1.8 * 92)  # D12: 1.8 g/kg


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
