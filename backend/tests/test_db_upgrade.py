"""Opening a database written by an older Forkcast (db._migrate).

Every connect() brings an older user database up to date: missing tables are
created and columns added since a table first shipped are added to it. This
matters in two places: your own database on a long-running install, and
saved demo kitchens (D34), kept for 30 days in whatever format they were
saved in. The old formats below are copied from the git history, not
invented, plus today's, frozen, so the next schema change is checked too.
"""

import sqlite3

import pytest
from fastapi.testclient import TestClient

from app import db, demo, main
from test_demo import H, demo_app, saved_app  # noqa: F401  (fixtures)

# The first user tables (July 2026, before 28864fc): no profile, no products,
# and meals were only ever cooked recipes.
JULY = """
CREATE TABLE inventory (
    canonical TEXT PRIMARY KEY,
    added_at  TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE TABLE meal_log (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    recipe_id INTEGER REFERENCES recipes(id),
    logged_at TEXT NOT NULL DEFAULT (datetime('now')),
    liked     INTEGER
);
"""

# Just before the goal weight (f9dc26b^, 2026-11-15): profile without
# goal_weight_kg and pace; no weigh-ins or day checks yet. Saved demo kitchens
# from before D39 are in this shape.
BEFORE_GOAL_WEIGHT = """
CREATE TABLE inventory (
    canonical TEXT PRIMARY KEY,
    added_at  TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE TABLE meal_log (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    recipe_id INTEGER,
    logged_at TEXT NOT NULL DEFAULT (datetime('now')),
    liked     INTEGER,
    name      TEXT,
    calories  REAL,
    protein_g REAL,
    carbs_g   REAL,
    fat_g     REAL
);
CREATE TABLE products (
    barcode        TEXT PRIMARY KEY,
    name           TEXT,
    brand          TEXT,
    calories_100g  REAL,
    protein_g_100g REAL,
    carbs_g_100g   REAL,
    fat_g_100g     REAL,
    source         TEXT NOT NULL,
    fetched_at     TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE TABLE profile (
    id         INTEGER PRIMARY KEY CHECK (id = 1),
    sex        TEXT NOT NULL,
    age        INTEGER NOT NULL,
    height_cm  REAL NOT NULL,
    weight_kg  REAL NOT NULL,
    activity   TEXT NOT NULL,
    goal       TEXT NOT NULL,
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);
"""

# The user tables as of D45 (2026-11-16), frozen. Leave this as it is when the
# schema changes: it is the database every install has today, and the test
# below checks that the upgrade brings it to whatever the new schema is.
D45 = """
CREATE TABLE inventory (
    canonical TEXT PRIMARY KEY,
    added_at  TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE TABLE meal_log (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    recipe_id INTEGER,
    logged_at TEXT NOT NULL DEFAULT (datetime('now')),
    liked     INTEGER,
    name      TEXT,
    calories  REAL,
    protein_g REAL,
    carbs_g   REAL,
    fat_g     REAL
);
CREATE TABLE products (
    barcode        TEXT PRIMARY KEY,
    name           TEXT,
    brand          TEXT,
    calories_100g  REAL,
    protein_g_100g REAL,
    carbs_g_100g   REAL,
    fat_g_100g     REAL,
    source         TEXT NOT NULL,
    fetched_at     TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE TABLE profile (
    id         INTEGER PRIMARY KEY CHECK (id = 1),
    sex        TEXT NOT NULL,
    age        INTEGER NOT NULL,
    height_cm  REAL NOT NULL,
    weight_kg  REAL NOT NULL,
    activity   TEXT NOT NULL,
    goal       TEXT NOT NULL,
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    goal_weight_kg REAL,
    pace       TEXT
);
CREATE TABLE weight_log (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    logged_at TEXT NOT NULL DEFAULT (datetime('now')),
    weight_kg REAL NOT NULL
);
CREATE TABLE day_check (
    day      TEXT PRIMARY KEY,
    complete INTEGER NOT NULL
);
"""

PROFILE = {"sex": "f", "age": 31, "height_cm": 170, "weight_kg": 72, "activity": "moderate",
           "goal": "maintain", "goal_weight_kg": 66, "pace": "steady"}


def _old_db(path, schema: str, with_recipes: bool = False) -> None:
    con = sqlite3.connect(path)
    if with_recipes:  # in July the corpus lived in the same file
        con.executescript(db.CORPUS_SCHEMA)
        con.execute("INSERT INTO recipes (id, name, calories, protein_g, carbs_g, fat_g) "
                    "VALUES (1, 'chicken and rice', 500, 40, 60, 10)")
    con.executescript(schema)
    con.commit()
    con.close()


def _columns(con, table: str) -> set[str]:
    return {r["name"] for r in con.execute(f"PRAGMA table_info({table})")}


def _tables(con) -> set[str]:
    return {r["name"] for r in con.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}


@pytest.fixture
def july(tmp_path, monkeypatch):
    path = tmp_path / "forkcast.db"
    _old_db(path, JULY, with_recipes=True)
    con = sqlite3.connect(path)
    con.executemany("INSERT INTO inventory (canonical) VALUES (?)", [("chicken",), ("rice",)])
    con.execute("INSERT INTO meal_log (recipe_id, liked) VALUES (1, 1)")
    con.commit()
    con.close()
    monkeypatch.setattr(db, "DB_PATH", path)
    return path


def test_a_july_database_gets_every_table_and_column(july):
    con = db.connect()
    assert {"profile", "products", "weight_log", "day_check"} <= _tables(con)
    assert {"name", "calories", "protein_g", "carbs_g", "fat_g"} <= _columns(con, "meal_log")
    assert {"goal_weight_kg", "pace"} <= _columns(con, "profile")
    # What was there is still there.
    assert {r["canonical"] for r in con.execute("SELECT canonical FROM inventory")} == {"chicken", "rice"}
    meal = con.execute("SELECT recipe_id, liked, name, calories FROM meal_log").fetchone()
    assert tuple(meal) == (1, 1, None, None)
    con.close()


def test_a_july_database_works_in_the_app(july):
    client = TestClient(main.app)
    day = client.get("/api/day?tz=0").json()
    assert day["totals"]["calories"] == 500  # the old cooked meal, from its recipe
    assert client.put("/api/profile?tz=0", json=PROFILE).status_code == 200
    assert client.post("/api/meals", json={"name": "Skyr", "calories": 150, "protein_g": 17, "carbs_g": 6, "fat_g": 0.3}).status_code == 200
    assert client.post("/api/weight?tz=0", json={"weight_kg": 71.8}).status_code == 200
    today = client.get("/api/day?tz=0").json()
    assert client.put(f"/api/days/{today['date']}/check", json={"complete": True}).status_code == 200
    assert today["totals"]["calories"] == 650 and today["plan"]["direction"] == "lose"


@pytest.mark.parametrize("schema", [JULY, BEFORE_GOAL_WEIGHT, D45], ids=["july", "before-goal-weight", "d45"])
def test_an_upgraded_database_has_exactly_the_tables_and_columns_of_a_new_one(tmp_path, schema):
    # Guards the next schema change too: a column added to USER_SCHEMA but not
    # to the upgrade lists in db.py fails here, whichever table it is in.
    fresh = db.connect(tmp_path / "new.db", attach_corpus=False)
    _old_db(tmp_path / "old.db", schema, with_recipes=True)
    old = db.connect(tmp_path / "old.db", attach_corpus=False)
    assert _tables(old) == _tables(fresh)
    for table in sorted(_tables(fresh) - {"sqlite_sequence"}):
        missing = _columns(fresh, table) - _columns(old, table)
        assert not missing, (f"{table}: {sorted(missing)} not added to older databases; "
                             "add it to the upgrade lists in db.py (_migrate)")
        assert _columns(old, table) == _columns(fresh, table), table
    fresh.close()
    old.close()


def test_upgrading_twice_changes_nothing(july):
    db.connect().close()
    con = db.connect()
    assert len(con.execute("SELECT * FROM meal_log").fetchall()) == 1
    assert len(con.execute("SELECT * FROM inventory").fetchall()) == 2
    con.close()


def test_a_profile_from_before_the_goal_weight_keeps_working(tmp_path, monkeypatch):
    path = tmp_path / "forkcast.db"
    _old_db(path, BEFORE_GOAL_WEIGHT)
    con = sqlite3.connect(path)
    con.execute("INSERT INTO profile (id, sex, age, height_cm, weight_kg, activity, goal) "
                "VALUES (1, 'm', 30, 180, 80, 'moderate', 'cut')")
    con.execute("INSERT INTO meal_log (name, calories, protein_g) VALUES ('Oats', 400, 14)")
    con.commit()
    con.close()
    monkeypatch.setattr(db, "DB_PATH", path)
    client = TestClient(main.app)

    got = client.get("/api/profile?tz=0").json()
    assert got["profile"]["goal"] == "cut" and got["profile"]["goal_weight_kg"] is None
    assert got["plan"] is None and got["targets"]["calories"] > 0
    assert client.get("/api/day?tz=0").json()["totals"]["calories"] == 400
    assert client.get("/api/progress?tz=0").json()["progress"]["target"] > 0
    assert client.get("/api/weight?tz=0").json()["entries"] == []
    saved = client.put("/api/profile?tz=0", json=PROFILE | {"sex": "m", "weight_kg": 80, "goal_weight_kg": 74})
    assert saved.status_code == 200 and saved.json()["plan"]["direction"] == "lose"


def test_a_saved_demo_kitchen_from_before_the_goal_weight_comes_back(saved_app):  # noqa: F811
    client, saved = saved_app
    kitchen = "OldKitchenFromBeforeD39"[:22]
    saved.mkdir(parents=True, exist_ok=True)
    _old_db(saved / f"{kitchen}.db", BEFORE_GOAL_WEIGHT)
    con = sqlite3.connect(saved / f"{kitchen}.db")
    con.execute("INSERT INTO inventory (canonical) VALUES ('saffron')")
    con.execute("INSERT INTO profile (id, sex, age, height_cm, weight_kg, activity, goal) "
                "VALUES (1, 'f', 31, 170, 72, 'moderate', 'maintain')")
    con.commit()
    con.close()

    r = client.get("/api/inventory", headers={H: kitchen})
    assert r.headers[H] == kitchen  # restored, not a fresh kitchen
    assert "saffron" in {i["canonical"] for i in r.json()["items"]}
    assert client.put("/api/profile?tz=0", json=PROFILE, headers={H: kitchen}).json()["plan"]["direction"] == "lose"
    assert client.post("/api/weight?tz=0", json={"weight_kg": 71.8}, headers={H: kitchen}).status_code == 200
    assert client.get("/api/progress?tz=0", headers={H: kitchen}).status_code == 200
    assert demo.save_pending() == 1  # and it is saved again, in the new format
    upgraded = sqlite3.connect(saved / f"{kitchen}.db")
    assert {"goal_weight_kg", "pace"} <= {r[1] for r in upgraded.execute("PRAGMA table_info(profile)")}
    upgraded.close()
