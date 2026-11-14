"""Daily calorie/macro targets from the user profile (D12), and how well a
recipe fits what is left of the day (D20).

Mifflin-St Jeor BMR x activity factor = TDEE, adjusted by goal.
Protein 1.8 g/kg body weight, fat 25% of kcal, carbs the remainder.
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

PROTEIN_G_PER_KG = 1.8
FAT_KCAL_SHARE = 0.25

KCAL_PER_G_PROTEIN = 4.0
KCAL_PER_G_CARB = 4.0
KCAL_PER_G_FAT = 9.0


def bmr(sex: str, age: int, height_cm: float, weight_kg: float) -> float:
    base = 10.0 * weight_kg + 6.25 * height_cm - 5.0 * age
    return base + (5.0 if sex == "m" else -161.0)


def targets(profile: Mapping) -> dict:
    tdee = bmr(profile["sex"], profile["age"], profile["height_cm"], profile["weight_kg"])
    tdee *= ACTIVITY_FACTORS[profile["activity"]]
    calories = tdee * (1.0 + GOAL_ADJUST[profile["goal"]])

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
