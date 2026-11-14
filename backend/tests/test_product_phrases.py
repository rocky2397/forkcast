"""Product phrases (D27): "chicken stock" is not chicken.

A product named after its main food must match the product, or nothing. A
wrong match lists a recipe as "cookable now" when it isn't; a missed match
only drops it. Every case here is a false "cookable" recipe or a mismatched
string found by forkcast-evals stage 1, or a guard against over-correcting.
"""

import pytest

from app.normalize import Normalizer

VOCAB = [
    "chicken", "beef", "tomato", "sun_dried_tomato", "basil", "pesto",
    "sugar", "salt", "vanilla", "almond", "yogurt", "pudding", "chocolate",
    "pasta", "pasta_sauce", "broth", "chicken_broth", "hot_sauce", "sriracha",
    "ice", "garlic", "taco_seasoning", "fruit_preserves", "mushroom",
    "cream_of_mushroom_soup", "soy_sauce", "lemon", "oil", "hot_dog",
]


@pytest.fixture
def n():
    return Normalizer(VOCAB)


@pytest.mark.parametrize("raw", [
    "chicken stock",              # 1,703 corpus rows matched chicken
    "tomato paste",               # 1,448 rows matched tomato
    "beef bouillon cube",
    "chicken bouillon powder",    # product word in the middle
    "chicken stock cubes",
    "almond extract",
    "tomato sauce",
    "Classic Tomato Puree",
    "onion soup mix",
    "hot dog buns",               # buns, not hot dogs
])
def test_a_product_without_a_name_abstains(n, raw):
    assert n.match(raw) is None


@pytest.mark.parametrize("raw", [
    "powdered sugar",             # 2,200 rows matched the sugar staple
    '"confectioners sugar"',
    "icing sugar",
    "seasoning salt",
])
def test_sugar_and_salt_products_are_not_the_staple(n, raw):
    assert n.match(raw) is None


@pytest.mark.parametrize("raw,expected", [
    ("basil pesto", "pesto"),                      # pesto is in the vocab
    ("Raw Basil Pesto", "pesto"),                  # a D26 regression
    ("Vanilla Skyr Nonfat Yogurt", "yogurt"),
    ("chocolate pudding", "pudding"),
    ("raspberry preserves", "fruit_preserves"),
    ("prego spaghetti sauce", "pasta_sauce"),
    ("beef broth", "broth"),
    ("condensed cream of mushroom soup", "cream_of_mushroom_soup"),
])
def test_the_product_wins_when_the_vocabulary_names_it(n, raw, expected):
    assert n.match(raw) == expected


@pytest.mark.parametrize("raw,expected", [
    ("pesto sauce", "pesto"),                      # the match is itself a product
    ("taco seasoning mix", "taco_seasoning"),
    ("vanilla instant pudding mix", "pudding"),
    ("sriracha sauce", "sriracha"),
    ("pure vanilla extract", "vanilla"),           # extract is how vanilla is sold
    ("ice cubes", "ice"),
    ("garlic granules", "garlic"),                 # a form, not a product
    ("soy sauce", "soy_sauce"),
    ("chicken broth", "chicken_broth"),
    ("lemon juice", "lemon"),                      # juice is not a product word
])
def test_ordinary_names_are_left_alone(n, raw, expected):
    assert n.match(raw) == expected


def test_a_deliberate_abstain_does_not_fall_through_to_the_tail(n):
    """The head "tomato sauce" abstains; the rest must not answer basil."""
    assert n.match("tomato sauce with basil and garlic") is None


def test_a_longer_name_survives_descriptor_stripping(n):
    """"dried" is a descriptor, which used to leave "sun tomato" -> tomato."""
    assert n.match("sun-dried tomato packed in oil") == "sun_dried_tomato"
