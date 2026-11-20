"""Ingredient matching (D24 determinism, D25 compound names, D26 connectors and negations).

A hand-written vocabulary rather than the real 1,790 names: these assert the
*rules*, and a fixture vocab keeps them offline and readable. Corpus-wide
effects are measured with backend/scripts/normalizer_diff.py instead.
"""

import pytest
from conftest import needs_embeddings

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
    "bread flour" matched bread or flour depending on the hash seed. (Bread
    flour now has its own alias, D29, so the tie is shown with another pair.)"""
    results = {Normalizer(VOCAB).match("onion basil") for _ in range(5)}
    assert results == {"basil"}  # alphabetically first among equal-length spans


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


# --- D35: names read off European packaging, and scanned juice -------------

D35_VOCAB = [
    "yogurt", "soy_yogurt", "milk", "soy_milk", "oat_milk", "coconut_milk",
    "almond_milk", "buttermilk", "milk_chocolate", "chocolate", "strawberry",
    "vanilla", "eggplant", "zucchini", "beet", "kiwi", "fruit", "tangerine",
    "orange", "lemon", "grapefruit", "apple", "fruit_juice", "mandarin_fish",
]


@pytest.fixture
def d35():
    return Normalizer(D35_VOCAB)


@pytest.mark.parametrize("raw, expected", [
    ("natural yoghurt", "yogurt"),          # British spelling
    ("vanilla yoghurt", "yogurt"),          # flavoured dairy is the dairy
    ("apricot yoghurt", "yogurt"),
    ("soy yoghurt", "soy_yogurt"),
    ("soya milk", "soy_milk"),              # was plain milk
    ("aubergines", "eggplant"),
    ("courgette", "zucchini"),
    ("beetroot", "beet"),
    ("kiwi fruit", "kiwi"),                 # was "fruit"
    ("satsumas", "tangerine"),
    ("mandarin oranges", "tangerine"),
    ("mandarin fish", "mandarin_fish"),     # a longer name still wins
    ("strawberry milk", "milk"),            # not strawberries
    ("chocolate milk", "milk"),
    ("coconut milk", "coconut_milk"),       # plant milks keep their names
    ("almond milk", "almond_milk"),
    ("coconut milk vanilla yogurt", "yogurt"),
    ("buttermilk", "buttermilk"),
    ("milk chocolate", "milk_chocolate"),
    ("orange juice", "orange"),             # in a recipe, citrus juice is the fruit
])
def test_d35_european_names_and_flavoured_dairy(d35, raw, expected):
    assert d35.match(raw) == expected


@pytest.mark.parametrize("raw, expected", [
    ("orange juice", "fruit_juice"),        # a scanned carton is not oranges
    ("red grapefruit juice", "fruit_juice"),
    ("juice", "fruit_juice"),
    ("apple juice", "fruit_juice"),
    ("orange", "orange"),                   # the fruit itself is unchanged
    ("natural yoghurt", "yogurt"),
])
def test_d35_scanned_products(d35, raw, expected):
    from app.normalize import packaged

    assert packaged(d35, raw) == expected


# --- D46: skyr, and "Did you mean…?" for what isn't recognised ---

@pytest.fixture
def n46():
    return Normalizer(VOCAB + ["yogurt", "zucchini", "mozzarella_cheese", "chicken_broth", "chicken_fat"])


@pytest.mark.parametrize("raw", ["skyr", "Skyr", "skyr natural", "vanilla skyr"])
def test_skyr_is_yogurt(n46, raw):
    assert n46.match(raw) == "yogurt"


@pytest.mark.parametrize("raw, first", [
    ("tomatoe", "tomato"),
    ("zuchini", "zucchini"),
    ("mozarella", "mozzarella_cheese"),
    # Each word corrected first, then matched as usual: chicken, not broth or fat.
    ("chiken breast", "chicken"),
    ("yougurt", "yogurt"),
])
def test_a_misspelling_gets_the_right_suggestion_first(n46, raw, first):
    assert n46.match(raw) is None
    assert n46.suggest(raw)[0] == first


@pytest.mark.parametrize("raw", ["Arla", "Müller Corner", "xyz", ""])
def test_nothing_close_gets_no_guess(n46, raw):
    assert n46.suggest(raw) == []


def test_at_most_three_suggestions_without_repeats(n46):
    got = n46.suggest("chiken")
    assert len(got) <= 3 and len(got) == len(set(got))


# --- D47: German names, translated and then matched as English ---

@pytest.fixture
def de():
    return Normalizer(VOCAB + ["yogurt", "carrot", "lemon", "beef", "paprika", "parsley", "red_onion",
                               "cream", "egg", "rice", "speck", "banana"])


@pytest.mark.parametrize("raw, name", [
    ("Zwiebel", "onion"), ("Zwiebeln", "onion"), ("rote Zwiebel", "red_onion"),
    ("Knoblauch", "garlic"), ("Kartoffeln", "potato"), ("Süßkartoffel", "sweet_potato"),
    ("Hähnchen", "chicken"), ("Hähnchenbrust", "chicken"), ("Hackfleisch", "beef"),
    ("Möhren", "carrot"), ("Zitrone", "lemon"), ("frische Petersilie", "parsley"),
    ("Eier", "egg"), ("Sahne", "cream"), ("Reis", "rice"), ("Joghurt", "yogurt"),
    ("Olivenöl", "olive_oil"),
])
def test_german_names(de, raw, name):
    assert de.match(raw) == name


def test_paprika_alone_is_the_spice_but_a_red_one_is_a_bell_pepper(de):
    assert de.match("Paprika") == "paprika"
    assert de.match("rote Paprika") == "bell_pepper"
    assert de.match("Paprikaschote") == "bell_pepper"


def test_english_wins_where_both_languages_use_a_word(de):
    assert de.match("speck") == "speck"  # the Italian ham, as English recipes mean it


def test_another_languages_name_is_not_read_as_german(de):
    # "Banane" is German, but "creme de banane" is a liqueur, not a banana.
    assert de.match("creme de banane") != "banana"


def test_a_misspelled_german_word_gets_a_suggestion(de):
    assert de.match("Zwiebl") is None
    assert de.suggest("Zwiebl")[0] == "onion"


@needs_embeddings
def test_every_german_word_is_one_the_english_matcher_does_not_know():
    """A German word English already recognises would never be translated:
    English is tried first. "speck" and "paprika" are left out on purpose."""
    from app import embeddings, german

    n = Normalizer(embeddings.vocabulary())
    clashes = {w: n._match_english(w) for w in german.WORDS if n._match_english(w)}
    assert clashes == {}
    describing = {"red", "green", "yellow", "fresh", "dried", "ground"}
    # Unmatched on purpose, in English too (D27): a product, not the food in it.
    abstains = {"tomato paste", "powdered sugar"}
    unplaced = {w: e for w, e in {**german.WORDS, **german.PHRASES}.items()
                if e not in describing | abstains and n.match(e) is None}
    assert unplaced == {}
    # ...and the German behaves exactly like the English.
    for w, e in german.WORDS.items():
        if e not in describing:
            assert n.match(w) == n.match(e), w



# --- D53: German compounds, the main noun last ---

@pytest.fixture
def compounds():
    return Normalizer(VOCAB + ["milk", "almond_milk", "oat_milk", "buttermilk", "whole_wheat_flour", "rice"])


@pytest.mark.parametrize("raw, name", [
    ("Vollmilch", "milk"), ("Weizenmehl", "flour"), ("Mandelmilch", "almond_milk"),
    ("Hafermilch", "oat_milk"), ("Buttermilch", "buttermilk"), ("Vollkornmehl", "whole_wheat_flour"),
])
def test_a_compound_is_read_whole(compounds, raw, name):
    assert compounds.match(raw) == name


def test_a_compound_behaves_like_its_english(compounds):
    # Read whole, never as its main noun alone: Kokosmilch goes wherever
    # "coconut milk" goes, which here (no coconut milk in the list) is milk...
    assert compounds.match("Kokosmilch") == compounds.match("coconut milk")
    # ...and coconut milk once the list has it.
    assert Normalizer(VOCAB + ["milk", "coconut_milk"]).match("Kokosmilch") == "coconut_milk"


def test_a_word_that_ends_in_no_known_word_is_not_a_compound():
    from app import german
    assert german.split_compound("vollmilch") == ("voll", "milch")
    assert german.split_compound("milch") is None  # a word on its own
    assert german.split_compound("tomatenmark") is None  # "mark" isn't a food word here
    assert german.compound("buttermilch") == ["buttermilk", "butter milk"]


def test_an_unknown_front_needs_an_exact_ingredient():
    # D67: "Knöblauch" (a typo for Knoblauch) read as "knoeb leek" and became
    # leek; "Rosenkohl" became cabbage. A front part that isn't German is kept
    # only when the whole reading is an ingredient: Basmatireis, Kidneybohnen.
    n = Normalizer(VOCAB + ["leek", "garlic", "cabbage", "basmati_rice", "kidney_bean", "rice", "bean"])
    assert n.match("Knöblauch") is None and "garlic" in n.suggest("Knöblauch")
    assert n.match("Basmatireis") == "basmati_rice"
    assert n.match("Kidneybohnen") == "kidney_bean"
    assert n.match("Spitzkohl") == "cabbage"  # a German word of its own now
    assert Normalizer(VOCAB + ["brussels_sprout", "cabbage"]).match("Rosenkohl") == "brussels_sprout"
