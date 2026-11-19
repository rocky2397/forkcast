"""Nutrition per ingredient, for meals built from ingredients and grams (D49).

The values come from the USDA's FoodData Central (SR Legacy, public domain),
mapped onto Forkcast's ingredients by scripts/build_ingredient_nutrition.py:
ingredient_nutrition.json holds each ingredient's USDA food, calories and
macros per 100 g, the USDA's portions (1 medium banana, 118 g) and, for rice,
pasta, beans and a few others, the cooked form as well.

The 300 ingredients used most in recipes, plus 80 sampled from the rest, were
checked by hand ("picked": "hand"). The others were matched by name and a
sample of 80 was about 84% right, so the app shows which USDA food it used
and says when it was matched by name only.
"""

import json
from functools import lru_cache
from pathlib import Path

from . import embeddings
from .recipes import STAPLES

TABLE = Path(__file__).with_name("ingredient_nutrition.json")
MACROS = ("calories", "protein_g", "carbs_g", "fat_g")


@lru_cache(maxsize=1)
def table() -> dict[str, dict]:
    with open(TABLE) as f:
        return json.load(f)


def label(canonical: str) -> str:
    return canonical.replace("_", " ")


def food(canonical: str) -> dict | None:
    """What the app shows for one ingredient, or None without USDA values."""
    row = table().get(canonical)
    if row is None:
        return None

    def form(r: dict) -> dict:
        return {
            "usda": r["usda"],
            "fdc_id": r["fdc_id"],
            "per_100g": {"calories": r["kcal"], "protein_g": r["protein_g"],
                         "carbs_g": r["carbs_g"], "fat_g": r["fat_g"]},
            "portions": [{"label": p[0], "grams": p[1]} for p in r["portions"]],
        }

    out = {"canonical": canonical, "name": label(canonical), "checked": row["picked"] == "hand", **form(row)}
    out["cooked"] = form(row["cooked"]) if "cooked" in row else None
    return out


def lookup(normalizer, raw: str) -> dict:
    """A typed food name -> {"food": ... | None, "canonical": ..., "suggestions": [...]}.

    canonical is what the name matched even when there are no USDA values for
    it, so the app can say "no nutrition for quark yet" rather than "unknown".
    Suggestions are other ingredients the name could mean, with values.
    """
    canonical = normalizer.match(raw)
    found = food(canonical) if canonical else None
    suggestions = [
        {"canonical": c, "name": label(c)}
        for c in normalizer.suggest(raw, limit=5)
        if c != canonical and c in table()
    ][:3]
    return {"query": raw, "canonical": canonical, "food": found, "suggestions": suggestions}


def totals(items: list[dict]) -> dict[str, float]:
    """Sum of [{canonical, grams, cooked}] -> calories and macros, rounded.

    Raises KeyError naming the first ingredient without values, and ValueError
    for a cooked form an ingredient doesn't have.
    """
    acc = dict.fromkeys(MACROS, 0.0)
    for it in items:
        row = table().get(it["canonical"])
        if row is None:
            raise KeyError(it["canonical"])
        if it.get("cooked"):
            if "cooked" not in row:
                raise ValueError(it["canonical"])
            row = row["cooked"]
        f = it["grams"] / 100
        acc["calories"] += row["kcal"] * f
        acc["protein_g"] += row["protein_g"] * f
        acc["carbs_g"] += row["carbs_g"] * f
        acc["fat_g"] += row["fat_g"] * f
    return {k: round(v, 1) for k, v in acc.items()}


MIN_TASTE_INGREDIENTS = 2


def teaches_taste(canonicals: list[str]) -> bool:
    """Whether a built meal says something about what you like to eat.

    The recipe feed compares recipes with dishes, and one food on its own (a
    banana) isn't a dish: it would make every banana recipe "Like your banana".
    Two or more ingredients that aren't staples (salt, oil, flour...) are.
    """
    candidates = {c for c in canonicals if c not in STAPLES}
    if len(candidates) < MIN_TASTE_INGREDIENTS:  # no need to load the vectors
        return False
    usable = {c for c in candidates if embeddings.ingredient_vector(c, "cooc") is not None}
    return len(usable) >= MIN_TASTE_INGREDIENTS
