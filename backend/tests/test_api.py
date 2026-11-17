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
    assert client.get("/api/session").json() == {"demo": False, "saved": False, "scans": False, "stats": False, "required": True, "authenticated": True}

    client.post("/api/logout")
    assert client.get("/api/recipes/cookable").status_code == 401


def test_session_cookie_is_secure_and_httponly_by_default(client, monkeypatch):
    """A cookie that leaks over plain HTTP or to JS would be a real regression."""
    monkeypatch.setenv("FORKCAST_PASSWORD", "hunter2")
    monkeypatch.delenv("FORKCAST_INSECURE_COOKIE", raising=False)
    header = client.post("/api/login", json={"password": "hunter2"}).headers["set-cookie"]
    assert "Secure" in header and "HttpOnly" in header


def test_a_scanned_juice_carton_is_fruit_juice_not_the_fruit(client, monkeypatch):
    """D35: the scan endpoint matches what it reads as a product."""
    from app import vision
    from app.normalize import Normalizer

    monkeypatch.setattr(main, "normalizer", Normalizer(["orange", "fruit_juice", "yogurt"]))
    seen = vision.ScanResult(items=[
        vision.SeenItem(name="orange juice", confidence=0.9),
        vision.SeenItem(name="oranges", confidence=0.9),
        vision.SeenItem(name="natural yoghurt", confidence=0.8),
    ])
    monkeypatch.setattr(vision, "extract_items", lambda raw, media_type: seen)
    r = client.post("/api/vision/scan", files={"photo": ("p.jpg", b"\xff\xd8\xff", "image/jpeg")})
    assert r.status_code == 200
    assert [p["canonical"] for p in r.json()["proposals"]] == ["fruit_juice", "orange", "yogurt"]


@pytest.mark.parametrize("read, warns", [
    ((539, 6.3, 57.5, 30.9), False),   # Nutella read right: 9*30.9 + 4*63.8 = 533
    ((1345, 8.3, 60.0, 1.5), True),    # kJ taken for kcal
    ((163, 3.0, 25.0, 1.8), False),    # soy drink, kJ and "2,5" read as 25: they happen to add up (blind spot)
    ((443, 16.0, 70.0, 7.4), False),   # Mars rows swapped: adds up anyway (a known blind spot)
    ((109, 26.0, 0.0, 0.5), False),    # tuna
    ((14, 0.5, 0.0, None), True),      # a value missing
    ((50, None, 69.0, None), True),    # a tester's scan: 69 g carbs alone is ~276 kcal, more than 50
    ((50, None, 6.9, None), True),     # the same with the comma read: still warns, values are missing
    ((15, 0.5, 0.0, 1.1), False),      # tiny values: under the 40 kcal floor
])
def test_label_sum_check(read, warns):
    """D36: the calorie sum check on values read off a label."""
    from app import nutrition

    assert (nutrition.label_check(*read) is not None) is warns


def test_missing_values_are_named_and_the_rest_still_checked():
    """D48: a value missing no longer hides a reading that can't be right."""
    from app import nutrition

    impossible = nutrition.label_check(50, None, 69.0, None)
    assert impossible.startswith("Protein and fat couldn't be read")
    assert "50 kcal is less than the carbs alone would give (about 276 kcal)" in impossible
    plausible = nutrition.label_check(50, None, 6.9, None)
    assert plausible.startswith("Protein and fat couldn't be read") and "less than" not in plausible
    assert nutrition.label_check(None, 1, 2, 3).startswith("The calories couldn't be read")


def _scan(client, monkeypatch, scan, off=None, barcode=None):
    """POST a photo with the label reader and Open Food Facts stubbed."""
    from app import nutrition, vision

    monkeypatch.setattr(vision, "extract_product", lambda raw, media_type: scan)

    def fake_off(code):
        if isinstance(off, Exception):
            raise off
        return off

    monkeypatch.setattr(nutrition, "fetch_off", fake_off)
    data = {"barcode": barcode} if barcode else None
    return client.post("/api/nutrition/scan", files={"photo": ("p.jpg", b"\xff\xd8\xff", "image/jpeg")}, data=data)


def test_a_barcode_that_isnt_on_open_food_facts_says_so(client, monkeypatch):
    """D48: the tester's bag. The barcode was read; the product just isn't listed."""
    from app import vision

    r = _scan(client, monkeypatch, vision.ProductScan(barcode="4306188068372"))
    assert r.status_code == 404
    detail = r.json()["detail"]
    assert detail["barcode"] == "4306188068372"
    assert "isn't on Open Food Facts yet" in detail["message"] and "nutrition table" in detail["message"]


def test_scan_errors_say_what_was_found(client, monkeypatch):
    from app import nutrition, vision

    down = _scan(client, monkeypatch, vision.ProductScan(barcode="4306188068372"), off=nutrition.OffUnavailable("timeout"))
    assert "couldn't be reached" in down.json()["detail"]["message"]
    nothing = _scan(client, monkeypatch, vision.ProductScan())
    assert nothing.json()["detail"] == {
        "message": "Couldn't find a barcode or a nutrition table in the photo. Try a closer, sharper photo of either one.",
        "barcode": None,
    }


def test_a_label_photo_is_returned_under_the_barcode_from_the_earlier_photo(client, monkeypatch):
    """D48: the table is often on another side of the pack than the barcode."""
    from app import vision

    label = vision.NutritionPer100g(calories=350, protein_g=10, carbs_g=61, fat_g=2.6)
    r = _scan(client, monkeypatch, vision.ProductScan(per_100g=label), barcode="4306188068372")
    product = r.json()["product"]
    assert product["barcode"] == "4306188068372" and product["source"] == "label" and product["check"] is None
    # a barcode on the label photo itself wins over the one carried over
    r = _scan(client, monkeypatch, vision.ProductScan(barcode="4000000000017", per_100g=label), barcode="4306188068372")
    assert r.json()["product"]["barcode"] == "4000000000017"


def test_a_saved_label_reading_fills_in_from_the_barcode_and_can_be_forgotten(client, monkeypatch):
    from app import nutrition

    monkeypatch.setattr(nutrition, "fetch_off", lambda code: None)
    body = {"barcode": "4306188068372", "name": "Tortilla chips", "calories_100g": 490,
            "protein_g_100g": 6.5, "carbs_g_100g": 61, "fat_g_100g": 24}
    assert client.get("/api/nutrition/barcode/4306188068372").status_code == 404
    assert client.post("/api/nutrition/products", json=body).status_code == 200
    product = client.get("/api/nutrition/barcode/4306188068372").json()["product"]
    assert product["source"] == "saved" and product["calories_100g"] == 490 and product["name"] == "Tortilla chips"
    assert client.delete("/api/nutrition/products/4306188068372").status_code == 200
    assert client.get("/api/nutrition/barcode/4306188068372").status_code == 404


def test_saving_never_overwrites_open_food_facts_values(client, monkeypatch):
    from app import nutrition

    listed = {"barcode": "4000000000017", "name": "Listed", "brand": None, "calories_100g": 100,
              "protein_g_100g": 1, "carbs_g_100g": 20, "fat_g_100g": 1, "source": "openfoodfacts"}
    monkeypatch.setattr(nutrition, "fetch_off", lambda code: listed)
    assert client.get("/api/nutrition/barcode/4000000000017").status_code == 200
    body = {"barcode": "4000000000017", "calories_100g": 1, "protein_g_100g": 0, "carbs_g_100g": 0, "fat_g_100g": 0}
    assert client.post("/api/nutrition/products", json=body).status_code == 409
    assert client.delete("/api/nutrition/products/4000000000017").status_code == 200
    assert client.get("/api/nutrition/barcode/4000000000017").json()["product"]["calories_100g"] == 100


def test_listed_without_values_can_be_filled_from_a_label(client, monkeypatch):
    from app import nutrition

    empty = {"barcode": "4000000000024", "name": "Listed, no values", "brand": None, "calories_100g": None,
             "protein_g_100g": None, "carbs_g_100g": None, "fat_g_100g": None, "source": "openfoodfacts"}
    monkeypatch.setattr(nutrition, "fetch_off", lambda code: empty)
    client.get("/api/nutrition/barcode/4000000000024")
    body = {"barcode": "4000000000024", "calories_100g": 52, "protein_g_100g": 0.3, "carbs_g_100g": 12, "fat_g_100g": 0.2}
    assert client.post("/api/nutrition/products", json=body).status_code == 200
    assert client.get("/api/nutrition/barcode/4000000000024").json()["product"]["source"] == "saved"


@pytest.mark.parametrize("bad", [
    {"barcode": "abc", "calories_100g": 1, "protein_g_100g": 0, "carbs_g_100g": 0, "fat_g_100g": 0},
    {"barcode": "4306188068372", "calories_100g": 1, "protein_g_100g": 0, "carbs_g_100g": 0},
    {"barcode": "4306188068372", "calories_100g": 1, "protein_g_100g": 0, "carbs_g_100g": 150, "fat_g_100g": 0},
])
def test_saving_needs_a_barcode_and_all_four_values(client, bad):
    assert client.post("/api/nutrition/products", json=bad).status_code == 422


def test_a_label_reading_that_doesnt_add_up_comes_with_a_warning(client, monkeypatch):
    from app import vision

    scan = vision.ProductScan(per_100g=vision.NutritionPer100g(calories=1345, protein_g=8.3, carbs_g=60.0, fat_g=1.5))
    monkeypatch.setattr(vision, "extract_product", lambda raw, media_type: scan)
    r = client.post("/api/nutrition/scan", files={"photo": ("p.jpg", b"\xff\xd8\xff", "image/jpeg")})
    assert r.status_code == 200
    product = r.json()["product"]
    assert product["source"] == "label"
    assert "don't add up" in product["check"]


def test_a_label_reading_that_adds_up_has_no_warning(client, monkeypatch):
    from app import vision

    scan = vision.ProductScan(per_100g=vision.NutritionPer100g(calories=350, protein_g=10, carbs_g=61, fat_g=2.6))
    monkeypatch.setattr(vision, "extract_product", lambda raw, media_type: scan)
    r = client.post("/api/nutrition/scan", files={"photo": ("p.jpg", b"\xff\xd8\xff", "image/jpeg")})
    assert r.json()["product"]["check"] is None


def test_the_label_reader_writes_out_the_table_first():
    """D37: the table comes before per_100g in the schema, so it is generated first."""
    from app import vision

    fields = list(vision.ProductScan.model_fields)
    assert fields.index("table") < fields.index("per_100g")
    assert "kcal" in vision.PRODUCT_PROMPT and "1,2 g" in vision.PRODUCT_PROMPT


def test_a_label_scan_with_a_written_out_table_still_returns_per_100g(client, monkeypatch):
    from app import vision

    scan = vision.ProductScan(
        table=[vision.TableRow(name="Energie", per_100g="1463 kJ / 350 kcal"),
               vision.TableRow(name="Fett", per_100g="2,6 g")],
        per_100g=vision.NutritionPer100g(calories=350, protein_g=10, carbs_g=61, fat_g=2.6),
    )
    monkeypatch.setattr(vision, "extract_product", lambda raw, media_type: scan)
    product = client.post("/api/nutrition/scan", files={"photo": ("p.jpg", b"\xff\xd8\xff", "image/jpeg")}).json()["product"]
    assert product["calories_100g"] == 350 and product["check"] is None


def test_a_goal_weight_is_saved_and_planned(client):
    body = {"sex": "m", "age": 30, "height_cm": 180, "weight_kg": 80, "activity": "moderate",
            "goal": "maintain", "goal_weight_kg": 72, "pace": "steady"}
    r = client.put("/api/profile", json=body)
    assert r.status_code == 200
    assert r.json()["plan"]["calories"] == 2099  # 0.75% of 80 kg a week (D44)
    assert r.json()["profile"]["goal"] == "cut"  # the goal weight decides the direction
    got = client.get("/api/profile").json()
    assert got["profile"]["goal_weight_kg"] == 72 and got["plan"]["weeks"] == 14
    assert client.get("/api/day").json()["plan"]["calories"] == 2099


def test_an_unhealthy_goal_weight_is_refused_with_a_reason(client):
    body = {"sex": "m", "age": 30, "height_cm": 180, "weight_kg": 80, "activity": "moderate",
            "goal": "maintain", "goal_weight_kg": 55}
    r = client.put("/api/profile", json=body)
    assert r.status_code == 422 and "below a healthy weight" in r.json()["detail"]


def test_an_old_database_gains_the_goal_columns(tmp_path):
    import sqlite3

    from app import db as dbmod

    path = tmp_path / "old.db"
    con = sqlite3.connect(path)
    con.execute("""CREATE TABLE profile (id INTEGER PRIMARY KEY, sex TEXT NOT NULL, age INTEGER NOT NULL,
        height_cm REAL NOT NULL, weight_kg REAL NOT NULL, activity TEXT NOT NULL, goal TEXT NOT NULL,
        updated_at TEXT NOT NULL DEFAULT (datetime('now')))""")
    con.execute("INSERT INTO profile (id, sex, age, height_cm, weight_kg, activity, goal) VALUES (1,'f',40,165,70,'light','cut')")
    con.commit()
    con.close()
    con = dbmod.connect(path, attach_corpus=False)
    row = con.execute("SELECT * FROM profile").fetchone()
    assert row["goal_weight_kg"] is None and row["pace"] is None


def test_progress_needs_a_profile_then_reports(client):
    assert client.get("/api/progress").json()["progress"] is None
    client.put("/api/profile", json={"sex": "m", "age": 30, "height_cm": 180, "weight_kg": 80,
                                     "activity": "moderate", "goal": "maintain"})
    p = client.get("/api/progress?tz=60").json()["progress"]
    assert p["burn"] == 2759 and len(p["strip"]) == 14 and "recap" in p


def test_the_day_follows_the_clients_time_zone(client):
    r = client.get("/api/day?tz=-300")
    assert r.status_code == 200 and "date" in r.json()


def test_the_day_check_endpoint(client):
    assert client.put("/api/days/2026-11-14/check", json={"complete": True}).status_code == 200
    assert client.put("/api/days/yesterday/check", json={"complete": True}).status_code == 422



def test_the_weight_endpoints(client):
    client.put("/api/profile", json={"sex": "m", "age": 30, "height_cm": 180, "weight_kg": 82,
                                     "activity": "moderate", "goal": "maintain", "goal_weight_kg": 75})
    assert client.get("/api/weight").json()["entries"] == []
    s = client.post("/api/weight?tz=60", json={"weight_kg": 81.4}).json()
    assert s["trend_kg"] == 81.4 and s["status"] == "not_enough_data"
    assert client.get("/api/profile").json()["profile"]["weight_kg"] == 81.4
    assert client.post("/api/weight", json={"weight_kg": 20}).status_code == 422
    s = client.delete(f"/api/weight/{s['entries'][0]['id']}").json()
    assert s["entries"] == []



def test_health_says_what_is_running_when_the_image_says(client, monkeypatch):
    # The demo's image sets these (deploy/huggingface/Dockerfile); ops/check_live.py reads them.
    assert "commit" not in client.get("/health").json()
    monkeypatch.setenv("FORKCAST_COMMIT", "abc123")
    monkeypatch.setenv("FORKCAST_CORPUS_URL",
                       "https://github.com/rocky2397/forkcast-corpus/releases/download/corpus-20261115-d35/corpus.db")
    got = client.get("/health").json()
    assert got["commit"] == "abc123" and got["corpus"] == "corpus-20261115-d35"


def test_unrecognised_ingredients_get_did_you_mean_suggestions(client, db):
    # D46: a close spelling is offered, never added on its own; a brand gets nothing.
    r = client.post("/api/inventory", json={"items": ["chiken", "Arla", "onion"]}).json()
    assert r["added"] == ["onion"] and r["unknown"] == ["chiken", "Arla"]
    assert r["suggestions"] == {"chiken": ["chicken"]}
    kitchen = {row["canonical"] for row in db.execute("SELECT canonical FROM inventory")}
    assert "chiken" not in kitchen and "Arla" not in kitchen


def test_german_names_can_be_added_to_the_kitchen(client, db):
    r = client.post("/api/inventory", json={"items": ["Zwiebeln", "Hähnchenbrust"]}).json()
    assert r["added"] == ["onion", "chicken"] and r["unknown"] == []
