"""SQLite access for Forkcast.

Two files, because they have opposite lifecycles (D15):

  corpus.db    87k recipes + their ingredients — ~110 MB, read-only, identical
               for every deployment. Baked into the container image.
  forkcast.db  inventory, meal log, profile, products — a few KB that must
               survive redeploys. Lives on the host's persistent disk.

Locally the two can still be one file: when corpus.db is absent, connect()
creates every table in the user DB and behaves exactly as it did before the
split, so an existing dev database keeps working untouched.
"""

import os
import sqlite3
from contextvars import ContextVar
from pathlib import Path

_REPO = Path(__file__).resolve().parents[2]

# FORKCAST_DATA_DIR points at the persistent disk in a deployment (D10 keeps it
# on the external volume locally).
DATA_DIR = Path(os.environ.get("FORKCAST_DATA_DIR") or _REPO / "data")
DB_PATH = DATA_DIR / "forkcast.db"
CORPUS_PATH = Path(os.environ.get("FORKCAST_CORPUS_DB") or _REPO / "data" / "corpus.db")

# The public demo (D32) gives every visitor their own user DB; the request's
# middleware points this at it, and connect() follows. Unset everywhere else.
current_db: ContextVar[Path | None] = ContextVar("current_db", default=None)

CORPUS_SCHEMA = """
CREATE TABLE IF NOT EXISTS recipes (
    id            INTEGER PRIMARY KEY,
    name          TEXT NOT NULL,
    minutes       INTEGER,
    n_steps       INTEGER,
    steps         TEXT,          -- JSON array
    description   TEXT,
    calories      REAL,          -- per serving (per source data)
    fat_g         REAL,
    sat_fat_g     REAL,
    sugar_g       REAL,
    sodium_mg     REAL,
    protein_g     REAL,
    carbs_g       REAL,
    n_ingredients INTEGER,
    matched_frac  REAL           -- share of ingredients normalized to the vocab
);

CREATE TABLE IF NOT EXISTS recipe_ingredients (
    recipe_id INTEGER NOT NULL REFERENCES recipes(id),
    raw       TEXT NOT NULL,
    canonical TEXT               -- NULL when the normalizer had no match
);
CREATE INDEX IF NOT EXISTS idx_ri_recipe    ON recipe_ingredients(recipe_id);
CREATE INDEX IF NOT EXISTS idx_ri_canonical ON recipe_ingredients(canonical);
"""

USER_SCHEMA = """
CREATE TABLE IF NOT EXISTS inventory (
    canonical TEXT PRIMARY KEY,
    added_at  TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS meal_log (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    recipe_id INTEGER,                            -- NULL for ad-hoc meals
    logged_at TEXT NOT NULL DEFAULT (datetime('now')),
    liked     INTEGER,                            -- NULL unknown, 0/1 once rated
    name      TEXT,                               -- ad-hoc meals only; cooks join recipes
    calories  REAL,
    protein_g REAL,
    carbs_g   REAL,
    fat_g     REAL
);

CREATE TABLE IF NOT EXISTS products (
    barcode        TEXT PRIMARY KEY,            -- EAN/UPC digits
    name           TEXT,
    brand          TEXT,
    calories_100g  REAL,
    protein_g_100g REAL,
    carbs_g_100g   REAL,
    fat_g_100g     REAL,
    source         TEXT NOT NULL,               -- 'openfoodfacts' | 'saved' (D48: read off a label)
    fetched_at     TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS profile (
    id         INTEGER PRIMARY KEY CHECK (id = 1),  -- single-user app: one row
    sex        TEXT NOT NULL,
    age        INTEGER NOT NULL,
    height_cm  REAL NOT NULL,
    weight_kg  REAL NOT NULL,
    activity   TEXT NOT NULL,
    goal       TEXT NOT NULL,
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    goal_weight_kg REAL,          -- D39, optional
    pace       TEXT               -- D39: gentle | steady
);

-- D49: what a meal built from ingredients was made of. Its totals are worked
-- out once, when it's logged, and kept on meal_log like any typed meal.
CREATE TABLE IF NOT EXISTS meal_ingredients (
    meal_id   INTEGER NOT NULL,   -- meal_log.id
    canonical TEXT NOT NULL,
    grams     REAL NOT NULL,
    cooked    INTEGER NOT NULL DEFAULT 0   -- 1: weighed cooked (rice, pasta, beans...)
);
CREATE INDEX IF NOT EXISTS idx_mi_meal ON meal_ingredients(meal_id);

-- D50: meals kept at the top of "Log again", by name (lower case), so a
-- favourite survives deleting one day's entry of it.
CREATE TABLE IF NOT EXISTS favourite_meals (
    name_key TEXT PRIMARY KEY,
    added_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- D41: weigh-ins, for the trend and the projection to the goal weight.
CREATE TABLE IF NOT EXISTS weight_log (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    logged_at TEXT NOT NULL DEFAULT (datetime('now')),
    weight_kg REAL NOT NULL
);

-- D42: the user's own word on whether a day's log is complete.
CREATE TABLE IF NOT EXISTS day_check (
    day      TEXT PRIMARY KEY,    -- local date, YYYY-MM-DD
    complete INTEGER NOT NULL     -- 1 complete, 0 incomplete
);
"""

# Kept for the split script and anything wanting the whole shape at once.
SCHEMA = CORPUS_SCHEMA + USER_SCHEMA

# Columns added after the table first shipped; CREATE TABLE IF NOT EXISTS
# won't add them to an existing DB.
_MEAL_LOG_ADDED = {
    "name": "TEXT",
    "calories": "REAL",
    "protein_g": "REAL",
    "carbs_g": "REAL",
    "fat_g": "REAL",
}


# D39: a goal weight and the pace to reach it.
_PROFILE_ADDED = {"goal_weight_kg": "REAL", "pace": "TEXT"}


def _migrate(con: sqlite3.Connection) -> None:
    for table, added in (("meal_log", _MEAL_LOG_ADDED), ("profile", _PROFILE_ADDED)):
        have = {row["name"] for row in con.execute(f"PRAGMA table_info({table})")}
        for col, typ in added.items():
            if col not in have:
                con.execute(f"ALTER TABLE {table} ADD COLUMN {col} {typ}")
    con.commit()


def connect(path: Path | None = None, attach_corpus: bool = True) -> sqlite3.Connection:
    """A connection with both halves visible.

    With no path: this request's demo kitchen if there is one, else DB_PATH.

    The corpus is attached read-only; SQLite resolves an unqualified `recipes`
    against main first and then attached databases, so every existing query
    works unchanged whether or not the split has happened.

    attach_corpus=False forces the legacy single-file shape — that is what the
    import pipeline needs, since it writes the recipe tables.
    """
    path = path or current_db.get() or DB_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(path, uri=True)
    con.row_factory = sqlite3.Row

    split = attach_corpus and CORPUS_PATH.is_file()
    if split:
        con.execute(f"ATTACH DATABASE 'file:{CORPUS_PATH}?mode=ro' AS corpus")
    else:
        con.executescript(CORPUS_SCHEMA)

    con.executescript(USER_SCHEMA)
    _migrate(con)
    return con
