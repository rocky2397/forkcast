"""The ingredient nutrition table (D49): app/ingredient_nutrition.json."""

from app import foods
from app.recipes import STAPLES

# Spices are mostly fibre and drinks mostly alcohol, which the three macros
# don't cover; everything else should roughly add up (4/4/9 kcal per gram).
NOT_ADDING_UP = ("Spices", "Alcoholic", "Leavening", "Vanilla", "Sweetener", "Seasoning",
                 "Oat bran", "Carob", "Cocoa", "Liqueur", "Whiskey")


def test_every_entry_has_all_four_values():
    for c, row in foods.table().items():
        for form in [row] + ([row["cooked"]] if "cooked" in row else []):
            assert all(form[k] is not None and form[k] >= 0 for k in ("kcal", "protein_g", "carbs_g", "fat_g")), c


def test_the_values_add_up():
    for c, row in foods.table().items():
        for form in [row] + ([row["cooked"]] if "cooked" in row else []):
            if form["usda"].startswith(NOT_ADDING_UP):
                continue
            est = 4 * form["protein_g"] + 4 * form["carbs_g"] + 9 * form["fat_g"]
            assert abs(est - form["kcal"]) <= max(40, 0.2 * form["kcal"]), (c, form["usda"])


def test_the_everyday_ingredients_were_checked_by_hand():
    for c in ("banana", "milk", "egg", "rice", "oat", "chicken", "olive_oil", "flour", *STAPLES - {"all_purpose_flour"}):
        assert foods.table()[c]["picked"] == "hand", c
    assert sum(r["picked"] == "hand" for r in foods.table().values()) >= 380


def test_cooked_forms_are_lighter_per_gram_than_dry_ones():
    for c, row in foods.table().items():
        if "cooked" in row and c not in ("chicken", "beef", "potato"):  # these lose water when cooked
            assert row["cooked"]["kcal"] < row["kcal"], c


def test_portions_say_their_weight():
    banana = foods.food("banana")
    assert {"label": "1 medium", "grams": 118.0} in banana["portions"]
    assert not any(True for r in foods.table().values() for p in r["portions"] if '"' in p[0])
