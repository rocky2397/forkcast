"""Anonymous usage totals for the public demo (D33).

The important tests are the "never stored" ones: whatever a visitor sends,
the written files hold only counts, Forkcast's own ingredient names and
recipe ids.
"""

import json
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app import db, demo, main, stats, stats_page

H = demo.HEADER
VOCAB = set(demo.seed()["kitchen"]) | {"saffron"}


@pytest.fixture
def app(tmp_path, monkeypatch):
    monkeypatch.setenv("FORKCAST_DEMO", "1")
    monkeypatch.setenv("FORKCAST_STATS_DIR", str(tmp_path / "stats"))
    monkeypatch.setattr(db, "DATA_DIR", tmp_path)
    monkeypatch.setattr(main, "normalizer", SimpleNamespace(match=lambda s: s.strip().lower() or None))
    demo.build_template(lambda s: s)
    con = db.connect(demo.template_path())
    con.execute(
        "INSERT INTO recipes (id, name, minutes, steps, calories) VALUES (7, 'saffron rice', 30, '[]', 400)"
    )
    con.execute("INSERT INTO recipe_ingredients (recipe_id, raw, canonical) VALUES (7, 'saffron', 'saffron')")
    con.commit()
    con.close()
    stats._reset_for_tests()
    stats.start(VOCAB)
    yield TestClient(main.app)
    stats._reset_for_tests()


def _new_visitor(client) -> str:
    return client.get("/api/session").headers[H]


def _written(tmp_path) -> str:
    stats.flush()
    return "".join(p.read_text() for p in (tmp_path / "stats").glob("*.json"))


def test_each_new_kitchen_is_one_visitor(app):
    a = _new_visitor(app)
    _new_visitor(app)
    app.get("/api/inventory", headers={H: a})  # returning visitor: not counted again
    assert stats.summary(lambda ids: {})["visitors"] == 2


def test_actions_and_funnel_are_counted_once_per_visitor(app):
    a = _new_visitor(app)
    _new_visitor(app)
    for _ in range(2):
        app.post("/api/inventory", json={"items": ["saffron"]}, headers={H: a})
    app.get("/api/recipes/7", headers={H: a})
    meal = app.post("/api/recipes/7/cooked", json={"used_up": []}, headers={H: a}).json()["meal_log_id"]
    app.post(f"/api/meals/{meal}/rate", json={"liked": True}, headers={H: a})
    app.post("/api/vision/scan", files={"photo": ("p.jpg", b"\xff", "image/jpeg")}, headers={H: a})

    s = stats.summary(lambda ids: {7: "saffron rice"})
    assert s["events"]["ingredient_added"] == 2
    assert s["events"]["recipe_cooked"] == 1
    assert s["events"]["rated_liked"] == 1
    assert s["events"]["photo_scan_tried"] == 1
    assert {k: v["visitors"] for k, v in s["funnel"].items()} == {"visited": 2, "added": 1, "opened": 1, "cooked": 1}
    assert s["funnel"]["cooked"]["share"] == 0.5
    assert s["top_ingredients_added"] == [{"ingredient": "saffron", "times": 2}]
    assert s["top_recipes_opened"] == [{"id": 7, "name": "saffron rice", "times": 1}]


def test_nothing_personal_is_ever_written(app, tmp_path):
    a = _new_visitor(app)
    app.post("/api/inventory", json={"items": ["my secret note"]}, headers={H: a})  # not a Forkcast ingredient
    app.post(
        "/api/meals",
        json={"name": "Dinner at Alex's", "calories": 612, "protein_g": 31, "carbs_g": 40, "fat_g": 20},
        headers={H: a},
    )
    app.put(
        "/api/profile",
        json={"sex": "m", "age": 47, "height_cm": 181, "weight_kg": 93.5, "activity": "light", "goal": "cut"},
        headers={H: a},
    )
    data = json.loads(_written(tmp_path))
    # Timing holds only route templates and measured numbers, which could
    # contain any digits by chance; everything else must hold none of these.
    timing = data.pop("timing")
    assert all(r.startswith(("GET /api/", "POST /api/", "PUT /api/")) for r in timing)
    assert all(set(t) == {"buckets", "count", "total_ms"} for t in timing.values())
    text = json.dumps(data)
    for private in ("secret", "Alex", "612", "47", "181", "93.5", a, "testclient"):
        assert private not in text, private
    assert data["events"]["meal_typed"] == 1
    assert data["events"]["profile_saved"] == 1
    assert data["items"]["ingredient_added"] == {}


def test_unknown_events_and_items_are_dropped(app):
    _new_visitor(app)
    stats.event("made_up_event")
    stats.event("ingredient_added", item="not in the vocabulary")
    stats.event("recipe_opened", item="7")  # must be an int id
    stats.event("recipe_opened", item=True)
    s = stats.summary(lambda ids: {})
    assert "made_up_event" not in s["events"]
    assert s["top_ingredients_added"] == []
    assert s["top_recipes_opened"] == []


def test_totals_survive_a_restart(app, tmp_path):
    _new_visitor(app)
    stats.flush()
    stats._reset_for_tests()  # what a restart does to memory
    stats.start(VOCAB)
    _new_visitor(app)
    stats.flush()
    assert stats.summary(lambda ids: {})["visitors"] == 2


def test_the_stats_pages_count_nobody(app):
    _new_visitor(app)
    for path in ("/stats", "/stats.json"):
        r = app.get(path)
        assert r.status_code == 200
        assert H not in r.headers
    assert app.get("/stats.json").json()["visitors"] == 1
    assert "How the Forkcast demo is used" in app.get("/stats").text


def test_the_page_escapes_what_it_shows():
    s = {
        "since": "2026-11-15", "visitors": 1, "per_day": [{"day": "2026-11-15", "visitors": 1}],
        "funnel": {k: {"visitors": 1, "share": 1.0} for k in stats.FUNNEL}, "events": {},
        "top_ingredients_added": [], "top_recipes_opened": [{"id": 1, "name": "<script>x</script>", "times": 1}],
    }
    page = stats_page.render(s)
    assert "<script>x" not in page
    assert "&lt;script&gt;x&lt;/script&gt;" in page


def test_off_without_a_stats_dir(app, monkeypatch, tmp_path):
    monkeypatch.delenv("FORKCAST_STATS_DIR")
    _new_visitor(app)
    stats.event("ingredient_added", item="saffron")
    assert app.get("/stats").status_code == 404
    assert not list((tmp_path / "stats").glob("*.json"))


def test_times_are_grouped_by_action_not_address(app, tmp_path):
    a = _new_visitor(app)
    app.get("/api/recipes/7", headers={H: a})
    app.get("/api/recipes/8", headers={H: a})  # no such recipe: a 404
    app.get("/api/no-such-thing", headers={H: a})
    text = _written(tmp_path)
    data = json.loads(text)
    route = "GET /api/recipes/{recipe_id:int}"
    assert data["timing"][route]["count"] == 2
    assert sum(data["timing"][route]["buckets"]) == 2
    assert data["errors"]["not_found"] == {route: 1, "other": 1}
    assert "/api/recipes/7" not in text and "no-such-thing" not in text


def test_server_errors_are_counted(app, monkeypatch):
    client = TestClient(main.app, raise_server_exceptions=False)
    a = client.get("/api/session").headers[H]

    def broken():
        raise RuntimeError("boom")

    monkeypatch.setattr(main.taste, "taste_vector", lambda con: broken())
    assert client.get("/api/taste", headers={H: a}).status_code == 500
    s = stats.summary(lambda ids: {})
    taste_row = next(r for r in s["speed"] if r["route"] == "GET /api/taste")
    assert taste_row["server_errors"] == 1
    assert s["errors_per_day"][-1]["server"] == 1


def test_starts_and_the_runs_section(app):
    stats.started(12.34)
    _new_visitor(app)
    s = stats.summary(lambda ids: {})
    assert s["starts"][-1]["seconds"] == 12.3
    page = stats_page.render(s)
    assert "How it runs" in page
    assert "Open the app" in page  # the session route, by its plain name
    assert "usually ready in 12.3 s" in page


def test_percentiles_come_from_the_histogram():
    buckets = [0] * (len(stats.TIME_BUCKETS) + 1)
    buckets[1] = 90   # 90 requests in 10-25 ms
    buckets[4] = 10   # 10 in 100-250 ms
    assert stats._percentile_ms(buckets, 0.5) == 25
    assert stats._percentile_ms(buckets, 0.95) == 250
    buckets[-1] = 1000
    assert stats._percentile_ms(buckets, 0.95) is None  # slower than 5 s
