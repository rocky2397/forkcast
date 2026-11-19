"""Public demo mode (D32): every visitor gets their own kitchen.

Runs offline: the lifespan (which loads the Epicure weights) is skipped, the
normalizer is a stand-in that accepts any name, and the demo template is built
directly.
"""

import os
import time
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app import db, demo, main

H = demo.HEADER


@pytest.fixture
def demo_app(tmp_path, monkeypatch):
    monkeypatch.setenv("FORKCAST_DEMO", "1")
    monkeypatch.setattr(db, "DATA_DIR", tmp_path)
    monkeypatch.setattr(main, "normalizer", SimpleNamespace(match=lambda s: s.strip().lower() or None))
    assert demo.build_template(lambda s: s) == []
    return TestClient(main.app)


def _visit(client, kitchen=None):
    headers = {H: kitchen} if kitchen else {}
    r = client.get("/api/inventory", headers=headers)
    assert r.status_code == 200
    return r.headers[H], {i["canonical"] for i in r.json()["items"]}


def test_a_visitor_starts_with_the_demo_kitchen(demo_app):
    kitchen, items = _visit(demo_app)
    assert items == set(demo.seed()["kitchen"])
    assert demo_app.get("/api/session").json()["demo"] is True
    # D57: no profile and an empty, unrated day: each visitor starts as themselves.
    assert demo_app.get("/api/profile", headers={H: kitchen}).json()["profile"] is None
    day = demo_app.get("/api/day", headers={H: kitchen}).json()
    assert day["meals"] == []


def test_visitors_cannot_see_each_others_changes(demo_app):
    a, _ = _visit(demo_app)
    b, _ = _visit(demo_app)
    assert a != b
    r = demo_app.post("/api/inventory", json={"items": ["saffron"]}, headers={H: a})
    assert r.headers[H] == a
    assert "saffron" in _visit(demo_app, a)[1]
    assert "saffron" not in _visit(demo_app, b)[1]
    assert "saffron" not in _visit(demo_app)[1]  # nor a newcomer's


def test_the_same_id_keeps_the_same_kitchen(demo_app):
    a, _ = _visit(demo_app)
    demo_app.delete("/api/inventory/basil", headers={H: a})
    again, items = _visit(demo_app, a)
    assert again == a
    assert "basil" not in items


@pytest.mark.parametrize("bad", ["../../etc/passwd", "x" * 22 + "/..", "not-a-kitchen", "A" * 22])
def test_unknown_or_malformed_ids_get_a_fresh_kitchen(demo_app, bad):
    kitchen, items = _visit(demo_app, bad)
    assert kitchen != bad
    assert items == set(demo.seed()["kitchen"])
    assert all(f.parent == demo.kitchens_dir() for f in demo.kitchens_dir().iterdir())


def test_nothing_is_seeded_for_today(demo_app):
    # D57: the demo's earlier cooks are on earlier days (none exist in the
    # test corpus); today is the visitor's own.
    kitchen, _ = _visit(demo_app)
    assert demo_app.get("/api/day", headers={H: kitchen}).json()["meals"] == []
    assert all(c["days_ago"] >= 1 for c in demo.seed()["cooked_earlier"])


def test_scanning_is_off(demo_app):
    photo = {"photo": ("p.jpg", b"\xff\xd8\xff", "image/jpeg")}
    for path in ("/api/vision/scan", "/api/nutrition/scan"):
        r = demo_app.post(path, files=photo)
        assert r.status_code == 403
        assert "switched off in this demo" in r.json()["detail"]


def test_idle_kitchens_are_deleted(demo_app):
    old, _ = _visit(demo_app)
    stale = time.time() - demo.IDLE_SECONDS - 60
    os.utime(demo.kitchens_dir() / f"{old}.db", (stale, stale))
    _visit(demo_app)  # a newcomer triggers the sweep
    assert not (demo.kitchens_dir() / f"{old}.db").exists()
    assert _visit(demo_app, old)[0] != old


def test_kitchens_are_capped(demo_app, monkeypatch):
    monkeypatch.setattr(demo, "MAX_KITCHENS", 3)
    ids = []
    for age in (40, 30, 20):
        k, _ = _visit(demo_app)
        t = time.time() - age
        os.utime(demo.kitchens_dir() / f"{k}.db", (t, t))
        ids.append(k)
    _visit(demo_app)
    left = {f.stem for f in demo.kitchens_dir().glob("*.db")}
    assert len(left) == 3
    assert ids[0] not in left  # least recently used goes first


def test_without_demo_mode_nothing_changes(db, monkeypatch):
    monkeypatch.delenv("FORKCAST_DEMO", raising=False)
    client = TestClient(main.app)
    r = client.get("/api/inventory")
    assert H not in r.headers
    assert {i["canonical"] for i in r.json()["items"]} == {"chicken", "rice", "onion", "carrot", "egg"}
    assert client.get("/api/session").json()["demo"] is False


def test_startup_warms_the_feed_on_the_demo_kitchen(demo_app, monkeypatch):
    calls = []

    def feed(**kwargs):
        calls.append((db.current_db.get(), kwargs["max_missing"]))

    monkeypatch.setattr(main, "cookable_recipes", feed)
    main._warm_up()
    assert calls == [(demo.template_path(), 0), (demo.template_path(), 1)]
    assert db.current_db.get() is None  # no kitchen left set for later requests


# --- saved kitchens (D34): surviving restarts, 30 days, delete my data ---


@pytest.fixture
def saved_app(demo_app, tmp_path, monkeypatch):
    saved = tmp_path / "saved"
    monkeypatch.setenv("FORKCAST_KITCHENS_DIR", str(saved))
    monkeypatch.setattr(demo, "_dirty", set())
    monkeypatch.setattr(demo, "_saved_on", {})
    monkeypatch.setattr(demo, "_swept_saved_at", 0.0)
    return demo_app, saved


def _restart():
    """What a restart of the Space does: every live kitchen is gone."""
    for f in demo.kitchens_dir().glob("*.db"):
        f.unlink()
    demo._dirty.clear()
    demo._saved_on.clear()


def test_a_change_survives_a_restart(saved_app):
    client, saved = saved_app
    a, _ = _visit(client)
    client.post("/api/inventory", json={"items": ["saffron"]}, headers={H: a})
    assert demo.save_pending() == 1
    assert (saved / f"{a}.db").is_file()
    _restart()
    again, items = _visit(client, a)
    assert again == a
    assert "saffron" in items


def test_an_untouched_kitchen_is_not_saved(saved_app):
    client, saved = saved_app
    _visit(client)
    assert demo.save_pending() == 0
    assert not saved.exists() or not list(saved.glob("*.db"))


def test_the_session_says_kitchens_are_saved(saved_app):
    client, _ = saved_app
    assert client.get("/api/session").json()["saved"] is True


def test_without_a_saved_folder_kitchens_are_not_saved(demo_app):
    a, _ = _visit(demo_app)
    demo_app.post("/api/inventory", json={"items": ["saffron"]}, headers={H: a})
    assert demo.save_pending() == 0
    assert demo_app.get("/api/session").json()["saved"] is False


def test_a_visit_refreshes_the_saved_copy_once_a_day(saved_app, monkeypatch):
    client, saved = saved_app
    a, _ = _visit(client)
    client.post("/api/inventory", json={"items": ["saffron"]}, headers={H: a})
    demo.save_pending()
    _visit(client, a)
    assert demo.save_pending() == 0  # already saved today
    monkeypatch.setattr(demo, "_today", lambda: "2099-01-01")
    _visit(client, a)
    assert demo.save_pending() == 1  # next day: the 30 days start again


def test_saved_kitchens_expire_after_30_days(saved_app):
    client, saved = saved_app
    a, _ = _visit(client)
    client.post("/api/inventory", json={"items": ["saffron"]}, headers={H: a})
    demo.save_pending()
    old = time.time() - demo.KEEP_SECONDS - 60
    os.utime(saved / f"{a}.db", (old, old))
    demo._swept_saved_at = 0.0
    demo.save_pending()
    assert not (saved / f"{a}.db").exists()


def test_saved_kitchens_are_capped(saved_app, monkeypatch):
    client, saved = saved_app
    monkeypatch.setattr(demo, "MAX_SAVED", 2)
    ids = []
    for age in (30, 20, 10):
        k, _ = _visit(client)
        client.post("/api/inventory", json={"items": ["saffron"]}, headers={H: k})
        demo._swept_saved_at = time.time()  # no sweep yet
        demo.save_pending()
        t = time.time() - age
        os.utime(saved / f"{k}.db", (t, t))
        ids.append(k)
    demo._swept_saved_at = 0.0
    demo.save_pending()
    assert {f.stem for f in saved.glob("*.db")} == set(ids[1:])


def test_delete_my_data_removes_both_copies(saved_app):
    client, saved = saved_app
    a, _ = _visit(client)
    client.post("/api/inventory", json={"items": ["saffron"]}, headers={H: a})
    demo.save_pending()
    r = client.delete("/api/demo/kitchen", headers={H: a})
    assert r.status_code == 200
    assert H not in r.headers  # nothing for the browser to remember
    assert not (demo.kitchens_dir() / f"{a}.db").exists()
    assert not (saved / f"{a}.db").exists()
    assert demo.save_pending() == 0
    fresh, items = _visit(client, a)
    assert fresh != a
    assert "saffron" not in items


def test_unsaved_changes_are_not_swept_away(saved_app):
    client, saved = saved_app
    a, _ = _visit(client)
    client.post("/api/inventory", json={"items": ["saffron"]}, headers={H: a})
    stale = time.time() - demo.IDLE_SECONDS - 60
    os.utime(demo.kitchens_dir() / f"{a}.db", (stale, stale))
    _visit(client)  # a newcomer triggers the idle sweep
    assert (demo.kitchens_dir() / f"{a}.db").exists()
    demo.save_pending()
    assert (saved / f"{a}.db").is_file()


def test_delete_is_only_for_the_demo(db, monkeypatch):
    monkeypatch.delenv("FORKCAST_DEMO", raising=False)
    assert TestClient(main.app).delete("/api/demo/kitchen").status_code == 404


# --- scanning in the demo (D38): only with an API key, and capped ---


@pytest.fixture
def scanning_app(demo_app, monkeypatch):
    from app import vision

    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key-not-real")
    monkeypatch.setattr(demo, "_scans", {})
    monkeypatch.setattr(demo, "_scans_total", 0)
    monkeypatch.setattr(demo, "_scans_day", "")
    seen = vision.ScanResult(items=[vision.SeenItem(name="garlic", confidence=0.9)])
    monkeypatch.setattr(vision, "extract_items", lambda raw, media_type: seen)
    return demo_app


PHOTO = {"photo": ("p.jpg", b"\xff\xd8\xff", "image/jpeg")}


def test_without_a_key_scanning_stays_off(demo_app, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    assert demo_app.get("/api/session").json()["scans"] is False
    assert demo_app.post("/api/vision/scan", files=PHOTO).status_code == 403


def test_with_a_key_a_visitor_can_scan(scanning_app):
    k, _ = _visit(scanning_app)
    assert scanning_app.get("/api/session").json()["scans"] is True
    r = scanning_app.post("/api/vision/scan", files=PHOTO, headers={H: k})
    assert r.status_code == 200
    assert r.json()["proposals"][0]["seen"] == "garlic"


def test_a_visitor_gets_ten_scans_a_day(scanning_app):
    k, _ = _visit(scanning_app)
    codes = [scanning_app.post("/api/vision/scan", files=PHOTO, headers={H: k}).status_code for _ in range(11)]
    assert codes == [200] * 10 + [429]
    other, _ = _visit(scanning_app)
    assert scanning_app.post("/api/vision/scan", files=PHOTO, headers={H: other}).status_code == 200


def test_the_whole_demo_has_a_daily_cap(scanning_app, monkeypatch):
    monkeypatch.setattr(demo, "SCANS_PER_DAY", 3)
    codes = []
    for _ in range(4):
        k, _ = _visit(scanning_app)
        codes.append(scanning_app.post("/api/vision/scan", files=PHOTO, headers={H: k}).status_code)
    assert codes == [200, 200, 200, 429]


def test_the_caps_reset_the_next_day(scanning_app, monkeypatch):
    k, _ = _visit(scanning_app)
    for _ in range(10):
        scanning_app.post("/api/vision/scan", files=PHOTO, headers={H: k})
    monkeypatch.setattr(demo, "_today", lambda: "2099-01-01")
    assert scanning_app.post("/api/vision/scan", files=PHOTO, headers={H: k}).status_code == 200



def test_earlier_cooks_stay_days_back_for_a_new_visitor(demo_app, monkeypatch):
    # D57: a seeded cook in the template is moved to its own number of days
    # back from now when a visitor's kitchen is copied, never to today. (The
    # test corpus lacks the demo's recipes, so the cook is written directly.)
    import sqlite3
    monkeypatch.setattr(demo, "seed", lambda: {"kitchen": [], "cooked_earlier": [{"recipe_id": 7, "days_ago": 2}]})
    con = sqlite3.connect(demo.template_path())
    con.execute("INSERT INTO meal_log (recipe_id, logged_at) VALUES (7, '2000-01-01 12:00:00')")
    con.commit()
    con.close()
    _, path, new = demo.kitchen(None)
    assert new
    con = sqlite3.connect(path)
    days = con.execute("SELECT julianday('now') - julianday(logged_at) FROM meal_log WHERE recipe_id = 7").fetchone()[0]
    con.close()
    assert 1.99 < days < 2.01
