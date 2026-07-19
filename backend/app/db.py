"""SQLite access for Forkcast. The DB lives in data/ on the dev volume (D10)."""

import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).resolve().parents[2] / "data" / "forkcast.db"

SCHEMA = """
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

CREATE TABLE IF NOT EXISTS inventory (
    canonical TEXT PRIMARY KEY,
    added_at  TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS meal_log (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    recipe_id INTEGER REFERENCES recipes(id),   -- NULL for ad-hoc meals
    logged_at TEXT NOT NULL DEFAULT (datetime('now')),
    liked     INTEGER,                           -- NULL unknown, 0/1 once rated
    name      TEXT,                              -- ad-hoc meals only; cooks join recipes
    calories  REAL,
    protein_g REAL,
    carbs_g   REAL,
    fat_g     REAL
);

CREATE TABLE IF NOT EXISTS profile (
    id         INTEGER PRIMARY KEY CHECK (id = 1),  -- single-user app: one row
    sex        TEXT NOT NULL,
    age        INTEGER NOT NULL,
    height_cm  REAL NOT NULL,
    weight_kg  REAL NOT NULL,
    activity   TEXT NOT NULL,
    goal       TEXT NOT NULL,
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);
"""

# Columns added after the table first shipped; CREATE TABLE IF NOT EXISTS
# won't add them to an existing DB.
_MEAL_LOG_ADDED = {
    "name": "TEXT",
    "calories": "REAL",
    "protein_g": "REAL",
    "carbs_g": "REAL",
    "fat_g": "REAL",
}


def _migrate(con: sqlite3.Connection) -> None:
    have = {row["name"] for row in con.execute("PRAGMA table_info(meal_log)")}
    for col, typ in _MEAL_LOG_ADDED.items():
        if col not in have:
            con.execute(f"ALTER TABLE meal_log ADD COLUMN {col} {typ}")
    con.commit()


def connect(path: Path = DB_PATH) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(path)
    con.row_factory = sqlite3.Row
    con.executescript(SCHEMA)
    _migrate(con)
    return con
