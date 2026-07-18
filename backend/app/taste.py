"""Taste learning (D6): the user's taste is an embedding centroid.

taste_vector() builds a time-decayed weighted mean over the ingredient
embeddings of logged cooks (Epicure-Cooc: recipe-context is the right notion
of "my kind of cooking"). Universal staples are excluded — they sit near the
embedding hub and would wash every profile toward salt/onion/garlic (the same
hubness we measured in the SLERP experiments).

No training, fully explainable: nearest_ingredients() answers "why these
suggestions".
"""

import sqlite3

import numpy as np

from . import embeddings
from .recipes import STAPLES

MODEL = "cooc"
HALF_LIFE_DAYS = 30.0
LIKED_BOOST = 1.5     # explicit like counts more
DISLIKED_WEIGHT = -0.5  # explicit dislike pushes the centroid away


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
    con: sqlite3.Connection, recipe_ids: list[int], taste: np.ndarray
) -> dict[int, float]:
    """Cosine(recipe vector, taste vector) per recipe; missing vectors -> 0."""
    if not recipe_ids:
        return {}
    placeholders = ",".join("?" * len(recipe_ids))
    by_recipe: dict[int, list[str]] = {}
    for r in con.execute(
        f"SELECT recipe_id, canonical FROM recipe_ingredients"
        f" WHERE recipe_id IN ({placeholders}) AND canonical IS NOT NULL",
        recipe_ids,
    ):
        by_recipe.setdefault(r["recipe_id"], []).append(r["canonical"])
    scores = {}
    for rid in recipe_ids:
        rv = recipe_vector(by_recipe.get(rid, []))
        scores[rid] = float(rv @ taste) if rv is not None else 0.0
    return scores


def nearest_ingredients(taste: np.ndarray, k: int = 8):
    """Explainability: which (non-staple) ingredients define this profile."""
    hits = embeddings.nearest_to_vector(taste, MODEL, k=k + len(STAPLES))
    return [
        {"ingredient": name, "similarity": round(sim, 3)}
        for name, sim in hits if name not in STAPLES
    ][:k]
