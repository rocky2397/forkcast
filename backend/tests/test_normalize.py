"""Ingredient matching (D24 determinism, D25 compound names, D26 connectors and negations).

A hand-written vocabulary rather than the real 1,790 names: these assert the
*rules*, and a fixture vocab keeps them offline and readable. Corpus-wide
effects are measured with backend/scripts/normalizer_diff.py instead.
"""

import pytest

from app.normalize import Normalizer

VOCAB = [
    "tomato", "cherry", "grape", "plum", "sun_dried_tomato",
    "onion", "scallion", "garlic", "clove", "bell_pepper",
    "salt", "black_pepper", "flour", "corn", "cornstarch", "bread",
    "basil", "oregano", "coriander", "spinach", "potato", "sweet_potato",
    "tuna", "water", "oil", "olive_oil", "anchovy", "peach", "syrup",
    "green_chili", "juice", "gluten_free_flour", "artichoke", "sugar",
    "cream_of_chicken_soup", "chicken", "bean",
]


@pytest.fixture
def n():
    return Normalizer(VOCAB)


@pytest.mark.parametrize("raw", [
    "cherry tomatoes",          # the reported bug: read as the fruit
    "cherry tomato",
    "yellow cherry tomatoes",   # descriptor the stripper doesn't know
    "yellow cherry tomato",
    "grape tomatoes",
    "italian plum tomatoes",
    "crushed plum tomatoes",
])
def test_compound_tomatoes_are_tomatoes(n, raw):
    assert n.match(raw) == "tomato"


@pytest.mark.parametrize("raw,expected", [
    ("cherry", "cherry"),        # the fruit on its own must survive
    ("cherries", "cherry"),
    ("grape", "grape"),
    ("tomatoes", "tomato"),
])
def test_the_narrow_words_still_match_themselves(n, raw, expected):
    assert n.match(raw) == expected


@pytest.mark.parametrize("raw,expected", [
    # "clove" is a canonical spice, but garlic is the longer span and wins.
    ("garlic clove", "garlic"),
    ("garlic cloves", "garlic"),
    # Two ingredients in one string: whichever is picked, the rule must not
    # start preferring the trailing word.
    ("salt and pepper", "salt"),
    ("salt & pepper", "salt"),
])
def test_compound_rule_leaves_these_alone(n, raw, expected):
    """The cases that "last word wins" and "longest match wins" both broke."""
    assert n.match(raw) == expected


def test_corn_flour_is_excluded_from_upgrades(n):
    """"corn flour" -> cornstarch is right alone, wrong as an override."""
    assert n.match("masa corn flour") == "flour"
    assert n.match("yellow corn flour") == "flour"
    assert n.match("corn flour") == "cornstarch"  # the plain alias still applies


def test_green_onion_resolves_to_scallion(n):
    assert n.match("green onion tops") == "scallion"
    assert n.match("green onion") == "scallion"
    assert n.match("onion") == "onion"


def test_equal_length_spans_resolve_the_same_way_every_time():
    """Ties were broken by set iteration order, so this varied per process:
    "bread flour" matched bread or flour depending on the hash seed."""
    results = {Normalizer(VOCAB).match("bread flour") for _ in range(5)}
    assert results == {"bread"}  # alphabetically first among equal-length spans


def test_longer_spans_still_beat_shorter_ones(n):
    assert n.match("sweet potato") == "sweet_potato"
    assert n.match("sun-dried tomatoes") == "sun_dried_tomato"


def test_descriptors_are_stripped(n):
    assert n.match("fresh chopped basil") == "basil"
    assert n.match("frozen chopped spinach") == "spinach"


def test_unknown_strings_stay_unmatched(n):
    assert n.match("instant pudding mix") is None
    assert n.match("") is None


# --- "X with Y" / "X in Y": the ingredient is the head, not the packing (D26) ---


@pytest.mark.parametrize("raw,expected", [
    ("diced tomatoes with green chilies", "tomato"),   # matched the chili
    ("diced tomatoes with juice", "tomato"),           # matched nothing at all
    ("tomatoes with basil", "tomato"),
    ("tuna in water", "tuna"),                         # matched the water
    ("anchovies packed in oil", "anchovy"),            # matched the oil
    ("peaches in syrup", "peach"),                     # matched the syrup
    ("green onions with tops", "scallion"),
])
def test_the_head_of_a_connector_phrase_wins(n, raw, expected):
    assert n.match(raw) == expected


def test_connector_phrases_that_were_already_right_stay_right(n):
    assert n.match("chicken legs with thigh") == "chicken"
    assert n.match("water-packed artichoke hearts") == "artichoke"


def test_an_unmatchable_head_falls_back_to_the_whole_phrase(n):
    """Truncation is an attempt, not a commitment — otherwise this returns None."""
    assert n.match("packed in olive oil") == "olive_oil"


def test_and_is_not_a_connector(n):
    """Cutting at "and" rewrote "salt and black pepper" across 327 corpus rows."""
    assert n.match("salt and black pepper") == "black_pepper"


@pytest.mark.parametrize("raw,expected", [
    ("no-salt-added diced tomatoes", "tomato"),   # matched the absent salt
    ("no-salt-added whole tomatoes", "tomato"),
    ("fat-free cream of chicken soup", "cream_of_chicken_soup"),
    ("sugar-free syrup", "syrup"),
])
def test_a_negated_ingredient_is_not_the_ingredient(n, raw, expected):
    assert n.match(raw) == expected


def test_a_name_that_is_itself_negated_survives(n):
    """"gluten free flour" is its own ingredient; stripping leaves plain flour."""
    assert n.match("gluten-free flour") == "gluten_free_flour"
