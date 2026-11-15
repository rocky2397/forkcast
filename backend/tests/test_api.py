"""HTTP surface via TestClient.

The client is built without the lifespan context on purpose: starting it would
construct the Normalizer, which downloads the Epicure vocabulary. Routes that
need the normalizer get a stub instead, so these tests stay offline.
"""

import pytest
from fastapi.testclient import TestClient

from app import embeddings, main, substitutions
from app.normalize import Normalizer

VOCAB = ["chicken", "rice", "onion", "carrot", "egg", "yeast", "milk", "salt"]


@pytest.fixture
def client(db, monkeypatch):
    # Stub the vocabulary rather than downloading 300-dimensional vectors to
    # answer "is this a known ingredient": /health reports its size, and
    # substitutions consult it before anything else. Nothing here reaches the
    # rank arrays, which would need the real weights (see test_substitutions).
    monkeypatch.setattr(embeddings, "vocabulary", lambda: VOCAB)
    substitutions._index.cache_clear()
    main.normalizer = Normalizer(VOCAB)
    yield TestClient(main.app)
    substitutions._index.cache_clear()


def test_health_needs_no_session(client):
    assert client.get("/health").status_code == 200


def test_cookable_feed_lists_stocked_recipes(client):
    body = client.get("/api/recipes/cookable?max_missing=0").json()
    assert {r["id"] for r in body["recipes"]} == {1, 2}
    assert body["personalized"] is False  # nothing logged yet


def test_cookable_feed_carries_an_ingredient_signature(client):
    """The feed's ingredient dots: main ingredients, staples left out."""
    body = client.get("/api/recipes/cookable?max_missing=0").json()
    for r in body["recipes"]:
        names = [i["canonical"] for i in r["signature"]]
        assert "salt" not in names                     # a staple, assumed present
        assert len(names) == len(set(names))           # each ingredient once
        assert all(i["have"] for i in r["signature"])  # cookable now: all in stock
    rice = next(r for r in body["recipes"] if r["id"] == 2)["signature"]
    assert {"canonical": "rice", "family": "grain", "have": True} in rice


def test_min_missing_leaves_out_closer_recipes(client):
    """The feed's "one away" tab: exactly one missing, not cookable-now again."""
    body = client.get("/api/recipes/cookable?max_missing=1&min_missing=1").json()
    assert body["recipes"], "the fixture has recipes one ingredient away"
    assert all(r["ingredients_missing"] == 1 for r in body["recipes"])
    everything = client.get("/api/recipes/cookable?max_missing=1").json()["recipes"]
    assert {r["ingredients_missing"] for r in everything} == {0, 1}


def test_inventory_items_carry_their_food_class(client):
    items = {i["canonical"]: i for i in client.get("/api/inventory").json()["items"]}
    assert items["chicken"]["family"] == "meat"
    assert items["onion"]["family"] == "allium"


def test_recipe_detail_flags_inventory_and_staples(client):
    ings = {i["canonical"]: i for i in client.get("/api/recipes/2").json()["ingredients"]}
    assert ings["rice"]["in_inventory"] is True and ings["rice"]["staple"] is False
    # Staples are assumed present, so salt is flagged rather than "missing".
    assert ings["salt"]["staple"] is True


def test_logging_a_cook_without_a_body_keeps_the_inventory(client, db):
    assert client.post("/api/recipes/1/cooked").json()["removed"] == []
    assert db.execute("SELECT COUNT(*) c FROM inventory").fetchone()["c"] == 5


def test_logging_a_cook_depletes_what_ran_out(client, db):
    body = client.post("/api/recipes/1/cooked", json={"used_up": ["chicken", "onion"]}).json()
    assert sorted(body["removed"]) == ["chicken", "onion"]
    left = {r["canonical"] for r in db.execute("SELECT canonical FROM inventory")}
    assert left == {"rice", "carrot", "egg"}
    assert db.execute("SELECT COUNT(*) c FROM meal_log").fetchone()["c"] == 1


def test_depleting_something_absent_is_ignored_not_an_error(client, db):
    """A stale checklist from another device must not fail the log."""
    body = client.post("/api/recipes/1/cooked", json={"used_up": ["chicken", "unicorn"]}).json()
    assert body["removed"] == ["chicken"]
    assert body["logged"] is True


def test_duplicate_used_up_entries_are_collapsed(client):
    body = client.post("/api/recipes/1/cooked", json={"used_up": ["egg", "egg"]}).json()
    assert body["removed"] == ["egg"]


def test_cooking_an_unknown_recipe_is_404_and_changes_nothing(client, db):
    assert client.post("/api/recipes/9999/cooked", json={"used_up": ["egg"]}).status_code == 404
    assert db.execute("SELECT COUNT(*) c FROM inventory").fetchone()["c"] == 5


def test_macro_steering_is_off_without_a_profile(client):
    body = client.get("/api/recipes/cookable?max_missing=0").json()
    assert body["macro_focus"] is None
    assert all("macro_fit" not in r for r in body["recipes"])


def test_macro_steering_reports_the_focus_with_a_profile(client, profile):
    body = client.get("/api/recipes/cookable?max_missing=0").json()
    assert body["macro_focus"]["macro"] == "protein_g"
    assert any("macro_fit" in r for r in body["recipes"])


def test_macro_steering_switches_off_once_the_day_is_eaten(client, profile):
    profile.execute(
        """INSERT INTO meal_log (name, calories, protein_g, carbs_g, fat_g)
           VALUES ('big day', 2300, 180, 260, 70)"""
    )
    profile.commit()
    body = client.get("/api/recipes/cookable?max_missing=0").json()
    assert body["macro_focus"] is None
    assert all("macro_fit" not in r for r in body["recipes"])


def test_shopping_endpoint_returns_an_ordered_basket(client):
    body = client.get("/api/shopping").json()
    assert [i["canonical"] for i in body["items"]][:2] == ["yeast", "milk"]
    assert body["unlocks_total"] == sum(i["unlocks"] for i in body["items"])
    assert body["partial_scan"] is False


def test_day_summary_totals_what_was_logged(client, profile):
    client.post("/api/meals", json={"name": "eggs", "calories": 200,
                                    "protein_g": 18, "carbs_g": 2, "fat_g": 14})
    body = client.get("/api/day").json()
    assert body["totals"]["calories"] == 200
    assert body["targets"]["protein_g"] == 144  # 1.8 g/kg x 80 kg


def test_password_gate_blocks_api_but_not_the_login_screen(client, monkeypatch):
    monkeypatch.setenv("FORKCAST_PASSWORD", "hunter2")
    assert client.get("/api/recipes/cookable").status_code == 401
    assert client.get("/health").status_code == 200
    assert client.post("/api/login", json={"password": "wrong"}).status_code == 401


def test_logging_in_opens_the_api_and_logging_out_closes_it(client, monkeypatch):
    monkeypatch.setenv("FORKCAST_PASSWORD", "hunter2")
    # Without this the Secure cookie is dropped over the test client's plain
    # HTTP — the same switch DEPLOY.md documents for a LAN run.
    monkeypatch.setenv("FORKCAST_INSECURE_COOKIE", "1")

    assert client.post("/api/login", json={"password": "hunter2"}).status_code == 200
    assert client.get("/api/recipes/cookable").status_code == 200
    assert client.get("/api/session").json() == {"demo": False, "stats": False, "required": True, "authenticated": True}

    client.post("/api/logout")
    assert client.get("/api/recipes/cookable").status_code == 401


def test_session_cookie_is_secure_and_httponly_by_default(client, monkeypatch):
    """A cookie that leaks over plain HTTP or to JS would be a real regression."""
    monkeypatch.setenv("FORKCAST_PASSWORD", "hunter2")
    monkeypatch.delenv("FORKCAST_INSECURE_COOKIE", raising=False)
    header = client.post("/api/login", json={"password": "hunter2"}).headers["set-cookie"]
    assert "Secure" in header and "HttpOnly" in header
