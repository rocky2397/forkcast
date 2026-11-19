"""The ingredient nutrition table (D49): app/ingredient_nutrition.json."""

from app import foods
from app.recipes import STAPLES

# D53: values follow EU labelling, so energy is 4 kcal per g of protein and
# carbohydrate, 9 per g of fat, 2 per g of fibre and 7 per g of alcohol.


def test_energy_follows_the_eu_factors():
    for c, row in foods.table().items():
        for form in [row] + ([row["cooked"]] if "cooked" in row else []):
            est = (4 * form["protein_g"] + 4 * form["carbs_g"] + 9 * form["fat_g"]
                   + 2 * form["fibre_g"] + 7 * form.get("alcohol_g", 0))
            assert abs(est - form["kcal"]) <= 1, (c, form["usda"])


def test_carbs_leave_out_fibre_as_on_eu_labels():
    oats = foods.table()["oat"]
    assert oats["fibre_g"] == 10.1
    assert oats["carbs_g"] == 57.6  # 67.7 by the US definition
    assert abs(oats["kcal"] - 362) <= 1


def test_no_us_measures():
    import re
    us = re.compile(r"\b(cups?|fl oz|oz|quarts?|pints?|NLEA)\b", re.I)
    assert not [p for r in foods.table().values() for p in r["portions"] if us.search(p[0])]


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
