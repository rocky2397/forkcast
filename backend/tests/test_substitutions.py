"""Substitution gates (D13).

D13 claimed "validated on 17 regression pairs (all pass)", but the pairs were
never committed — this file makes that claim reproducible. Needs the Epicure
weights, so it is skipped when they aren't cached (CI runs without them).
"""

import pytest

from conftest import needs_embeddings

from app import substitutions

pytestmark = needs_embeddings

# Pairs D13 and the module docstring record as accepted: (missing, stand-in).
ACCEPTED = [
    ("basil", "oregano"),      # herb <-> herb
    ("tarragon", "basil"),     # the README's example
    ("chicken", "turkey"),
    ("turkey", "chicken"),
    ("duck", "chicken"),
    ("pork", "chicken"),
    ("beef", "lamb"),
    ("lime", "lemon"),
    ("rice", "couscous"),      # within-class pair the chem gate alone missed
    ("scallion", "onion"),
    ("maple_syrup", "honey"),
    ("celery", "carrot"),      # both unclassed: strict dual gate
    ("lemongrass", "ginger"),
]

# Pairs that must be refused — the precision half of "precision over recall".
REJECTED = [
    ("duck", "ginger"),        # passes every rank gate; class map is the veto
    ("chicken", "oregano"),    # meat -> herb
    ("lemon", "salmon"),       # citrus -> seafood
    ("rice", "chicken"),       # grain -> meat
]


@pytest.mark.parametrize("missing,stand_in", ACCEPTED)
def test_documented_substitutions_are_accepted(missing, stand_in):
    assert substitutions.suggest(missing, [stand_in]) == stand_in


@pytest.mark.parametrize("missing,stand_in", REJECTED)
def test_complements_and_cross_class_pairs_are_rejected(missing, stand_in):
    assert substitutions.suggest(missing, [stand_in]) is None


def test_staples_are_never_substituted_for():
    """The salt->ginger bug D13 fixed: a staple missing would match half the pantry."""
    assert substitutions.suggest("salt", ["ginger", "black_pepper", "sugar"]) is None


def test_staples_are_never_offered_as_stand_ins():
    assert substitutions.suggest("basil", ["salt", "butter", "sugar"]) is None


def test_unknown_names_are_harmless():
    assert substitutions.suggest("basil", ["definitely_not_an_ingredient"]) is None
    assert substitutions.suggest("not_an_ingredient", ["oregano"]) is None


def test_the_ingredient_itself_is_not_a_substitution():
    assert substitutions.suggest("basil", ["basil"]) is None


def test_best_candidate_wins_when_several_pass():
    """Same class, so the better cooc rank decides — not list order."""
    assert substitutions.suggest("chicken", ["venison", "turkey"]) == "turkey"
    assert substitutions.suggest("chicken", ["turkey", "venison"]) == "turkey"


def test_same_class_relaxes_the_chem_gate():
    """D13: class membership already vouches for "same kind", so cooc alone gates."""
    score = substitutions._pair_score("rice", "couscous")
    assert score is not None and score <= substitutions.SAME_CLASS_COOC_MAX


def test_class_mismatch_short_circuits_before_any_rank_lookup():
    assert substitutions._pair_score("duck", "ginger") is None
