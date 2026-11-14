"""Recipe queries: what can I cook with my inventory?

Staples (salt, water, oil, ...) are assumed present by default — nearly every
recipe needs them and requiring them in inventory would zero out results.
"""

import sqlite3

STAPLES = {
    "salt", "water", "black_pepper", "sugar", "oil", "vegetable_oil",
    "olive_oil", "butter", "flour", "all_purpose_flour",
}


def cookable(
    con: sqlite3.Connection,
    max_missing: int = 0,
    assume_staples: bool = True,
    min_matched_frac: float = 1.0,
    limit: int = 20,
    min_missing: int = 0,
):
    """Recipes ordered by fewest missing ingredients, then fewest total.

    min_missing > 0 leaves out recipes closer than that: the feed's "one away"
    tab asks for exactly one missing, not "cookable now" again on top.

    Only recipes whose ingredient list fully normalized (matched_frac >=
    min_matched_frac) are considered: an unmatched ingredient can never be
    in inventory, so partially-matched recipes would look permanently
    uncookable rather than almost-cookable.
    """
    staples = tuple(STAPLES) if assume_staples else ()
    placeholders = ",".join("?" * len(staples)) or "''"
    rows = con.execute(
        f"""
        WITH need AS (
            SELECT ri.recipe_id,
                   COUNT(*) AS needed,
                   SUM(CASE WHEN inv.canonical IS NULL THEN 1 ELSE 0 END) AS missing,
                   GROUP_CONCAT(CASE WHEN inv.canonical IS NULL THEN ri.canonical END) AS missing_names
            FROM recipe_ingredients ri
            LEFT JOIN inventory inv ON inv.canonical = ri.canonical
            WHERE ri.canonical IS NOT NULL
              AND ri.canonical NOT IN ({placeholders})
            GROUP BY ri.recipe_id
        )
        SELECT r.id, r.name, r.minutes, r.calories, r.protein_g, r.carbs_g, r.fat_g,
               need.needed, need.missing, need.missing_names
        FROM need
        JOIN recipes r ON r.id = need.recipe_id
        WHERE need.missing <= ?
          AND need.missing >= ?
          AND r.matched_frac >= ?
        ORDER BY need.missing ASC, need.needed DESC
        LIMIT ?
        """,
        (*staples, max_missing, min_missing, min_matched_frac, limit),
    ).fetchall()
    return _rows_to_dicts(rows)


def missing_sets(
    con: sqlite3.Connection,
    max_missing: int = 3,
    assume_staples: bool = True,
    min_matched_frac: float = 1.0,
    limit: int = 4000,
):
    """(recipe id, name, its missing ingredient set) for recipes 1-N away (D21).

    The raw material for shopping suggestions: which purchases would complete
    which recipes. Already-cookable recipes are excluded — they need nothing.
    """
    staples = tuple(STAPLES) if assume_staples else ()
    placeholders = ",".join("?" * len(staples)) or "''"
    rows = con.execute(
        f"""
        WITH need AS (
            SELECT ri.recipe_id,
                   SUM(CASE WHEN inv.canonical IS NULL THEN 1 ELSE 0 END) AS missing,
                   GROUP_CONCAT(CASE WHEN inv.canonical IS NULL THEN ri.canonical END) AS missing_names
            FROM recipe_ingredients ri
            LEFT JOIN inventory inv ON inv.canonical = ri.canonical
            WHERE ri.canonical IS NOT NULL
              AND ri.canonical NOT IN ({placeholders})
            GROUP BY ri.recipe_id
        )
        SELECT r.id, r.name, need.missing, need.missing_names
        FROM need
        JOIN recipes r ON r.id = need.recipe_id
        WHERE need.missing BETWEEN 1 AND ?
          AND r.matched_frac >= ?
        ORDER BY need.missing ASC
        LIMIT ?
        """,
        (*staples, max_missing, min_matched_frac, limit),
    ).fetchall()
    return [
        {
            "id": row["id"],
            "name": row["name"],
            "missing": frozenset(row["missing_names"].split(",")),
        }
        for row in rows
        if row["missing_names"]
    ]


def _rows_to_dicts(rows):
    return [
        {
            "id": row["id"],
            "name": row["name"],
            "minutes": row["minutes"],
            "calories": round(row["calories"], 1) if row["calories"] is not None else None,
            "protein_g": round(row["protein_g"], 1) if row["protein_g"] is not None else None,
            "carbs_g": round(row["carbs_g"], 1) if row["carbs_g"] is not None else None,
            "fat_g": round(row["fat_g"], 1) if row["fat_g"] is not None else None,
            "ingredients_needed": row["needed"],
            "ingredients_missing": row["missing"],
            "missing": sorted(set(row["missing_names"].split(","))) if row["missing_names"] else [],
        }
        for row in rows
    ]
