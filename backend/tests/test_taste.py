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
