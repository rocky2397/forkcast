"""Shopping suggestions (D21): what to buy to unlock the most recipes.

Greedy set cover over the recipes you are 1-N ingredients away from. Each pick
is the ingredient that completes the most still-locked recipes *given the
picks before it*, so the list reads as one basket rather than three
independent suggestions that all unlock the same pasta dishes.

Taste only tilts the ranking; the count shown to the user is the honest
integer of recipes the purchase completes.
"""

import sqlite3

import numpy as np

from . import recipes, taste

# Safety ceiling, not a working limit: a typical inventory leaves ~15k recipes
# within 3 ingredients, and scanning all of them costs ~0.3s. An earlier 4k cap
# silently dropped two thirds of the candidates and picked a worse basket, so
# suggest() reports when this bites rather than quietly covering less.
POOL_LIMIT = 20000
EXAMPLES_PER_ITEM = 3

# D59: for someone losing weight, desserts don't count towards what to buy:
# yeast, vanilla and baking powder topped the list for a calorie-counting
# tester, with cookies and icing as the examples. A dessert here is a recipe
# with an added-sweet ingredient that gets a quarter or more of its calories
# from sugar (about 27k of 88k recipes; a few glazed savoury dishes too).
SWEET = ("sugar", "brown_sugar", "powdered_sugar", "vanilla", "chocolate", "milk_chocolate",
         "white_chocolate", "cocoa_powder", "marshmallow", "corn_syrup", "whipped_topping",
         "ice_cream", "condensed_milk", "frosting", "sprinkles", "candy", "caramel", "butterscotch")
SWEET_SHARE = 0.25
_sweet_cache: dict[tuple, frozenset[int]] = {}


def sweet_ids(con: sqlite3.Connection) -> frozenset[int]:
    n, top = con.execute("SELECT COUNT(*), COALESCE(MAX(id), 0) FROM recipes").fetchone()
    key = (n, top)
    if key not in _sweet_cache:
        _sweet_cache.clear()
        _sweet_cache[key] = frozenset(r[0] for r in con.execute(
            f"""SELECT r.id FROM recipes r
                WHERE r.calories > 0 AND r.sugar_g * 4 >= ? * r.calories
                  AND r.id IN (SELECT recipe_id FROM recipe_ingredients
                               WHERE canonical IN ({','.join('?' * len(SWEET))}))""",
            (SWEET_SHARE, *SWEET),
        ))
    return _sweet_cache[key]


# A recipe at the bottom of the taste range still counts half — the profile is
# a hint about what to buy, not a veto on recipes you simply haven't cooked yet.
TASTE_FLOOR = 0.5


def _weights(con: sqlite3.Connection, pool: list[dict], profile) -> dict[int, float]:
    """Per-recipe ranking weight in [TASTE_FLOOR, 1], or all 1.0 without taste data.

    Min-max normalized *within the pool*: absolute taste scores aren't
    comparable across the corpus (hub effects, paper §8 — the same reason D13
    gates on ranks), so only their order within this pool is used.
    """
    if profile is None or not pool:
        return {r["id"]: 1.0 for r in pool}
    scores = taste.score_recipes(con, [r["id"] for r in pool], profile)
    vals = np.fromiter((scores.get(r["id"], 0.0) for r in pool), dtype="float64", count=len(pool))
    lo, hi = float(vals.min()), float(vals.max())
    if hi - lo < 1e-9:
        return {r["id"]: 1.0 for r in pool}
    return {
        r["id"]: TASTE_FLOOR + (1.0 - TASTE_FLOOR) * (scores.get(r["id"], 0.0) - lo) / (hi - lo)
        for r in pool
    }


def suggest(
    con: sqlite3.Connection,
    profile=None,
    basket_size: int = 3,
    max_missing: int = 3,
    leave_out_sweet: bool = False,
) -> tuple[list[dict], bool]:
    """(up to basket_size ingredients to buy, whether the pool was truncated)."""
    pool = recipes.missing_sets(con, max_missing=max_missing, limit=POOL_LIMIT)
    truncated = len(pool) >= POOL_LIMIT
    if leave_out_sweet:
        sweet = sweet_ids(con)
        pool = [r for r in pool if r["id"] not in sweet]
    if not pool:
        return [], truncated
    weight = _weights(con, pool, profile)

    basket: set[str] = set()
    locked = list(pool)
    out: list[dict] = []

    for _ in range(basket_size):
        # What each candidate would complete, given everything already picked.
        gain: dict[str, float] = {}
        count: dict[str, int] = {}
        completed: dict[str, list[dict]] = {}
        for r in locked:
            rest = r["missing"] - basket
            if len(rest) != 1:
                continue
            c = next(iter(rest))
            gain[c] = gain.get(c, 0.0) + weight[r["id"]]
            count[c] = count.get(c, 0) + 1
            completed.setdefault(c, []).append(r)

        if not gain:
            break
        pick = max(gain, key=lambda c: (gain[c], count[c]))
        basket.add(pick)
        unlocked = completed[pick]
        unlocked_ids = {r["id"] for r in unlocked}
        locked = [r for r in locked if r["id"] not in unlocked_ids]

        out.append({
            "canonical": pick,
            "unlocks": count[pick],
            # Most on-taste first, so the examples justify the pick.
            "examples": [
                r["name"]
                for r in sorted(unlocked, key=lambda r: -weight[r["id"]])[:EXAMPLES_PER_ITEM]
            ],
        })

    return out, truncated
