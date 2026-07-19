"""Substitution suggestions (D13): can something in the inventory stand in
for a recipe's missing ingredient?

Rank-based dual gate: the candidate must sit within the missing ingredient's
top COOC_MAX_RANK cooc neighbors (used in similar recipes) AND top
CHEM_MAX_RANK chem neighbors (shares flavor chemistry). Raw cosines are not
comparable across ingredients (hub effects, see APP_DECISIONS §8), ranks are.
Empirically this accepts pairs like basil->oregano, chicken->turkey,
lime->lemon and rejects all probed nonsense pairs (precision over recall).
"""

from functools import lru_cache

import numpy as np

from . import embeddings
from .recipes import STAPLES

COOC_MAX_RANK = 200
CHEM_MAX_RANK = 400


@lru_cache(maxsize=1)
def _index() -> dict[str, int]:
    return {name: i for i, name in enumerate(embeddings.vocabulary())}


@lru_cache(maxsize=512)
def _rank_arrays(name: str) -> tuple[np.ndarray, np.ndarray] | None:
    """Per-vocab-entry neighbor rank of `name` on cooc and chem (0 = itself)."""
    idx = _index().get(name)
    if idx is None:
        return None
    out = []
    for model in ("cooc", "chem"):
        M = embeddings.unit_matrix(model)
        sims = M @ M[idx]
        ranks = np.empty(len(sims), dtype=np.int32)
        ranks[np.argsort(-sims)] = np.arange(len(sims))
        out.append(ranks)
    return out[0], out[1]


def _pair_score(a: str, b: str) -> int | None:
    """Gate a->b: b must rank within both cutoffs among a's neighbors."""
    arrays = _rank_arrays(a)
    if arrays is None:
        return None
    cooc_rank, chem_rank = arrays
    i = _index()[b]
    rc, rh = int(cooc_rank[i]), int(chem_rank[i])
    if rc > COOC_MAX_RANK or rh > CHEM_MAX_RANK:
        return None
    return rc + rh


def suggest(missing: str, candidates: list[str]) -> str | None:
    """Best in-inventory stand-in for `missing`, or None if nothing passes.

    Forward direction only: symmetrizing the gate lets hub candidates
    through (chicken ranks 284 among basil's chem neighbors in reverse),
    so an occasional asymmetric recall miss is the accepted cost. Staples
    are excluded as sources (hub ingredients; and they are assumed present
    anyway), as should be anything already in the recipe (callers pass
    candidates accordingly).
    """
    idx = _index()
    if missing not in idx:
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
