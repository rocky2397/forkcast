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
    assert demo_app.get("/api/profile").json()["profile"] is not None


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


def test_seeded_meals_are_from_today(demo_app):
    kitchen, _ = _visit(demo_app)
    day = demo_app.get("/api/day", headers={H: kitchen}).json()
    assert [m["name"] for m in day["meals"]] == [demo.seed()["typed_meal"]["name"]]


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
