"""Test fixtures (D22).

Everything here must work offline and without the 130 MB corpus: the env is
pointed at a temp database *before* `app.db` is imported, because `connect()`
binds its default path at definition time. Tests that genuinely need the
Epicure weights are marked `embeddings` and skipped when they aren't cached.
"""

import os
import tempfile
from pathlib import Path

_TMP = Path(tempfile.mkdtemp(prefix="forkcast-tests-"))

# A corpus path that does not exist puts connect() in its legacy single-file
# shape, so the recipe tables are created in (and writable on) the temp DB.
os.environ["FORKCAST_DATA_DIR"] = str(_TMP)
os.environ["FORKCAST_CORPUS_DB"] = str(_TMP / "absent-corpus.db")
# The gate is opt-in per test; a password in the developer's shell must not
# silently turn it on for every request.
os.environ.pop("FORKCAST_PASSWORD", None)

# Convenience: reuse the dev volume's model cache so the `embeddings` tests
# actually run locally (dev.sh exports this; a bare `pytest` does not).
_DEV_HF = Path("/Volumes/RecipesDev/caches/huggingface")
if "HF_HOME" not in os.environ and _DEV_HF.is_dir():
    os.environ["HF_HOME"] = str(_DEV_HF)

import pytest  # noqa: E402  (must follow the env setup above)

from app.db import connect  # noqa: E402

# (name, kcal, protein, carbs, fat, [(canonical, in_inventory_or_not)])
_INVENTORY = ["chicken", "rice", "onion", "carrot", "egg"]

# Shaped so the greedy basket has a known answer: yeast completes two recipes
# on its own, milk completes one on its own plus one that also needed yeast.
_RECIPES = [
    # id, name, kcal, protein, carbs, fat, ingredients
    (1, "chicken and rice", 500.0, 40.0, 60.0, 10.0, ["chicken", "rice", "onion"]),
    (2, "salted rice", 300.0, 8.0, 60.0, 2.0, ["rice", "salt"]),
    (3, "burger buns", 350.0, 9.0, 55.0, 8.0, ["yeast", "egg"]),
    (4, "flat bread", 320.0, 8.0, 58.0, 6.0, ["yeast", "carrot"]),
    (5, "milk bread", 400.0, 11.0, 62.0, 9.0, ["yeast", "milk"]),
    (6, "creamed carrots", 220.0, 5.0, 20.0, 12.0, ["milk", "carrot"]),
    (7, "duck feast", 900.0, 60.0, 10.0, 60.0, ["duck", "potato", "thyme"]),
]


@pytest.fixture
def db():
    """A clean connection to the temp database, seeded with a tiny corpus."""
    con = connect()
    con.executescript(
        "DELETE FROM recipe_ingredients; DELETE FROM recipes;"
        "DELETE FROM inventory; DELETE FROM meal_log; DELETE FROM profile;"
    )
    for rid, name, kcal, p, c, f, ings in _RECIPES:
        con.execute(
            """INSERT INTO recipes (id, name, minutes, steps, calories, protein_g,
                                    carbs_g, fat_g, n_ingredients, matched_frac)
               VALUES (?, ?, 20, '[]', ?, ?, ?, ?, ?, 1.0)""",
            (rid, name, kcal, p, c, f, len(ings)),
        )
        con.executemany(
            "INSERT INTO recipe_ingredients (recipe_id, raw, canonical) VALUES (?, ?, ?)",
            [(rid, ing.replace("_", " "), ing) for ing in ings],
        )
    con.executemany("INSERT INTO inventory (canonical) VALUES (?)", [(i,) for i in _INVENTORY])
    con.commit()
    yield con
    con.close()


@pytest.fixture
def profile(db):
    """A profile row, so targets and macro steering have something to work with."""
    db.execute(
        """INSERT INTO profile (id, sex, age, height_cm, weight_kg, activity, goal)
           VALUES (1, 'm', 30, 175, 80, 'light', 'cut')"""
    )
    db.commit()
    return db


def embeddings_cached() -> bool:
    """True when the Epicure weights are on disk, so no test downloads them."""
    try:
        from huggingface_hub import snapshot_download

        for repo in ("Kaikaku/epicure-cooc", "Kaikaku/epicure-chem"):
            snapshot_download(repo, local_files_only=True)
        return True
    except Exception:
        return False


needs_embeddings = pytest.mark.skipif(
    not embeddings_cached(),
    reason="Epicure weights not cached; run after a dev session or set HF_HOME",
)
