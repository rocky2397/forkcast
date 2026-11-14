"""Substitution suggestions (D13, D28): can something in the inventory stand
in for a recipe's missing ingredient?

A stand-in must share a food class with the missing ingredient, and then rank
within its top SAME_CLASS_COOC_MAX cooc neighbours (used in similar recipes).
Outside the class map the engine stays silent.

D13 also accepted unclassed pairs that passed a dual rank gate (cooc and chem).
The stage 2 eval (eval/RESULTS-stage2.md) showed that path was wrong four
times out of five: embedding ranks can't tell a substitute from a complement
(coconut -> banana, coffee -> chocolate, chicken broth -> bell pepper). Classes
are the signal that can, so D28 widened the map from 8 to 47 classes and
dropped the unclassed path. A missing hint costs nothing; a bad one costs trust.
"""

from functools import lru_cache

import numpy as np

from . import embeddings
from .recipes import STAPLES

SAME_CLASS_COOC_MAX = 400  # class vouches for "same kind"; cooc keeps it plausible

from .food_classes import CLASSES, NAME_TO_CLASS as _NAME_TO_CLASS  # noqa: E402,F401


@lru_cache(maxsize=1)
def _index() -> dict[str, int]:
    return {name: i for i, name in enumerate(embeddings.vocabulary())}


@lru_cache(maxsize=512)
def _cooc_ranks(name: str) -> np.ndarray | None:
    """Per-vocab-entry cooc neighbour rank of `name` (0 = itself)."""
    idx = _index().get(name)
    if idx is None:
        return None
    M = embeddings.unit_matrix("cooc")
    sims = M @ M[idx]
    ranks = np.empty(len(sims), dtype=np.int32)
    ranks[np.argsort(-sims)] = np.arange(len(sims))
    return ranks


def _pair_score(a: str, b: str) -> int | None:
    """Gate a->b, returning a sort score (lower = better) or None.

    Both in the same class: cooc rank within SAME_CLASS_COOC_MAX.
    Anything else is rejected: a class mismatch is the complement risk
    (duck->ginger), and an unclassed pair has nothing to vouch for it.
    """
    cls_a = _NAME_TO_CLASS.get(a)
    if cls_a is None or cls_a != _NAME_TO_CLASS.get(b):
        return None
    ranks = _cooc_ranks(a)
    if ranks is None:
        return None
    rc = int(ranks[_index()[b]])
    return rc if rc <= SAME_CLASS_COOC_MAX else None


def suggest(missing: str, candidates: list[str]) -> str | None:
    """Best in-inventory stand-in for `missing`, or None if nothing passes.

    Forward direction only: the cooc rank is read from the missing
    ingredient's side, so an occasional asymmetric miss is accepted. Staples
    are excluded as sources (hub ingredients; and they are assumed present
    anyway), as should be anything already in the recipe (callers pass
    candidates accordingly).
    """
    idx = _index()
    # Staples are hubs on both sides: as a missing ingredient they'd match
    # half the pantry (salt->ginger), and they're assumed present anyway.
    if missing not in idx or missing in STAPLES:
        return None
    best, best_score = None, None
    for cand in candidates:
        if cand == missing or cand in STAPLES or cand not in idx:
            continue
        score = _pair_score(missing, cand)
        if score is None:
            continue
        if best_score is None or score < best_score:
            best, best_score = cand, score
    return best
