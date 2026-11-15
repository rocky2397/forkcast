"""Taste learning (D6, D31).

Ranking (D31): a recipe scores by how close it is to the three nearest dishes
you've cooked and not disliked. Stage 3 of the eval replayed 2,710 food.com
users and found the old single average ("centroid") of everything you cooked
barely beat a coin flip: an average of curries and cakes is close to neither.
Comparing against your nearest dishes keeps distinct tastes apart. Recipes are
compared in a "dish space" built for that:

- rare ingredients count more than common ones (saffron says more about a
  dish than onion), by inverse document frequency over the corpus;
- the average dish is subtracted, because raw dish vectors all point roughly
  the same way (mean pairwise cosine ~0.49, ~0.08 after centring) — the same
  hubness as the SLERP experiments.

The nearest dish also explains the ranking: "Like your Cherry Tomato Pasta".

The explanation of the profile as a whole still uses taste_vector(), a
time-decayed weighted mean over the ingredient embeddings of logged cooks
(Epicure-Cooc: recipe-context is the right notion of "my kind of cooking"),
and nearest_ingredients() names what it leans towards. Universal staples are
excluded everywhere: they sit near the embedding hub and would wash every
profile toward salt/onion/garlic.

No training, fully explainable.
"""

import math
import sqlite3
from dataclasses import dataclass

import numpy as np

from . import embeddings
from .recipes import STAPLES

MODEL = "cooc"
HALF_LIFE_DAYS = 30.0
LIKED_BOOST = 1.5     # explicit like counts more
DISLIKED_WEIGHT = -0.5  # explicit dislike pushes the centroid away

K_NEAREST = 3       # dishes a recipe is compared against (D31; dev: 1 to 10 within a point)
LIKE_YOUR = 0.6     # nearest-dish similarity above which the feed names that dish
MEAN_SAMPLE = 4000  # recipes sampled to estimate the average dish


@dataclass
class Profile:
    """What a recipe is compared against: your cooked, not-disliked dishes."""

    ids: list[int]
    dishes: np.ndarray  # (len(ids), dim), unit rows in dish space


_space_cache: dict[tuple, tuple[dict[str, float], np.ndarray]] = {}


def _space(con: sqlite3.Connection) -> tuple[dict[str, float], np.ndarray]:
    """(ingredient -> idf weight, average dish vector) for the corpus behind con.

    Built once per corpus and cached; the key changes if recipes are added.
    """
    # Keyed on the recipe data, not the user DB: the demo opens a different
    # user file per visitor, and that must not rebuild the space each time.
    dbs = [(r[1], r[2]) for r in con.execute("PRAGMA database_list")]
    files = tuple(f for name, f in dbs if name == "corpus") or tuple(f for _, f in dbs)
    n, top = con.execute("SELECT COUNT(*), COALESCE(MAX(id), 0) FROM recipes").fetchone()
    key = (files, n, top)
    if key not in _space_cache:
        idf = {
            c: math.log(max(n, 1) / df)
            for c, df in con.execute(
                "SELECT canonical, COUNT(DISTINCT recipe_id) FROM recipe_ingredients"
                " WHERE canonical IS NOT NULL GROUP BY canonical"
            )
        }
        step = max(1, n // MEAN_SAMPLE)
        sample: dict[int, list[str]] = {}
        for rid, c in con.execute(
            "SELECT recipe_id, canonical FROM recipe_ingredients"
            " WHERE canonical IS NOT NULL AND recipe_id % ? = 0",
            (step,),
        ):
            sample.setdefault(rid, []).append(c)
        vecs = [v for cs in sample.values() if (v := _weighted(cs, idf)) is not None]
        mean = np.mean(vecs, axis=0) if vecs else None
        _space_cache.clear()  # one corpus per process; don't grow in tests
        _space_cache[key] = (idf, mean)
    return _space_cache[key]


def _weighted(canonicals: list[str], idf: dict[str, float]) -> np.ndarray | None:
    """Unit idf-weighted mean of a dish's non-staple ingredient vectors."""
    vecs, weights = [], []
    for c in set(canonicals):
        if c in STAPLES or (v := embeddings.ingredient_vector(c, MODEL)) is None:
            continue
        vecs.append(v)
        weights.append(idf.get(c, 0.0))
    if not vecs or sum(weights) <= 0:
        return None
    v = np.average(np.asarray(vecs, dtype="float64"), axis=0, weights=weights)
    n = np.linalg.norm(v)
    return v / n if n > 0 else None


def dish_vectors(con: sqlite3.Connection, recipe_ids: list[int]) -> dict[int, np.ndarray]:
    """Recipe id -> unit vector in dish space (idf-weighted, centred)."""
    if not recipe_ids:
        return {}
    idf, mean = _space(con)
    by_recipe: dict[int, list[str]] = {}
    ids = list(dict.fromkeys(recipe_ids))
    placeholders = ",".join("?" * len(ids))
    for r in con.execute(
        f"SELECT recipe_id, canonical FROM recipe_ingredients"
        f" WHERE recipe_id IN ({placeholders}) AND canonical IS NOT NULL",
        ids,
    ):
        by_recipe.setdefault(r[0], []).append(r[1])
    out = {}
    for rid, cs in by_recipe.items():
        v = _weighted(cs, idf)
        if v is None:
            continue
        if mean is not None:
            v = v - mean
        n = np.linalg.norm(v)
        if n > 0:
            out[rid] = v / n
    return out


def taste_profile(con: sqlite3.Connection) -> Profile | None:
    """Your cooked dishes that weren't disliked, or None before the first one."""
    ids = [
        r[0] for r in con.execute(
            "SELECT DISTINCT recipe_id FROM meal_log"
            " WHERE recipe_id IS NOT NULL AND (liked IS NULL OR liked != 0)"
        )
    ]
    vecs = dish_vectors(con, ids)
    kept = [rid for rid in ids if rid in vecs]
    if not kept:
        return None
    return Profile(ids=kept, dishes=np.stack([vecs[rid] for rid in kept]))


def match_recipes(
    con: sqlite3.Connection, recipe_ids: list[int], profile: Profile
) -> dict[int, tuple[float, int | None]]:
    """Recipe id -> (score, nearest cooked dish worth naming or None).

    The score is the mean similarity to the K_NEAREST closest cooked dishes;
    recipes without a dish vector score 0. The named dish is the closest one
    other than the recipe itself, and only when it clears LIKE_YOUR.
    """
    vecs = dish_vectors(con, recipe_ids)
    k = min(K_NEAREST, len(profile.ids))
    out: dict[int, tuple[float, int | None]] = {}
    for rid in recipe_ids:
        v = vecs.get(rid)
        if v is None:
            out[rid] = (0.0, None)
            continue
        sims = profile.dishes @ v
        score = float(np.sort(sims)[::-1][:k].mean())
        named = None
        for i in np.argsort(sims)[::-1]:
            if profile.ids[i] == rid:
                continue
            if sims[i] >= LIKE_YOUR:
                named = profile.ids[i]
            break
        out[rid] = (score, named)
    return out


def recipe_vector(canonicals: list[str]) -> np.ndarray | None:
    """Unit mean of a recipe's non-staple ingredient vectors."""
    vecs = [
        v for c in canonicals
        if c not in STAPLES and (v := embeddings.ingredient_vector(c, MODEL)) is not None
    ]
    if not vecs:
        return None
    v = np.mean(vecs, axis=0)
    n = np.linalg.norm(v)
    return v / n if n > 0 else None


def taste_vector(con: sqlite3.Connection) -> tuple[np.ndarray | None, int]:
    """(unit taste vector | None, number of meals it is based on)."""
    meals = con.execute(
        """SELECT recipe_id, liked,
                  (julianday('now') - julianday(logged_at)) AS age_days
           FROM meal_log WHERE recipe_id IS NOT NULL"""
    ).fetchall()
    if not meals:
        return None, 0

    acc = None
    used = 0
    for meal in meals:
        canonicals = [
            r["canonical"] for r in con.execute(
                "SELECT DISTINCT canonical FROM recipe_ingredients"
                " WHERE recipe_id = ? AND canonical IS NOT NULL",
                (meal["recipe_id"],),
            )
        ]
        rv = recipe_vector(canonicals)
        if rv is None:
            continue
        w = 0.5 ** (max(meal["age_days"], 0.0) / HALF_LIFE_DAYS)
        if meal["liked"] == 1:
            w *= LIKED_BOOST
        elif meal["liked"] == 0:
            w *= DISLIKED_WEIGHT
        acc = w * rv if acc is None else acc + w * rv
        used += 1

    if acc is None:
        return None, 0
    n = np.linalg.norm(acc)
    return (acc / n if n > 0 else None), used


def score_recipes(
    con: sqlite3.Connection, recipe_ids: list[int], profile: Profile
) -> dict[int, float]:
    """Nearest-dish score per recipe (see match_recipes); missing vectors -> 0."""
    return {rid: s for rid, (s, _) in match_recipes(con, recipe_ids, profile).items()}


def nearest_ingredients(taste: np.ndarray, k: int = 8):
    """Explainability: which (non-staple) ingredients define this profile."""
    hits = embeddings.nearest_to_vector(taste, MODEL, k=k + len(STAPLES))
    return [
        {"ingredient": name, "similarity": round(sim, 3)}
        for name, sim in hits if name not in STAPLES
    ][:k]
