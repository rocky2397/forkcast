"""Nearest-dish taste ranking (D31).

Runs on the tiny conftest corpus with the real Epicure weights: bread-like
recipes, a carrot dish, a duck dish, chicken and rice.
"""

from fastapi.testclient import TestClient

from app import main, taste
from conftest import needs_embeddings

pytestmark = needs_embeddings


def _cook(db, recipe_id, liked):
    db.execute(
        "INSERT INTO meal_log (recipe_id, name, calories, liked) VALUES (?, 'x', 0, ?)",
        (recipe_id, liked),
    )
    db.commit()


def test_no_cooking_means_no_profile(db):
    assert taste.taste_profile(db) is None


def test_disliked_dishes_are_not_your_taste(db):
    _cook(db, 7, 0)  # duck feast, disliked
    assert taste.taste_profile(db) is None


def test_the_profile_is_the_dishes_you_cooked(db):
    _cook(db, 5, 1)     # milk bread, liked
    _cook(db, 6, None)  # creamed carrots, no rating
    _cook(db, 7, 0)     # duck feast, disliked
    profile = taste.taste_profile(db)
    assert sorted(profile.ids) == [5, 6]
    assert profile.dishes.shape[0] == 2


def test_recipes_near_a_cooked_dish_rank_higher(db):
    _cook(db, 5, 1)  # milk bread: yeast, milk
    scores = taste.score_recipes(db, [3, 7], taste.taste_profile(db))
    assert scores[3] > scores[7]  # burger buns (yeast, egg) beat duck feast


def test_named_dish_is_never_the_recipe_itself(db, monkeypatch):
    monkeypatch.setattr(taste, "LIKE_YOUR", -1.0)  # name any nearest dish
    _cook(db, 5, 1)
    matches = taste.match_recipes(db, [5, 3], taste.taste_profile(db))
    assert matches[5][1] is None  # its only cooked neighbour is itself
    assert matches[3][1] == 5


def test_named_dish_needs_to_be_close(db, monkeypatch):
    monkeypatch.setattr(taste, "LIKE_YOUR", 1.01)  # nothing is that close
    _cook(db, 5, 1)
    matches = taste.match_recipes(db, [3], taste.taste_profile(db))
    assert matches[3][1] is None


def test_feed_names_the_dish_a_recipe_is_like(db, monkeypatch):
    monkeypatch.setattr(taste, "LIKE_YOUR", -1.0)
    _cook(db, 2, 1)  # salted rice
    body = TestClient(main.app).get("/api/recipes/cookable?max_missing=0").json()
    assert body["personalized"] is True
    chicken = next(r for r in body["recipes"] if r["id"] == 1)
    assert chicken["like_your"] == {"id": 2, "name": "salted rice"}
    assert "taste_sim" in chicken


# D49: meals built from ingredients count as dishes too.

def _build(db, name, canonicals, liked=None, ago_days=0):
    cur = db.execute(
        "INSERT INTO meal_log (name, calories, liked, logged_at)"
        " VALUES (?, 0, ?, datetime('now', ?))",
        (name, liked, f"-{ago_days} days"),
    )
    db.executemany(
        "INSERT INTO meal_ingredients (meal_id, canonical, grams) VALUES (?, ?, 100)",
        [(cur.lastrowid, c) for c in canonicals],
    )
    db.commit()
    return cur.lastrowid


def test_a_built_meal_joins_the_profile(db):
    mid = _build(db, "Carrot milk", ["milk", "carrot"])
    profile = taste.taste_profile(db)
    assert profile.ids == [-mid]
    assert profile.names == {-mid: "Carrot milk"}


def test_single_foods_staples_and_dislikes_dont(db):
    _build(db, "Banana", ["banana"])
    _build(db, "Salty oil", ["salt", "olive_oil", "carrot"])  # one real ingredient
    _build(db, "Duck and thyme", ["duck", "thyme"], liked=0)
    assert taste.taste_profile(db) is None


def test_a_meal_logged_every_day_counts_once(db):
    for ago in range(5):
        _build(db, "Smoothie", ["milk", "banana"], ago_days=ago)
    assert len(taste.taste_profile(db).ids) == 1
    assert taste.taste_vector(db)[1] == 1


def test_the_feed_names_a_built_meal(db, monkeypatch):
    monkeypatch.setattr(taste, "LIKE_YOUR", -1.0)
    _build(db, "My rice bowl", ["rice", "chicken", "onion"])
    body = TestClient(main.app).get("/api/recipes/cookable?max_missing=0").json()
    chicken = next(r for r in body["recipes"] if r["id"] == 1)
    assert chicken["like_your"]["name"] == "My rice bowl"
    assert chicken["like_your"]["id"] < 0  # not a recipe: nothing to open


def test_a_built_meal_with_real_ingredients_can_be_rated(db):
    _build(db, "Carrot milk", ["milk", "carrot"])
    meal = TestClient(main.app).get("/api/day").json()["meals"][0]
    assert meal["rateable"] is True


def test_a_product_counts_for_taste_by_its_matched_name(db):
    mid = _build(db, "Carrots in milk", ["carrot"])  # one ingredient alone wouldn't count
    db.execute(
        "INSERT INTO meal_products (meal_id, name, grams, calories_100g, protein_g_100g, carbs_g_100g,"
        " fat_g_100g, canonical) VALUES (?, 'Vollmilch', 150, 64, 3.4, 4.8, 3.5, 'milk')",
        (mid,),
    )
    db.commit()
    assert taste.taste_profile(db).ids == [-mid]
