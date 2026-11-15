"""Daily calorie/macro targets from the user profile (D12), and how well a
recipe fits what is left of the day (D20).

Mifflin-St Jeor BMR x activity factor = TDEE, adjusted by goal.
Protein 1.8 g/kg body weight, fat 25% of kcal, carbs the remainder.

With a goal weight (D39) the adjustment comes from the pace instead: about
7,700 kcal per kg, so 0.5 kg a week is a 550 kcal daily deficit or surplus.
Guardrails: a deficit is at most 25% of what you burn, and the daily target
never drops below your resting burn or 1,200 kcal (women) / 1,500 kcal (men);
when the pace would need more, the plan slows down and says why.
"""

import math
from typing import Mapping

ACTIVITY_FACTORS = {
    "sedentary": 1.2,
    "light": 1.375,
    "moderate": 1.55,
    "active": 1.725,
    "very_active": 1.9,
}

GOAL_ADJUST = {
    "cut": -0.15,
    "maintain": 0.0,
    "bulk": 0.10,
}

# D39: goal weight
PACE_KG_PER_WEEK = {"gentle": 0.25, "steady": 0.5}
KCAL_PER_KG = 7700.0
MAX_DEFICIT_SHARE = 0.25
KCAL_FLOOR = {"f": 1200.0, "m": 1500.0}
KEEP_BAND_KG = 0.5  # closer than this to the goal: keep weight
HEALTHY_BMI_MIN = 18.5
HEALTHY_BMI_MAX = 25.0

PROTEIN_G_PER_KG = 1.8
FAT_KCAL_SHARE = 0.25

KCAL_PER_G_PROTEIN = 4.0
KCAL_PER_G_CARB = 4.0
KCAL_PER_G_FAT = 9.0


def bmr(sex: str, age: int, height_cm: float, weight_kg: float) -> float:
    base = 10.0 * weight_kg + 6.25 * height_cm - 5.0 * age
    return base + (5.0 if sex == "m" else -161.0)


def _opt(profile, key: str):
    """An optional profile field, from a dict or a sqlite3.Row alike."""
    return profile[key] if key in profile.keys() else None


def burn(profile: Mapping) -> float:
    """Estimated calories burned a day (TDEE)."""
    b = bmr(profile["sex"], profile["age"], profile["height_cm"], profile["weight_kg"])
    return b * ACTIVITY_FACTORS[profile["activity"]]


def minimum_calories(profile: Mapping) -> float:
    """The daily minimum (D39): resting burn, and never under 1,200 / 1,500 kcal."""
    resting = bmr(profile["sex"], profile["age"], profile["height_cm"], profile["weight_kg"])
    return max(resting, KCAL_FLOOR[profile["sex"]])


def healthy_range_kg(height_cm: float) -> tuple[float, float]:
    """Weights for BMI 18.5 to 25 at this height, rounded to 0.5 kg."""
    m2 = (height_cm / 100.0) ** 2
    return (math.ceil(HEALTHY_BMI_MIN * m2 * 2) / 2, math.floor(HEALTHY_BMI_MAX * m2 * 2) / 2)


def goal_problem(profile: Mapping) -> str | None:
    """Why a goal weight can't be planned, or None (D39 guardrails)."""
    goal = _opt(profile, "goal_weight_kg")
    if goal is None:
        return None
    low, _ = healthy_range_kg(profile["height_cm"])
    if goal < low:
        return (f"{goal:g} kg is below a healthy weight for {profile['height_cm']:g} cm "
                f"(from about {low:g} kg). Forkcast won't plan for it.")
    if profile["age"] < 18 and goal < profile["weight_kg"] - KEEP_BAND_KG:
        return "Weight-loss plans are for adults. Please talk to a doctor about your weight goal."
    return None


def plan(profile: Mapping) -> dict | None:
    """How to reach the goal weight: daily calories, pace and rough timeline."""
    goal = _opt(profile, "goal_weight_kg")
    if goal is None or goal_problem(profile):
        return None
    daily_burn = burn(profile)
    diff = goal - profile["weight_kg"]
    out = {"goal_weight_kg": goal, "burn": round(daily_burn), "healthy_range_kg": healthy_range_kg(profile["height_cm"])}
    if abs(diff) < KEEP_BAND_KG:
        return out | {"direction": "keep", "calories": round(daily_burn), "change": 0,
                      "kg_per_week": 0.0, "weeks": 0, "limited": None}
    pace = _opt(profile, "pace") or "steady"
    wanted = PACE_KG_PER_WEEK[pace] * KCAL_PER_KG / 7.0
    limited = None
    if diff < 0:
        room = max(daily_burn - minimum_calories(profile), 0.0)
        cap = MAX_DEFICIT_SHARE * daily_burn
        change = min(wanted, cap, room)
        if change <= 0:
            limited = ("What you burn is already close to a safe minimum, so Forkcast won't plan "
                       "a deficit. A doctor or dietitian can help with this goal.")
        elif change < wanted - 1 and room <= cap:
            limited = "Slowed down to keep your daily calories above a safe minimum."
        elif change < wanted - 1:
            limited = "Slowed down: Forkcast keeps the deficit to at most a quarter of what you burn."
        calories = daily_burn - change
        direction = "lose"
    else:
        change = wanted
        calories = daily_burn + change
        direction = "gain"
    kg_per_week = change * 7.0 / KCAL_PER_KG
    weeks = math.ceil(abs(diff) / kg_per_week) if kg_per_week > 0 else None
    return out | {"direction": direction, "calories": round(calories), "change": round(change),
                  "kg_per_week": round(kg_per_week, 2), "weeks": weeks, "limited": limited}


def targets(profile: Mapping) -> dict:
    p = plan(profile)
    calories = p["calories"] if p else burn(profile) * (1.0 + GOAL_ADJUST[profile["goal"]])

    protein_g = PROTEIN_G_PER_KG * profile["weight_kg"]
    fat_g = calories * FAT_KCAL_SHARE / KCAL_PER_G_FAT
    carb_kcal = calories - protein_g * KCAL_PER_G_PROTEIN - fat_g * KCAL_PER_G_FAT
    carbs_g = max(carb_kcal, 0.0) / KCAL_PER_G_CARB

    return {
        "calories": round(calories),
        "protein_g": round(protein_g),
        "fat_g": round(fat_g),
        "carbs_g": round(carbs_g),
    }


# --- Macro fit (D20): steering suggestions toward the day's remaining budget ---

MACRO_KCAL = {"protein_g": KCAL_PER_G_PROTEIN, "carbs_g": KCAL_PER_G_CARB, "fat_g": KCAL_PER_G_FAT}

# Below this, the day is effectively done and macro steering is noise.
MIN_REMAINING_KCAL = 150.0


def remaining(totals: Mapping, target: Mapping) -> dict:
    """What is still to eat today, per macro and in calories (never negative)."""
    keys = ("calories", *MACRO_KCAL)
    return {k: max(target[k] - (totals.get(k) or 0.0), 0.0) for k in keys}


def _kcal_shares(macros: Mapping) -> list[float] | None:
    """Macros as a unit vector of calorie contributions, or None if empty.

    Grams aren't comparable across macros (fat carries 9 kcal/g, and carb
    counts dwarf protein counts), so the comparison happens in calorie space.
    """
    v = [(macros.get(k) or 0.0) * kcal for k, kcal in MACRO_KCAL.items()]
    norm = math.sqrt(sum(x * x for x in v))
    return [x / norm for x in v] if norm > 0 else None


def macro_fit(recipe: Mapping, rem: Mapping) -> float | None:
    """0-1: how well one serving matches what's left of the day, None if unscorable.

    Cosine between the recipe's macro composition and the remaining budget's,
    so "mostly protein" scores high when protein is what's missing. Overshooting
    the remaining calories decays the score rather than disqualifying the recipe —
    a big dish late in the day is a worse fit, not an error.
    """
    rv, dv = _kcal_shares(recipe), _kcal_shares(rem)
    if rv is None or dv is None:
        return None
    cos = sum(a * b for a, b in zip(rv, dv))
    kcal = recipe.get("calories") or 0.0
    overshoot = rem["calories"] / kcal if kcal > rem["calories"] > 0 else 1.0
    return max(cos, 0.0) * overshoot


def focus(rem: Mapping, target: Mapping) -> dict | None:
    """The macro furthest behind, as a share of its target (for the UI hint)."""
    gaps = {k: rem[k] / target[k] for k in MACRO_KCAL if target.get(k)}
    if not gaps:
        return None
    worst = max(gaps, key=gaps.get)
    return {"macro": worst, "grams": round(rem[worst])} if gaps[worst] > 0 else None
