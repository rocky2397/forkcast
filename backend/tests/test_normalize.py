"""Ingredient matching.

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
]


@pytest.fixture
def n():
    return Normalizer(VOCAB)


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
