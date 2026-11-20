"""The ingredient nutrition table (D49): app/ingredient_nutrition.json."""

from app import foods
from app.recipes import STAPLES

# D53: values follow EU labelling, so energy is 4 kcal per g of protein and
# carbohydrate, 9 per g of fat, 2 per g of fibre and 7 per g of alcohol.


def test_energy_follows_the_eu_factors():
    for c, row in foods.table().items():
        if row.get("source") == "openfoodfacts":
            continue  # medians of German labels (D55), as the packs print them
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


# D61: amounts and several foods in one typed line. D62: dishes by name.

LINE_VOCAB = ["chicken", "rice", "egg", "milk", "yogurt", "banana", "chickpea", "oat", "coffee", "sugar", "butter",
              "sweet_and_sour_sauce", "pasta"]


def _line(q):
    from app.normalize import Normalizer
    out = foods.parse(Normalizer(LINE_VOCAB), q)
    return [(p["food"]["canonical"], p.get("grams"), p.get("count"), p.get("portion"), p["cooked"])
            for p in out["parts"]], [m["query"] for m in out["missing"]], out["dishes"]


def test_a_count_is_pieces_and_grams_are_grams():
    assert _line("2 Eier")[0] == [("egg", None, 2, "1 large", False)]
    assert _line("zwei Eier")[0] == [("egg", None, 2, "1 large", False)]
    assert _line("150g Reis gekocht")[0] == [("rice", 150, None, None, True)]
    assert _line("Reis gekocht 150 g")[0] == [("rice", 150, None, None, True)]
    assert _line("1,5 l Milch")[0] == [("milk", 1500, None, None, False)]
    assert _line("2 coffee")[0] == [("coffee", None, 2, "1 glass", False)]  # a drink's glass


def test_commas_separate_foods_and_a_lone_amount_belongs_to_the_one_before():
    # The stage 7 phrasing: "Haferflocken, 50 g" is one food, not two.
    assert _line("Haferflocken, 50 g")[0] == [("oat", 50, None, None, False)]
    parts, missing, _ = _line("2 eggs, Blubberkraut, banana")
    assert [p[0] for p in parts] == ["egg", "banana"] and missing == ["Blubberkraut"]


def test_with_and_and_split_unless_they_name_one_food():
    assert [p[0] for p in _line("Hähnchen mit Reis")[0]] == ["chicken", "rice"]
    assert [p[0] for p in _line("coffee with milk and sugar")[0]] == ["coffee", "milk", "sugar"]
    assert [p[0] for p in _line("sweet and sour sauce")[0]] == ["sweet_and_sour_sauce"]
    # The amount before the first food is that food's, not the meal's.
    assert _line("2 eggs mit Butter")[0] == [("egg", None, 2, "1 large", False), ("butter", None, None, None, False)]


def test_dishes_are_their_typical_parts():
    parts, missing, dishes = _line("Cappuccino")
    assert dishes == ["cappuccino"] and missing == []
    assert parts == [("espresso", 30, None, None, False), ("milk", 120, None, None, False)]
    assert _line("Kaffee mit Milch")[2] == ["coffee with milk"]  # a dish, not black coffee
    assert [p[1] for p in _line("2 Cappuccino")[0]] == [60, 240]
    bolo, _, _ = _line("Spaghetti Bolognese")
    assert ("pasta", 250, None, None, True) in bolo and any(p[0] == "beef" for p in bolo)
    doener, _, names = _line("Döner")
    assert names == ["Döner"] and doener[0][0] == "pita_bread"


def test_every_dish_adds_up_to_a_plausible_serving():
    # Typical servings, so typical totals: catches a part with the wrong values.
    expect = {"cappuccino": (60, 130), "latte macchiato": (100, 180), "flat white": (60, 130),
              "coffee with milk": (15, 60), "spaghetti bolognese": (600, 900), "Döner": (550, 800),
              # D67
              "Käsebrot": (200, 320), "Butterbrot": (150, 250), "Apfelschorle": (40, 100),
              "Currywurst": (380, 560), "Schnitzel": (380, 600)}
    for name, typed, parts in foods._DISHES:
        assert foods.dishes()[foods._clean(typed[0])][0] == name
        kcal = foods.totals([{"canonical": c, "grams": g, "cooked": cooked} for c, g, cooked in parts])["calories"]
        low, high = expect[name]
        assert low <= kcal <= high, (name, kcal)


# D63: fat levels for milk and yogurt.

def test_fat_levels_are_their_own_foods_with_german_values():
    t = foods.table()
    assert t["low_fat_milk"]["source"] == "openfoodfacts" and 45 <= t["low_fat_milk"]["kcal"] <= 49
    assert 1.4 <= t["low_fat_milk"]["fat_g"] <= 1.6
    assert t["skim_milk"]["fat_g"] < 0.5
    assert t["low_fat_yogurt"]["source"] == "openfoodfacts" and t["low_fat_yogurt"]["kcal"] < t["yogurt"]["kcal"]
    # D65: Greek yogurt as German shelves have it, about 10% fat (the USDA's is 5%).
    assert t["greek_yogurt"]["source"] == "openfoodfacts" and 9 <= t["greek_yogurt"]["fat_g"] <= 11
    names = [v["name"] for v in foods.food("milk")["variants"]]
    assert names == ["whole milk", "low-fat milk", "skimmed milk"]
    assert foods.food("banana")["variants"] is None


def test_typed_fat_levels_find_the_right_milk_and_yogurt():
    assert [p[0] for p in _line("fettarme Milch")[0]] == ["low_fat_milk"]
    assert [p[0] for p in _line("Milch 1,5%")[0]] == ["low_fat_milk"]
    assert [p[0] for p in _line("1,5% Milch")[0]] == ["low_fat_milk"]  # not "1 of ,5% Milch"
    assert [p[0] for p in _line("Magermilch")[0]] == ["skim_milk"]
    assert [p[0] for p in _line("Vollmilch")[0]] == ["milk"]
    assert _line("200 ml fettarme Milch")[0] == [("low_fat_milk", 200, None, None, False)]


# D64: canned beans and peas, drained.

def test_canned_is_a_form_of_its_own():
    chick = foods.food("chickpea")
    # D65: from German cans, which hold more water than the USDA's (130 kcal).
    assert chick["canned"]["source"] == "openfoodfacts" and 110 <= chick["canned"]["per_100g"]["calories"] <= 125
    assert chick["source"] == "usda" and chick["cooked"]["source"] == "usda"  # the other forms stay
    # Canned chickpeas hold more water than boiled ones: fewer calories per 100 g.
    assert chick["canned"]["per_100g"]["calories"] < chick["cooked"]["per_100g"]["calories"]
    assert foods.food("rice")["canned"] is None
    canned = foods.totals([{"canonical": "chickpea", "grams": 100, "canned": True}])["calories"]
    assert canned == round(foods.table()["chickpea"]["canned"]["kcal"], 1)
    try:
        foods.totals([{"canonical": "rice", "grams": 100, "canned": True}])
        raise AssertionError("rice has no canned form")
    except ValueError as e:
        assert e.args == ("rice", "canned")


def test_typed_cans_start_canned():
    assert _line("Kichererbsen aus der Dose")[0] == [("chickpea", None, None, None, False)]
    from app.normalize import Normalizer
    out = foods.parse(Normalizer(["chickpea", "kidney_bean"]), "Kidneybohnen (Dose), Kichererbsen")
    assert [(p["food"]["canonical"], p["canned"]) for p in out["parts"]] == [("kidney_bean", True), ("chickpea", False)]


def test_a_food_starts_at_a_portion_people_have():
    # D60: "Toast mit Butter" started at 100 g of each (1,000 kcal).
    start = {c: foods.food(c)["default_portion"] for c in
             ["banana", "egg", "apple", "toast", "butter", "olive_oil", "honey", "milk", "rice"]}
    assert start == {"banana": "1 medium", "egg": "1 large", "apple": "1 large", "toast": "1 slice",
                     "butter": "1 tbsp", "olive_oil": "1 tablespoon", "honey": "1 tbsp", "milk": None,
                     "rice": None}
    assert _line("2 Toast")[0] == [("toast", None, 2, "1 slice", False)]


# D67: everyday German words and spoons, found missing in the second review.

def test_everyday_german_foods_are_found():
    from app.normalize import Normalizer
    n = Normalizer(LINE_VOCAB + ["wine", "pretzel", "rice_cake", "nut", "sugar", "olive_oil", "honey", "bread"])
    found = {q: [p["food"]["canonical"] for p in foods.parse(n, q)["parts"]]
             for q in ["Wein", "Brezel", "Spiegelei", "Burger", "Lasagne", "Reiswaffel", "Apfelsaft"]}
    assert found == {"Wein": ["wine"], "Brezel": ["pretzel"], "Spiegelei": ["fried_egg"], "Burger": ["hamburger"],
                     "Lasagne": ["lasagna"], "Reiswaffel": ["rice_cake"], "Apfelsaft": ["apple_juice"]}
    assert foods.parse(n, "Käsebrot")["dishes"] == ["Käsebrot"]  # not plain bread
    assert foods.food("lasagna")["default_portion"] == "1 piece center"  # 255 g, not 100 g
    assert foods.parse(n, "Brot mit Käse")["dishes"] == ["Käsebrot"]


def test_spoons_slices_and_a_handful():
    from app.normalize import Normalizer
    n = Normalizer(LINE_VOCAB + ["nut", "sugar", "olive_oil", "honey", "bread"])
    one = lambda q: [(p["food"]["canonical"], p.get("grams"), p.get("count"), p.get("portion"))
                     for p in foods.parse(n, q)["parts"]]
    assert one("1 TL Zucker") == [("sugar", None, 1, "1 tsp")]  # not a sugar packet
    assert one("2 EL Olivenöl") == [("olive_oil", None, 2, "1 tablespoon")]
    assert one("1 Scheibe Brot") == [("bread", None, 1, "1 slice")]
    assert one("3 TL Honig") == [("honey", 15.0, None, None)]  # no teaspoon portion: 5 g each
    assert one("eine Handvoll Nüsse") == [("nut", 30.0, None, None)]
