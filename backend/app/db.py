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
"""


def connect(path: Path = DB_PATH) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(path)
    con.row_factory = sqlite3.Row
    con.executescript(SCHEMA)
    return con
