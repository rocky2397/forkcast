"""Daily calorie/macro targets from the user profile (D12).

Mifflin-St Jeor BMR x activity factor = TDEE, adjusted by goal.
Protein 1.8 g/kg body weight, fat 25% of kcal, carbs the remainder.
"""

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
