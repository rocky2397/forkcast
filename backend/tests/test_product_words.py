"""More product words (D29): "tomato juice" is not tomatoes.

Extends D27 with the product words the stage 1 tightening found still
slipping through, plus the span fixes that came with it. Every case is a false
"cookable" recipe or wrong match from the development data, or a guard against
over-correcting.
"""

import pytest

from app.normalize import Normalizer

VOCAB = [
    "tomato", "carrot", "lemon", "lime", "orange", "apple", "chicken", "pork",
    "corn", "potato", "onion", "chocolate", "vanilla", "raisin", "flour",
    "flour_tortilla", "tortilla", "bread", "bread_crumbs", "syrup", "maple_syrup",
    "corn_syrup", "wafer", "cookie", "cracker", "graham_cracker", "sausage",
    "chorizo", "italian_sausage", "pickled_cucumber", "pickle_relish", "dill",
    "hummus", "gelatin", "noodle", "egg_noodle", "pasta", "kidney_bean",
    "kidney", "egg", "fruit_juice", "vegetable_juice", "baked_beans", "bean",
    "corn_flakes", "bell_pepper", "black_pepper", "red_pepper", "salt",
    "sun_dried_tomato", "peach", "cheese", "kiwi", "fruit", "green_chili",
    "chili_pepper", "tea", "tuna", "oil",
]


@pytest.fixture
def n():
    return Normalizer(VOCAB)


@pytest.mark.parametrize("raw,expected", [
    ("tomato juice", "vegetable_juice"),          # 257 corpus rows matched tomato
    ("carrot juice", "vegetable_juice"),
    ("apple juice", "fruit_juice"),
    ("cranberry juice cocktail", "fruit_juice"),
    ("chocolate syrup", "syrup"),                 # 283 rows matched chocolate
    ("vanilla wafers", "wafer"),
    ("chocolate chip cookies", "cookie"),
    ("butter flavored crackers", "cracker"),
    ("chicken sausage", "sausage"),               # a false "cookable" in two kitchens
    ("Organic Raisin Bread", "bread"),
    ("dill pickles", "pickled_cucumber"),
    ("Zesty Lemon Hommus", "hummus"),
    ("cherry jell-o", "gelatin"),
    ("pork and beans", "baked_beans"),
    ("corn flake crumbs", "corn_flakes"),
])
def test_the_product_wins_over_its_food_word(n, raw, expected):
    assert n.match(raw) == expected


@pytest.mark.parametrize("raw", [
    "creamed corn",
    "white cream-style corn",
    "instant potato flakes",
    "instant mashed potatoes",
    "barbecue potato chips",
    "french fried onions",
    "Macaroni & Cheese",
    "beef flavored rice-a-roni",
    "condensed chicken with rice soup",           # the soup, not the chicken
])
def test_a_product_without_a_name_abstains(n, raw):
    assert n.match(raw) is None


@pytest.mark.parametrize("raw,expected", [
    ("lemon juice", "lemon"),                     # citrus juice comes from the fruit
    ("fresh lime juice", "lime"),
    ("orange juice", "orange"),
    ("juice of 1 lemon", "lemon"),
    ("maple syrup", "maple_syrup"),               # the match is itself the product
    ("corn syrup", "corn_syrup"),
    ("graham cracker crumbs", "graham_cracker"),
    ("bread crumbs", "bread_crumbs"),
    ("pickle relish", "pickle_relish"),
    ("chorizo sausage", "chorizo"),               # already a sausage (same food class)
    ("italian sausage", "italian_sausage"),
    ("diced tomatoes with juice", "tomato"),      # packed in its own liquid
    ("peaches in syrup", "peach"),
    ("mashed potatoes", "potato"),
    ("chocolate chips", "chocolate"),
])
def test_ordinary_ingredients_are_left_alone(n, raw, expected):
    assert n.match(raw) == expected


@pytest.mark.parametrize("raw,expected", [
    ("sweet green pepper", "bell_pepper"),        # was black pepper, a pantry staple
    ("yellow sweet pepper", "bell_pepper"),
    ("yellow peppers", "bell_pepper"),
    ("salt and pepper", "salt"),                  # an alias still can't beat a name
    ("red pepper", "red_pepper"),                 # ambiguous, left as it was
])
def test_sweet_peppers_are_bell_peppers(n, raw, expected):
    assert n.match(raw) == expected


@pytest.mark.parametrize("raw,expected", [
    ("7-inch flour tortillas", "flour_tortilla"),  # the plural hid the longer name
    ("red kidney beans", "kidney_bean"),
    ("wide egg noodles", "egg_noodle"),
    ("spaghetti noodles", "pasta"),               # a later spelling must *extend* the match
    ("kiwi fruits", "kiwi"),
    ("green chili peppers", "green_chili"),
    ("sun-dried tomatoes packed in oil", "sun_dried_tomato"),  # a D27 known miss
])
def test_spans_across_spellings(n, raw, expected):
    assert n.match(raw) == expected
