"""Forkcast API — Phase 1 scaffold.

Run from the repo root:
  .venv/bin/uvicorn app.main:app --app-dir backend --reload
"""

import asyncio
import json
import os
import time
from contextlib import asynccontextmanager, suppress
from datetime import date as _date
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, Query, Request, Response, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.concurrency import run_in_threadpool
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, field_validator
from typing import Literal

from . import adaptive, auth, demo, embeddings, foods, goals, nutrition, progress, recipes, shopping, stats, stats_page, substitutions, taste, weight
from .food_classes import NAME_TO_CLASS
from .db import connect, current_db
from .normalize import Normalizer, packaged

normalizer: Normalizer | None = None
_LOADED_AT = time.monotonic()  # for how long a start takes (D33)


@asynccontextmanager
async def lifespan(app: FastAPI):
    global normalizer
    normalizer = Normalizer(embeddings.vocabulary())  # also warms the cooc model
    if demo.enabled():
        unknown = demo.build_template(normalizer.match)
        if unknown:
            raise RuntimeError(f"demo kitchen items not recognised: {unknown}")
        await asyncio.to_thread(_warm_up)
    saver = asyncio.create_task(_save_kitchens()) if demo.saved_dir() else None
    flusher = None
    if stats.enabled():  # anonymous usage totals (D33)
        stats.start(embeddings.vocabulary())
        stats.started(stats.seconds_since_process_start(_LOADED_AT))
        flusher = asyncio.create_task(_flush_stats())
    yield
    if flusher is not None:
        flusher.cancel()
        with suppress(asyncio.CancelledError):
            await flusher
        stats.flush()
    if saver is not None:
        saver.cancel()
        with suppress(asyncio.CancelledError):
            await saver
        demo.save_pending()  # nobody's changes are lost to a restart


def _warm_up() -> None:
    """Do the recipe feed's one-off work at startup, not for the first visitor.

    The first feed builds the taste "dish space" and reads the corpus from
    disk: about 0.6 s on a laptop, 2.5 s on the demo's host, every time the
    demo wakes up. Running the feed once against the demo's starting kitchen
    moves that into the start.
    """
    token = current_db.set(demo.template_path())
    try:
        cookable_recipes(max_missing=0, assume_staples=True, limit=20, min_missing=0)
        cookable_recipes(max_missing=1, assume_staples=True, limit=20, min_missing=1)
    finally:
        current_db.reset(token)


async def _save_kitchens():
    """Copy changed demo kitchens to the saved folder (D34)."""
    while True:
        await asyncio.sleep(demo.SAVE_SECONDS)
        await asyncio.to_thread(demo.save_pending)


async def _flush_stats():
    while True:
        await asyncio.sleep(stats.FLUSH_SECONDS)
        await asyncio.to_thread(stats.flush)


app = FastAPI(title="Forkcast API", lifespan=lifespan)

# Paths reachable without a session: the login exchange itself, the health
# check, and the static frontend (the SPA shell has to load to *render* the
# login screen — the data behind it is what's guarded).
_OPEN_PATHS = {"/api/login", "/api/logout", "/api/session", "/health"}


@app.middleware("http")
async def require_session(request: Request, call_next):
    """Gate /api/* behind the shared password (D15). No-op when unset."""
    path = request.url.path
    if auth.required() and path.startswith("/api/") and path not in _OPEN_PATHS:
        if not auth.valid_token(request.cookies.get(auth.COOKIE)):
            return JSONResponse({"detail": "not authenticated"}, status_code=401)
    return await call_next(request)


@app.middleware("http")
async def demo_kitchen(request: Request, call_next):
    """Public demo (D32): run each API request against the visitor's own kitchen."""
    if not demo.enabled() or not request.url.path.startswith("/api/"):
        return await call_next(request)
    kitchen_id, path, created = await run_in_threadpool(demo.kitchen, request.headers.get(demo.HEADER))
    token = current_db.set(path)
    id_token = demo.current_id.set(kitchen_id)
    kitchen_token = stats.current_kitchen.set(kitchen_id)
    counting_token = stats.counting.set(request.headers.get(stats.CHECK_HEADER) != "1")
    began = time.perf_counter()
    status = 500  # unless a response comes back
    try:
        if created:
            stats.visit()
        response = await call_next(request)
        status = response.status_code
    finally:
        route = request.scope.get("route")
        stats.request_done(
            f"{request.method} {route.path}" if route else None,
            status,
            (time.perf_counter() - began) * 1000,
        )
        stats.counting.reset(counting_token)
        stats.current_kitchen.reset(kitchen_token)
        demo.current_id.reset(id_token)
        current_db.reset(token)
    if not path.is_file():
        return response  # deleted by its visitor: the next request starts afresh
    if request.method not in ("GET", "HEAD") and status < 400:
        demo.changed(kitchen_id)
    response.headers[demo.HEADER] = kitchen_id
    return response


# Added after the gate so it wraps it: CORS headers must be present on the
# 401 too, or a cross-origin caller sees an opaque network error instead.
from fastapi.middleware.cors import CORSMiddleware  # noqa: E402

# In dev the Vite server proxies /api, so the browser is always same-origin and
# no CORS is needed. Permissive CORS stays only for the unauthenticated local
# case (phone hitting the API host directly); with a password set, cookies are
# credentialed and "*" would be both invalid and wrong.
if not auth.required():
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )


@app.get("/health")
def health():
    out = {"status": "ok", "vocab_size": len(embeddings.vocabulary())}
    # Set in the demo's image: what is running, for the post-deploy check.
    if os.environ.get("FORKCAST_COMMIT"):
        out["commit"] = os.environ["FORKCAST_COMMIT"]
    if os.environ.get("FORKCAST_CORPUS_URL"):
        out["corpus"] = os.environ["FORKCAST_CORPUS_URL"].rstrip("/").split("/")[-2]
    return out


class Login(BaseModel):
    password: str


@app.get("/api/session")
def session(request: Request):
    """Whether a password is configured, and whether this caller has passed it."""
    return {
        "demo": demo.enabled(),
        "saved": demo.saved_dir() is not None,
        "scans": demo.scanning(),  # D38
        "stats": stats.enabled(),
        "required": auth.required(),
        "authenticated": not auth.required()
        or auth.valid_token(request.cookies.get(auth.COOKIE)),
    }


@app.delete("/api/demo/kitchen")
def delete_my_kitchen():
    """Public demo (D34): delete this visitor's kitchen, live and saved."""
    kitchen_id = demo.current_id.get()
    if not demo.enabled() or kitchen_id is None:
        raise HTTPException(404, "only the public demo keeps visitor kitchens")
    demo.delete(kitchen_id)
    return {"deleted": True}


class Step(BaseModel):
    step: str = Field(max_length=40)


@app.post("/api/stats/step")
def stats_step(body: Step):
    """D68: a funnel step only the browser sees (finishing the welcome).

    Only names in stats.STEPS count; anything else is dropped, never stored.
    """
    stage = stats.STEPS.get(body.step)
    if stage:
        stats.event(body.step, stage=stage)
    elif body.step in stats.BROWSER_EVENTS:  # D73: opened from the home screen, installed
        stats.event(body.step)
    return {"counted": bool(stage or body.step in stats.BROWSER_EVENTS) and stats.enabled()}


@app.post("/api/login")
def login(body: Login, request: Request, response: Response):
    if not auth.required():
        return {"authenticated": True}
    client = request.client.host if request.client else "unknown"
    if auth.rate_limited(client):
        raise HTTPException(429, "too many attempts — wait a few minutes")
    if not auth.check_password(body.password):
        auth.record_attempt(client)
        raise HTTPException(401, "wrong password")
    auth.clear_attempts(client)
    response.set_cookie(auth.COOKIE, auth.issue_token(), **auth.cookie_kwargs())
    return {"authenticated": True}


@app.post("/api/logout")
def logout(response: Response):
    response.delete_cookie(auth.COOKIE, path="/")
    return {"authenticated": False}


@app.get("/api/normalize")
def normalize(q: str = Query(..., min_length=1, max_length=200)):
    """Free-text ingredient -> canonical Epicure ingredient (or null)."""
    return {"query": q, "canonical": normalizer.match(q)}


@app.get("/api/ingredients/{name}/neighbors")
def ingredient_neighbors(
    name: str,
    model: str = Query("cooc", pattern="^(cooc|core|chem)$"),
    k: int = Query(5, ge=1, le=25),
):
    """Nearest neighbours. model=cooc answers "what pairs with X",
    model=chem answers "what substitutes for X"."""
    canonical = normalizer.match(name)
    if canonical is None:
        raise HTTPException(404, f"unknown ingredient: {name!r}")
    return {
        "ingredient": canonical,
        "model": model,
        "neighbors": embeddings.neighbors(canonical, model=model, k=k),
    }


class InventoryAdd(BaseModel):
    # D66: bounded like the meal box: 50 names of up to 100 characters.
    items: list[str] = Field(max_length=50)

    @field_validator("items")
    @classmethod
    def _short(cls, v: list[str]) -> list[str]:
        if any(len(x) > 100 for x in v):
            raise ValueError("Each ingredient name can be up to 100 characters.")
        return v


@app.get("/api/inventory")
def get_inventory():
    with connect() as con:
        rows = con.execute("SELECT canonical, added_at FROM inventory ORDER BY canonical").fetchall()
    # family: the food class (D28), so the kitchen screen can group and colour items
    return {"items": [{**dict(r), "family": NAME_TO_CLASS.get(r["canonical"]),
                       "name": foods.kitchen_label(r["canonical"])} for r in rows]}


@app.post("/api/inventory")
def add_inventory(body: InventoryAdd, source: Literal["recipe"] | None = None):
    added, unknown, already = [], [], []
    with connect() as con:
        have = {r["canonical"] for r in con.execute("SELECT canonical FROM inventory")}
        for raw in body.items:
            canonical = foods.kitchen_match(normalizer, raw)
            if canonical is None:
                unknown.append(raw)
                continue
            # D66: "Tomaten, tomatoes" is one tomato, and one already there is said so.
            if canonical in have:
                if canonical not in added and canonical not in already:
                    already.append(canonical)
                continue
            con.execute("INSERT OR IGNORE INTO inventory (canonical) VALUES (?)", (canonical,))
            added.append(canonical)
            have.add(canonical)
        con.commit()
    for canonical in added:
        stats.event("ingredient_added", item=canonical, stage="added")
    if source == "recipe" and added:
        stats.event("kitchen_fixed_on_recipe")  # D70: "Have it" on a recipe
    # D46: "Did you mean…?" for what wasn't recognised (never counted or stored).
    suggestions = {raw: normalizer.suggest(raw) for raw in unknown}
    return {"added": added, "added_names": [foods.kitchen_label(c) for c in added],
            "already": [foods.kitchen_label(c) for c in already], "unknown": unknown,
            "suggestions": {k: v for k, v in suggestions.items() if v}}


@app.delete("/api/inventory/{name}")
def remove_inventory(name: str, source: Literal["recipe"] | None = None):
    canonical = normalizer.match(name) or name
    with connect() as con:
        cur = con.execute("DELETE FROM inventory WHERE canonical = ?", (canonical,))
        con.commit()
    if cur.rowcount == 0:
        raise HTTPException(404, f"not in inventory: {name!r}")
    stats.event("ingredient_removed")
    if source == "recipe":
        stats.event("kitchen_fixed_on_recipe")  # D70: "Don't have it" on a recipe
    return {"removed": canonical}


@app.get("/api/recipes/{recipe_id:int}")
def recipe_detail(recipe_id: int):
    import json as _json

    with connect() as con:
        r = con.execute("SELECT * FROM recipes WHERE id = ?", (recipe_id,)).fetchone()
        if r is None:
            raise HTTPException(404, f"no recipe {recipe_id}")
        stats.event("recipe_opened", item=recipe_id, stage="opened")
        ings = con.execute(
            """SELECT ri.raw, ri.canonical, inv.canonical IS NOT NULL AS in_inventory
               FROM recipe_ingredients ri
               LEFT JOIN inventory inv ON inv.canonical = ri.canonical
               WHERE ri.recipe_id = ?""",
            (recipe_id,),
        ).fetchall()
        inv = [row["canonical"] for row in con.execute("SELECT canonical FROM inventory")]
    in_recipe = {i["canonical"] for i in ings if i["canonical"]}
    cands = [c for c in inv if c not in in_recipe]
    return {
        "id": r["id"],
        "name": r["name"],
        "minutes": r["minutes"],
        "description": r["description"],
        "steps": _json.loads(r["steps"] or "[]"),
        "calories": r["calories"],
        "protein_g": r["protein_g"],
        "carbs_g": r["carbs_g"],
        "fat_g": r["fat_g"],
        "ingredients": [
            {
                "raw": i["raw"],
                "canonical": i["canonical"],
                "in_inventory": bool(i["in_inventory"]),
                "staple": i["canonical"] in recipes.STAPLES,
                "sub": (sub := (
                    substitutions.suggest(i["canonical"], cands)
                    if i["canonical"] and not i["in_inventory"]
                    else None
                )),
                # D70: what "I ate it" starts ticked as run out.
                "runs_out": NAME_TO_CLASS.get(i["canonical"]) in recipes.RUNS_OUT_FAMILIES,
                "sub_runs_out": bool(sub) and NAME_TO_CLASS.get(sub) in recipes.RUNS_OUT_FAMILIES,
            }
            for i in ings
        ],
    }


class CookedIn(BaseModel):
    used_up: list[str] = Field(default_factory=list, max_length=50)
    servings: float = Field(1, gt=0, le=10)  # D56
    logged_at: str | None = None  # D56: ISO time with offset; now when left out


SERVING_MACROS = ("calories", "protein_g", "carbs_g", "fat_g")


def _scaled(con, recipe_id: int, servings: float) -> tuple:
    """D56: a recipe's macros times the servings eaten, or NULLs for exactly one
    (then the recipe's own numbers are read, as before)."""
    if servings == 1:
        return (None, None, None, None, None)
    r = con.execute("SELECT calories, protein_g, carbs_g, fat_g FROM recipes WHERE id = ?", (recipe_id,)).fetchone()
    return (*(None if r[k] is None else round(r[k] * servings, 1) for k in SERVING_MACROS), servings)


def _logged_at(value: str | None) -> str | None:
    """D56: an ISO time with its offset ("2026-11-18T12:00:00+01:00") -> UTC as
    SQLite's datetime('now') writes it, or None for now. Not in the future,
    not more than 60 days back."""
    if value is None:
        return None
    from datetime import datetime, timedelta, timezone
    try:
        t = datetime.fromisoformat(value)
    except ValueError:
        raise HTTPException(422, "That time couldn't be read.") from None
    if t.tzinfo is None:
        raise HTTPException(422, "The time needs its offset from UTC.")
    utc = t.astimezone(timezone.utc).replace(tzinfo=None)
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    if utc > now + timedelta(minutes=10):
        raise HTTPException(422, "A meal can't be logged in the future.")
    if utc < now - timedelta(days=60):
        raise HTTPException(422, "Meals can be logged up to 60 days back.")
    return utc.strftime("%Y-%m-%d %H:%M:%S")


@app.post("/api/recipes/{recipe_id:int}/cooked")
def log_cooked(recipe_id: int, body: CookedIn | None = None):
    """Log a cook; optionally deplete inventory items the cook used up.

    used_up entries not currently in the inventory are ignored, so a stale
    checklist (item already removed on another device) can't fail the log.
    """
    body = body or CookedIn()
    used_up = body.used_up
    when = _logged_at(body.logged_at)
    with connect() as con:
        if con.execute("SELECT 1 FROM recipes WHERE id = ?", (recipe_id,)).fetchone() is None:
            raise HTTPException(404, f"no recipe {recipe_id}")
        stats.event("recipe_cooked", item=recipe_id, stage="cooked")
        cur = con.execute(
            "INSERT INTO meal_log (recipe_id, calories, protein_g, carbs_g, fat_g, servings, logged_at)"
            " VALUES (?, ?, ?, ?, ?, ?, COALESCE(?, datetime('now')))",
            (recipe_id, *_scaled(con, recipe_id, body.servings), when),
        )
        removed = [
            c for c in dict.fromkeys(used_up)
            if con.execute("DELETE FROM inventory WHERE canonical = ?", (c,)).rowcount
        ]
        con.commit()
    return {"logged": True, "meal_log_id": cur.lastrowid, "recipe_id": recipe_id, "removed": removed}


@app.get("/api/recipes/cookable")
def cookable_recipes(
    max_missing: int = Query(0, ge=0, le=3),
    assume_staples: bool = True,
    limit: int = Query(20, ge=1, le=100),
    min_missing: int = Query(0, ge=0, le=3),
):
    """Recipes you can cook now (max_missing=0) or almost (1-3 missing).

    Re-ranked within each missing-count group (fewest-missing always wins
    first) by taste similarity once cooks have been logged, and by how well
    the serving fits what's left of today's macro budget (D20).
    """
    stats.event("picks_seen", stage="picks")  # D68: the funnel step "saw meal picks"
    with connect() as con:
        profile = taste.taste_profile(con)
        budget = _remaining_today(con)
        pool = min(limit * 8, 300) if profile is not None or budget else limit
        results = recipes.cookable(
            con, max_missing=max_missing, assume_staples=assume_staples, limit=pool,
            min_missing=min_missing,
        )
        if profile is not None:
            matches = taste.match_recipes(con, [r["id"] for r in results], profile)
            for r in results:
                score, _ = matches.get(r["id"], (0.0, None))
                r["taste_sim"] = round(score, 3)
        if budget:
            for r in results:
                fit = goals.macro_fit(r, budget["remaining"])
                if fit is not None:
                    r["macro_fit"] = round(fit, 3)
        if profile is not None or budget:
            results.sort(key=lambda r: (r["ingredients_missing"], -_rank_score(r)))
        results = _distinct(results)[:limit]
        if profile is not None:
            _annotate_like_your(con, results, matches, profile)
        _annotate_subs(con, results)
        _annotate_signature(con, results)
    return {
        "count": len(results),
        "personalized": profile is not None,
        "macro_focus": budget["focus"] if budget else None,
        "recipes": results,
    }


# --- D71: the shopping list ---------------------------------------------------

class ListAdd(BaseModel):
    items: list[str] = Field(min_length=1, max_length=50)
    reason: Literal["ran_out", "missing", "worth_buying", "typed"] = "typed"

    @field_validator("items")
    @classmethod
    def _short(cls, v: list[str]) -> list[str]:
        if any(len(x) > 80 for x in v):
            raise ValueError("each item at most 80 characters")
        return v


class ListBought(BaseModel):
    items: list[str] = Field(min_length=1, max_length=50)


def _list_items(con) -> list[dict]:
    have = {r["canonical"] for r in con.execute("SELECT canonical FROM inventory")}
    rows = con.execute("SELECT canonical, reason, added_at FROM shopping_list ORDER BY added_at, canonical").fetchall()
    return [{"canonical": r["canonical"], "name": foods.kitchen_label(r["canonical"]), "reason": r["reason"],
             "family": NAME_TO_CLASS.get(r["canonical"]), "in_kitchen": r["canonical"] in have} for r in rows]


@app.get("/api/list")
def get_list():
    """D71: the shopping list, oldest first."""
    with connect() as con:
        return {"items": _list_items(con)}


@app.post("/api/list")
def add_to_list(body: ListAdd):
    """D71: put foods on the list; names are matched like the kitchen's."""
    added, already, unknown = [], [], []
    with connect() as con:
        on = {r["canonical"] for r in con.execute("SELECT canonical FROM shopping_list")}
        for raw in body.items:
            c = foods.kitchen_match(normalizer, raw)
            if c is None:
                unknown.append(raw)
            elif c in on:
                if c not in already and c not in added:
                    already.append(c)
            else:
                con.execute("INSERT INTO shopping_list (canonical, reason) VALUES (?, ?)", (c, body.reason))
                added.append(c)
                on.add(c)
        con.commit()
        items = _list_items(con)
    if added:
        stats.event(f"list_added_{body.reason}")
    return {"added": [foods.kitchen_label(c) for c in added], "already": [foods.kitchen_label(c) for c in already],
            "unknown": unknown, "items": items}


@app.delete("/api/list/{canonical}")
def remove_from_list(canonical: str):
    with connect() as con:
        con.execute("DELETE FROM shopping_list WHERE canonical = ?", (canonical,))
        con.commit()
        return {"items": _list_items(con)}


@app.post("/api/list/bought")
def list_bought(body: ListBought):
    """D71: what was bought goes into the kitchen and off the list."""
    with connect() as con:
        on = {r["canonical"] for r in con.execute("SELECT canonical FROM shopping_list")}
        moved = [c for c in dict.fromkeys(body.items) if c in on]
        for c in moved:
            con.execute("INSERT OR IGNORE INTO inventory (canonical) VALUES (?)", (c,))
            con.execute("DELETE FROM shopping_list WHERE canonical = ?", (c,))
        con.commit()
        items = _list_items(con)
    if moved:
        stats.event("list_bought")
    return {"moved": [foods.kitchen_label(c) for c in moved], "items": items}


@app.get("/api/shopping")
def shopping_suggestions(
    basket: int = Query(3, ge=1, le=5),
    max_missing: int = Query(3, ge=1, le=3),
):
    """What to buy to unlock the most recipes you'd like (D21).

    Deliberately ignores today's macro budget: you shop for the days ahead,
    not for tonight's remaining protein.
    """
    with connect() as con:
        profile = taste.taste_profile(con)
        me = con.execute("SELECT goal FROM profile WHERE id = 1").fetchone()
        losing = me is not None and me["goal"] == "cut"
        items, truncated = shopping.suggest(
            con, profile=profile, basket_size=basket, max_missing=max_missing,
            leave_out_sweet=losing,  # D59
        )
    return {
        "personalized": profile is not None,
        "without_desserts": losing,
        "unlocks_total": sum(i["unlocks"] for i in items),
        # True means the candidate pool hit its ceiling, so the basket is the
        # best over a subset — not over every near-miss recipe.
        "partial_scan": truncated,
        "items": items,
    }


# Taste outweighs macro fit: taste is learned over months, macro fit is a
# within-day nudge — the feed should stay recognizably yours on a protein day.
TASTE_WEIGHT = 0.6
MACRO_WEIGHT = 0.4


def _distinct(results: list[dict]) -> list[dict]:
    """D59: one of each recipe that food.com has twice under two names (same
    calories, protein, carbs, fat and ingredients), the first as ranked."""
    seen: set[tuple] = set()
    out = []
    for r in results:
        key = (r.get("calories"), r.get("protein_g"), r.get("carbs_g"), r.get("fat_g"),
               r.get("ingredients_needed"), tuple(r.get("missing") or ()))
        if key[0] is not None and key in seen:
            continue
        seen.add(key)
        out.append(r)
    return out


def _annotate_like_your(con, results: list[dict], matches: dict, profile) -> None:
    """Name the cooked dish (or built meal, D49) a recipe is closest to, when it is close (D31)."""
    named = {rid: d for rid, (_, d) in matches.items() if d is not None}
    if not named:
        return
    ids = sorted(d for d in set(named.values()) if d > 0)
    names = dict(con.execute(
        f"SELECT id, name FROM recipes WHERE id IN ({','.join('?' * len(ids))})", ids
    ).fetchall()) if ids else {}
    names.update(profile.names)
    for r in results:
        d = named.get(r["id"])
        if d is not None and d in names:
            r["like_your"] = {"id": d, "name": names[d]}


def _rank_score(r: dict) -> float:
    return TASTE_WEIGHT * r.get("taste_sim", 0.0) + MACRO_WEIGHT * r.get("macro_fit", 0.0)


def _remaining_today(con) -> dict | None:
    """Today's leftover macro budget + which macro is furthest behind (D20).

    None when there is no profile to derive targets from, or when so little of
    the day is left that steering suggestions by it would be noise.
    """
    profile, _ = adaptive.profile_with_burn(con)
    if profile is None:
        return None
    target = goals.targets(profile)
    totals = con.execute(
        """SELECT COALESCE(SUM(COALESCE(ml.calories, r.calories)), 0)   AS calories,
                  COALESCE(SUM(COALESCE(ml.protein_g, r.protein_g)), 0) AS protein_g,
                  COALESCE(SUM(COALESCE(ml.carbs_g, r.carbs_g)), 0)     AS carbs_g,
                  COALESCE(SUM(COALESCE(ml.fat_g, r.fat_g)), 0)         AS fat_g
           FROM meal_log ml
           LEFT JOIN recipes r ON r.id = ml.recipe_id
           WHERE date(ml.logged_at, 'localtime') = date('now', 'localtime')"""
    ).fetchone()
    rem = goals.remaining(dict(totals), target)
    if rem["calories"] < goals.MIN_REMAINING_KCAL:
        return None
    return {"remaining": rem, "focus": goals.focus(rem, target)}


SIGNATURE_SIZE = 6


def _annotate_signature(con, results: list[dict]) -> None:
    """Attach each recipe's main ingredients for the feed's ingredient dots.

    Up to SIGNATURE_SIZE non-staple ingredients in recipe order, each with its
    food class (D28, which the UI turns into a colour) and whether it is in
    the inventory. Staples are left out: they are assumed present and would
    put the same salt-and-oil dots on every card.
    """
    ids = [r["id"] for r in results]
    if not ids:
        return
    inv = {row["canonical"] for row in con.execute("SELECT canonical FROM inventory")}
    placeholders = ",".join("?" * len(ids))
    by_recipe: dict[int, list[str]] = {}
    for row in con.execute(
        f"SELECT recipe_id, canonical FROM recipe_ingredients "
        f"WHERE recipe_id IN ({placeholders}) AND canonical IS NOT NULL ORDER BY rowid",
        ids,
    ):
        seen = by_recipe.setdefault(row["recipe_id"], [])
        c = row["canonical"]
        if c not in recipes.STAPLES and c not in seen:
            seen.append(c)
    for r in results:
        r["signature"] = [
            {"canonical": c, "family": NAME_TO_CLASS.get(c), "have": c in inv}
            for c in by_recipe.get(r["id"], [])[:SIGNATURE_SIZE]
        ]


def _annotate_subs(con, results: list[dict]) -> None:
    """Attach {missing -> in-inventory stand-in} to each recipe (D13)."""
    ids = [r["id"] for r in results if r["ingredients_missing"] > 0]
    inv = [row["canonical"] for row in con.execute("SELECT canonical FROM inventory")]
    have: dict[int, set[str]] = {}
    if ids and inv:
        placeholders = ",".join("?" * len(ids))
        for row in con.execute(
            f"SELECT recipe_id, canonical FROM recipe_ingredients "
            f"WHERE recipe_id IN ({placeholders}) AND canonical IS NOT NULL",
            ids,
        ):
            have.setdefault(row["recipe_id"], set()).add(row["canonical"])
    for r in results:
        subs = {}
        if r["ingredients_missing"] > 0 and inv:
            cands = [c for c in inv if c not in have.get(r["id"], set())]
            for m in r["missing"]:
                sub = substitutions.suggest(m, cands)
                if sub:
                    subs[m] = sub
        r["subs"] = subs


async def _read_photo(photo: UploadFile) -> bytes:
    if photo.content_type not in ("image/jpeg", "image/png", "image/webp", "image/gif"):
        raise HTTPException(415, f"unsupported image type: {photo.content_type}")
    raw = await photo.read()
    if len(raw) > 20_000_000:
        raise HTTPException(413, "image too large")
    return raw


def _proposals(items) -> list[dict]:
    """What the photo reader saw, matched to ingredients (D35) and marked sure
    or not (D69). One proposal per ingredient: "chicken breast" and "whole
    chicken" are both chicken, kept once at the higher confidence."""
    from . import vision

    out: list[dict] = []
    by_canonical: dict[str, dict] = {}
    for item in items:
        canonical = packaged(normalizer, item.name)  # D35: read off a product
        p = {"seen": item.name, "quantity": item.quantity, "confidence": item.confidence,
             "canonical": canonical, "sure": item.confidence >= vision.SURE_LINE}
        if canonical and canonical in by_canonical:
            if item.confidence > by_canonical[canonical]["confidence"]:
                by_canonical[canonical].update(p)
            continue
        if canonical:
            by_canonical[canonical] = p
        out.append(p)
    return out


@app.post("/api/vision/sample")
def vision_sample():
    """D69: the demo's "Use a sample fridge": a recorded scan of a public photo,
    so a visitor sees the fridge scan without a camera or a paid call."""
    from . import vision

    data = json.loads((Path(__file__).parent / "sample_fridge.json").read_text())
    if demo.enabled():
        stats.event("sample_fridge_used")
    items = [vision.SeenItem(**i) for i in data["items"]]
    return {"proposals": _proposals(items), "photo": data["photo"], "credit": data["credit"]}


@app.post("/api/vision/scan")
async def vision_scan(photo: UploadFile = File(...)):
    """Fridge or groceries photo -> proposed items (nothing committed; client confirms)."""
    if demo.enabled():
        stats.event("photo_scan_tried")
        if not demo.scanning():
            raise HTTPException(403, demo.SCAN_OFF)
        refused = demo.take_scan(demo.current_id.get())  # D38: caps
        if refused:
            raise HTTPException(429, refused)
    from . import vision

    raw = await _read_photo(photo)
    try:
        result = vision.extract_items(raw, photo.content_type)
    except Exception as e:  # surface API failures as a clean 502
        raise HTTPException(502, f"vision extraction failed: {e}")
    return {"proposals": _proposals(result.items)}


class ProfileIn(BaseModel):
    sex: Literal["m", "f"]
    age: int = Field(ge=14, le=100)
    height_cm: float = Field(ge=120, le=230)
    weight_kg: float = Field(ge=35, le=250)
    activity: Literal["sedentary", "light", "moderate", "active", "very_active"]
    goal: Literal["cut", "maintain", "bulk"]
    # D39: optional; when set, it decides the direction and the pace the size
    goal_weight_kg: float | None = Field(default=None, ge=35, le=250)
    pace: Literal["gentle", "steady"] | None = "steady"  # None (older profiles): steady


@app.get("/api/profile")
def get_profile(tz: int = Query(0, ge=-840, le=840)):
    with connect() as con:
        profile, est = adaptive.profile_with_burn(con, tz)
    if profile is None:
        return {"profile": None, "targets": None, "plan": None, "burn": None}
    return {"profile": adaptive.public(profile), "targets": goals.targets(profile),
            "plan": goals.plan(profile), "burn": est}


@app.put("/api/profile")
def put_profile(body: ProfileIn, tz: int = Query(0, ge=-840, le=840), sample: bool = False):
    data = body.model_dump()
    problem = goals.goal_problem(data)  # D39 guardrails
    if problem:
        raise HTTPException(422, problem)
    p = goals.plan(data)
    if p is not None:  # the goal weight decides the direction
        data["goal"] = {"lose": "cut", "keep": "maintain", "gain": "bulk"}[p["direction"]]
    with connect() as con:
        con.execute(
            """INSERT INTO profile (id, sex, age, height_cm, weight_kg, activity, goal,
                                    goal_weight_kg, pace, updated_at)
               VALUES (1, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
               ON CONFLICT(id) DO UPDATE SET
                 sex = excluded.sex, age = excluded.age,
                 height_cm = excluded.height_cm, weight_kg = excluded.weight_kg,
                 activity = excluded.activity, goal = excluded.goal,
                 goal_weight_kg = excluded.goal_weight_kg, pace = excluded.pace,
                 updated_at = excluded.updated_at""",
            (data["sex"], data["age"], data["height_cm"], data["weight_kg"], data["activity"],
             data["goal"], data["goal_weight_kg"], data["pace"]),
        )
        con.commit()
        profile, est = adaptive.profile_with_burn(con, tz)  # D45: the learned burn, if any
    stats.event("profile_saved", stage="profiled")  # that it changed, never the values
    if sample:  # D68: the demo's "Use a sample person" (how many, not who)
        stats.event("sample_profile_used")
    return {"profile": adaptive.public(profile), "targets": goals.targets(profile),
            "plan": goals.plan(profile), "burn": est}


@app.get("/api/foods")
def find_food(q: str = Query(..., min_length=1, max_length=100)):
    """A typed food or ingredient -> its USDA values per 100 g and portions (D49).

    D54: with how much of it went into your last meal, if any, so the meal
    form can start there.
    """
    out = foods.lookup(normalizer, q)
    if out["food"] is not None:
        with connect() as con:
            out["food"]["last"] = _last_ingredient(con, out["food"]["canonical"])
    return out


@app.get("/api/foods/line")
def read_food_line(q: str = Query(..., min_length=1, max_length=200)):
    """A typed line -> the foods it adds, with their amounts (D61) and dishes (D62).

    "2 Eier, 150 g Reis gekocht" adds two rows at once. A part without a typed
    amount carries last time's, as /api/foods does (D54).
    """
    out = foods.parse(normalizer, q)
    with connect() as con:
        for part in out["parts"]:
            part["food"]["last"] = _last_ingredient(con, part["food"]["canonical"])
    return out


@app.get("/api/foods/{key}")
def food_by_key(key: str):
    """D56: one food by its key, as a logged meal names it, to edit that meal."""
    found = foods.food(key)
    if found is None:
        raise HTTPException(404, f"no values for {key}")
    with connect() as con:
        found["last"] = _last_ingredient(con, key)
    return {"food": found}


def _last_ingredient(con, canonical: str) -> dict | None:
    """D54: the amount of an ingredient in the latest meal that had it."""
    row = con.execute(
        """SELECT mi.grams, mi.cooked, mi.canned FROM meal_ingredients mi JOIN meal_log ml ON ml.id = mi.meal_id
           WHERE mi.canonical = ? ORDER BY ml.logged_at DESC, ml.id DESC, mi.rowid DESC LIMIT 1""",
        (canonical,),
    ).fetchone()
    return {"grams": row["grams"], "cooked": bool(row["cooked"]), "canned": bool(row["canned"])} if row else None


def _with_last(product: dict) -> dict:
    """D54: a product with the grams of it in the latest meal that had it (by barcode)."""
    product = dict(product)
    product["last_grams"] = None
    if product.get("barcode"):
        with connect() as con:
            row = con.execute(
                """SELECT mp.grams FROM meal_products mp JOIN meal_log ml ON ml.id = mp.meal_id
                   WHERE mp.barcode = ? ORDER BY ml.logged_at DESC, ml.id DESC, mp.rowid DESC LIMIT 1""",
                (product["barcode"],),
            ).fetchone()
        product["last_grams"] = row["grams"] if row else None
    return product


class MealIngredient(BaseModel):
    canonical: str = Field(min_length=1, max_length=80)
    grams: float = Field(gt=0, le=5000)
    cooked: bool = False
    canned: bool = False  # D64: from a can, drained


class MealProduct(BaseModel):
    """A scanned or remembered product in a built meal (D51)."""

    name: str = Field(min_length=1, max_length=120)
    barcode: str | None = Field(None, pattern=r"^\d{6,14}$")
    grams: float = Field(gt=0, le=5000)
    calories_100g: float = Field(ge=0, le=900)
    protein_g_100g: float = Field(ge=0, le=100)
    carbs_g_100g: float = Field(ge=0, le=100)
    fat_g_100g: float = Field(ge=0, le=100)
    # D73: a meal typed in as numbers, joined whole ("Add to meal"): how many of
    # it. Its grams are then only a stand-in weight that carries its values.
    meals: float | None = Field(None, gt=0, le=20)


PRODUCT_VALUES = {"calories": "calories_100g", "protein_g": "protein_g_100g",
                  "carbs_g": "carbs_g_100g", "fat_g": "fat_g_100g"}


def _product_totals(products: list[dict]) -> dict[str, float]:
    return {k: sum(p[col] * p["grams"] / 100 for p in products) for k, col in PRODUCT_VALUES.items()}


class MealAdd(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    # Typed in (or filled from a scanned product): the four numbers.
    calories: float | None = Field(None, ge=0, le=5000)
    protein_g: float | None = Field(None, ge=0, le=500)
    carbs_g: float | None = Field(None, ge=0, le=1000)
    fat_g: float | None = Field(None, ge=0, le=500)
    # D49: or built from ingredients; the server works the numbers out.
    ingredients: list[MealIngredient] | None = Field(None, min_length=1, max_length=30)
    # D51: and packaged products, with their own values per 100 g.
    # D73: up to 20, since earlier meals can join one ("Add to meal").
    products: list["MealProduct"] | None = Field(None, min_length=1, max_length=20)
    # D56: when it was eaten, for a meal logged later; now when left out.
    logged_at: str | None = None
    # D73: put together from meals logged before ("Add to meal"); counted, never stored.
    source: Literal["earlier"] | None = None
    # D74: the ingredients are a whole pot that made `pot` portions, of which
    # `portions` were eaten (one when left out); the meal counts that share.
    pot: float | None = Field(None, gt=1, le=50)
    portions: float | None = Field(None, gt=0, le=50)
    # D75: keep the portions not eaten in the kitchen, to eat later.
    keep: bool = False


def _pot_share(body: "MealAdd") -> float:
    """D74: the part of the ingredients eaten: 1 of 4 portions is a quarter."""
    if body.pot is None:
        if body.portions is not None:
            raise HTTPException(422, "Portions eaten need the portions the pot made.")
        return 1.0
    eaten = body.portions if body.portions is not None else 1.0
    if eaten > body.pot:
        raise HTTPException(422, f"That's more than the {body.pot:g} portions the pot made.")
    return eaten / body.pot


def _pot_columns(body: "MealAdd") -> tuple[float | None, float | None]:
    """D74: (pot, portions) as stored: both NULL for an ordinary meal."""
    if body.pot is None:
        return None, None
    return body.pot, body.portions if body.portions is not None else 1.0


def _meal_values(body: "MealAdd") -> tuple[dict, list[dict], list[dict]]:
    """(calories and macros, ingredients, products) for a meal as sent."""
    items = [i.model_dump() for i in body.ingredients or []]
    products = [p.model_dump() for p in body.products or []]
    if items or products:
        try:
            values = foods.totals(items)
        except KeyError as e:
            raise HTTPException(422, f"No nutrition values for {foods.label(e.args[0])}.") from None
        except ValueError as e:
            raise HTTPException(422, f"{foods.label(e.args[0]).capitalize()} has no {e.args[1]} form.") from None
        extra = _product_totals(products)
        # D74: a pot counts the share eaten.
        share = _pot_share(body)
        values = {k: round((values[k] + extra[k]) * share, 1) for k in foods.MACROS}
        if values["calories"] > 5000:
            raise HTTPException(422, "That's over 5,000 kcal for one meal. Check the amounts.")
    else:
        if body.pot is not None:
            raise HTTPException(422, "Only a meal built from ingredients can be a pot.")
        missing = [k for k in foods.MACROS if getattr(body, k) is None]
        if missing:
            raise HTTPException(422, "Give the meal's calories, protein, carbs and fat, or its ingredients.")
        values = {k: getattr(body, k) for k in foods.MACROS}
    return values, items, products


def _write_parts(con, meal_id: int, items: list[dict], products: list[dict]) -> None:
    """A built meal's ingredients and products (D49, D51)."""
    con.executemany(
            "INSERT INTO meal_ingredients (meal_id, canonical, grams, cooked, canned) VALUES (?, ?, ?, ?, ?)",
            [(meal_id, i["canonical"], i["grams"], int(i["cooked"]), int(i.get("canned", False))) for i in items],
        )
    con.executemany(
            """INSERT INTO meal_products (meal_id, name, barcode, grams, calories_100g, protein_g_100g,
                                          carbs_g_100g, fat_g_100g, canonical, meals)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            [(meal_id, p["name"], p["barcode"], p["grams"], p["calories_100g"], p["protein_g_100g"],
              p["carbs_g_100g"], p["fat_g_100g"],
              # D35: a product's name; D73: not a typed meal's, which says nothing sure about what's in it
              packaged(normalizer, p["name"]) if normalizer and not p.get("meals") else None,
              p.get("meals"))
             for p in products],
        )


def _insert_meal(con, body: MealAdd, values: dict, items: list[dict], products: list[dict]) -> int:
    cur = con.execute(
        "INSERT INTO meal_log (name, calories, protein_g, carbs_g, fat_g, logged_at, pot, portions)"
        " VALUES (?, ?, ?, ?, ?, COALESCE(?, datetime('now')), ?, ?)",
        (body.name, *(values[k] for k in foods.MACROS), _logged_at(body.logged_at), *_pot_columns(body)),
    )
    _write_parts(con, cur.lastrowid, items, products)
    return cur.lastrowid


@app.post("/api/meals")
def add_meal(body: MealAdd):
    values, items, products = _meal_values(body)
    if body.keep and body.pot is None:
        raise HTTPException(422, "Only a pot has portions left to keep.")
    leftover = None
    with connect() as con:
        meal_id = _insert_meal(con, body, values, items, products)
        eaten = body.portions if body.portions is not None else 1.0
        if body.keep and body.pot - eaten > 0:
            # D75: the rest of the pot goes into the kitchen, one portion's numbers kept for showing.
            per = {k: round(values[k] / eaten, 1) for k in foods.MACROS}
            leftover = con.execute(
                "INSERT INTO leftovers (name, parts, pot, portions_left, calories, protein_g, carbs_g, fat_g)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (body.name, json.dumps({"ingredients": items, "products": products}), body.pot,
                 body.pot - eaten, *(per[k] for k in foods.MACROS)),
            ).lastrowid
        con.commit()
    stats.event("meal_built" if items or products else "meal_typed")  # how, never what
    if body.source == "earlier":
        stats.event("meal_from_earlier")
    if body.pot is not None:
        stats.event("meal_pot")
    if leftover is not None:
        stats.event("leftover_kept")
    return {"logged": True, "meal_log_id": meal_id, "leftover_id": leftover, **values}


@app.put("/api/meals/{meal_id:int}")
def edit_meal(meal_id: int, body: MealAdd):
    """D56: change a typed or built meal: its name, numbers or ingredients.

    The time stays unless a new one is sent; the rating stays.
    """
    values, items, products = _meal_values(body)
    when = _logged_at(body.logged_at)
    with connect() as con:
        row = con.execute("SELECT recipe_id FROM meal_log WHERE id = ?", (meal_id,)).fetchone()
        if row is None:
            raise HTTPException(404, f"no logged meal {meal_id}")
        if row["recipe_id"] is not None:
            raise HTTPException(422, "A cooked recipe is changed by its servings.")
        con.execute(
            "UPDATE meal_log SET name = ?, calories = ?, protein_g = ?, carbs_g = ?, fat_g = ?,"
            " logged_at = COALESCE(?, logged_at), pot = ?, portions = ? WHERE id = ?",
            (body.name, *(values[k] for k in foods.MACROS), when, *_pot_columns(body), meal_id),
        )
        con.execute("DELETE FROM meal_ingredients WHERE meal_id = ?", (meal_id,))
        con.execute("DELETE FROM meal_products WHERE meal_id = ?", (meal_id,))
        _write_parts(con, meal_id, items, products)
        con.commit()
    return {"edited": meal_id, **values}


class Servings(BaseModel):
    servings: float = Field(gt=0, le=10)


@app.put("/api/meals/{meal_id:int}/servings")
def set_servings(meal_id: int, body: Servings):
    """D56: how much of a cooked recipe was eaten."""
    with connect() as con:
        row = con.execute("SELECT recipe_id FROM meal_log WHERE id = ?", (meal_id,)).fetchone()
        if row is None or row["recipe_id"] is None:
            raise HTTPException(404, f"no cooked recipe logged as {meal_id}")
        con.execute(
            "UPDATE meal_log SET calories = ?, protein_g = ?, carbs_g = ?, fat_g = ?, servings = ? WHERE id = ?",
            (*_scaled(con, row["recipe_id"], body.servings), meal_id),
        )
        con.commit()
    return {"id": meal_id, "servings": body.servings}


RECENT_DAYS = 30  # D50: how far back "Log again" looks; favourites always show


def _name_key(name: str | None) -> str:
    return " ".join((name or "").lower().split())


@app.get("/api/meals/recent")
def recent_meals(limit: int = Query(8, ge=1, le=20)):
    """Meals to log again in one tap (D50): favourites first, then recent ones.

    Typed and built meals only, the latest of each name; a cooked recipe is
    logged again from its page, where "I cooked this" also updates the kitchen.
    """
    with connect() as con:
        favourites = {r[0] for r in con.execute("SELECT name_key FROM favourite_meals")}
        rows = con.execute(
            """SELECT id, name, calories, protein_g, carbs_g, fat_g, pot, portions,
                      julianday('now') - julianday(logged_at) AS age_days
               FROM meal_log
               WHERE recipe_id IS NULL AND name IS NOT NULL
               ORDER BY logged_at DESC, id DESC"""
        ).fetchall()
        latest: dict[str, dict] = {}
        for r in rows:
            key = _name_key(r["name"])
            if key and key not in latest:
                latest[key] = dict(r)
        made_of = _meal_ingredients(con, [m["id"] for m in latest.values()])
    favs = sorted((m for k, m in latest.items() if k in favourites), key=lambda m: _name_key(m["name"]))
    recent = [m for k, m in latest.items() if k not in favourites and m["age_days"] <= RECENT_DAYS]
    out = []
    for m in (favs + recent)[:max(limit, len(favs))]:
        out.append({
            "meal_id": m["id"], "name": m["name"], "favourite": _name_key(m["name"]) in favourites,
            **{k: m[k] for k in foods.MACROS}, "ingredients": made_of.get(m["id"], []),
            "pot": m["pot"], "portions": m["portions"],  # D74
        })
    return {"meals": out}


class Again(BaseModel):
    logged_at: str | None = None  # D56: log it on another day


@app.post("/api/meals/{meal_id:int}/again")
def log_again(meal_id: int, body: Again | None = None):
    """Log a copy of a typed or built meal now, with its ingredients (D50)."""
    with connect() as con:
        m = con.execute(
            "SELECT name, calories, protein_g, carbs_g, fat_g, pot, portions FROM meal_log"
            " WHERE id = ? AND recipe_id IS NULL",
            (meal_id,),
        ).fetchone()
        if m is None:
            raise HTTPException(404, f"no typed or built meal {meal_id}")
        # D74: a pot's next portion is the same share of the same pot.
        cur = con.execute(
            "INSERT INTO meal_log (name, calories, protein_g, carbs_g, fat_g, pot, portions, logged_at)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, COALESCE(?, datetime('now')))",
            (*tuple(m), _logged_at(body.logged_at if body else None)),
        )
        con.execute(
            """INSERT INTO meal_ingredients (meal_id, canonical, grams, cooked, canned)
               SELECT ?, canonical, grams, cooked, canned FROM meal_ingredients WHERE meal_id = ? ORDER BY rowid""",
            (cur.lastrowid, meal_id),
        )
        con.execute(
            """INSERT INTO meal_products (meal_id, name, barcode, grams, calories_100g, protein_g_100g,
                                          carbs_g_100g, fat_g_100g, canonical, meals)
               SELECT ?, name, barcode, grams, calories_100g, protein_g_100g, carbs_g_100g, fat_g_100g,
                      canonical, meals
               FROM meal_products WHERE meal_id = ? ORDER BY rowid""",
            (cur.lastrowid, meal_id),
        )
        con.commit()
    stats.event("meal_again")
    return {"logged": True, "meal_log_id": cur.lastrowid}


class Favourite(BaseModel):
    favourite: bool


@app.put("/api/meals/{meal_id:int}/favourite")
def set_favourite(meal_id: int, body: Favourite):
    """Keep a meal at the top of "Log again", or stop (D50). By name, not by entry."""
    with connect() as con:
        row = con.execute("SELECT name FROM meal_log WHERE id = ?", (meal_id,)).fetchone()
        if row is None or not _name_key(row["name"]):
            raise HTTPException(404, f"no named meal {meal_id}")
        key = _name_key(row["name"])
        if body.favourite:
            con.execute("INSERT OR IGNORE INTO favourite_meals (name_key) VALUES (?)", (key,))
        else:
            con.execute("DELETE FROM favourite_meals WHERE name_key = ?", (key,))
        con.commit()
    return {"name": row["name"], "favourite": body.favourite}


class MealRating(BaseModel):
    liked: bool | None  # None clears the rating


@app.post("/api/meals/{meal_id:int}/rate")
def rate_meal(meal_id: int, body: MealRating):
    """Like/dislike a logged meal; feeds the taste vector (D6 weights)."""
    with connect() as con:
        cur = con.execute(
            "UPDATE meal_log SET liked = ? WHERE id = ?",
            (None if body.liked is None else int(body.liked), meal_id),
        )
        con.commit()
    if cur.rowcount == 0:
        raise HTTPException(404, f"no logged meal {meal_id}")
    stats.event({True: "rated_liked", False: "rated_not_for_me", None: "rating_cleared"}[body.liked])
    return {"id": meal_id, "liked": body.liked}


@app.delete("/api/meals/{meal_id:int}")
def delete_meal(meal_id: int):
    """Delete a logged meal; the answer carries everything about it, so the app
    can offer Undo (D56) by sending it back to /api/meals/restore."""
    with connect() as con:
        row = con.execute(
            "SELECT recipe_id, logged_at, liked, name, calories, protein_g, carbs_g, fat_g, servings, pot, portions"
            " FROM meal_log WHERE id = ?", (meal_id,),
        ).fetchone()
        if row is None:
            raise HTTPException(404, f"no logged meal {meal_id}")
        snapshot = dict(row)
        snapshot["ingredients"] = [dict(r) for r in con.execute(
            "SELECT canonical, grams, cooked, canned FROM meal_ingredients WHERE meal_id = ? ORDER BY rowid", (meal_id,))]
        snapshot["products"] = [dict(r) for r in con.execute(
            "SELECT name, barcode, grams, calories_100g, protein_g_100g, carbs_g_100g, fat_g_100g, canonical, meals"
            " FROM meal_products WHERE meal_id = ? ORDER BY rowid", (meal_id,))]
        con.execute("DELETE FROM meal_log WHERE id = ?", (meal_id,))
        con.execute("DELETE FROM meal_ingredients WHERE meal_id = ?", (meal_id,))
        con.execute("DELETE FROM meal_products WHERE meal_id = ?", (meal_id,))
        con.commit()
    return {"deleted": meal_id, "meal": snapshot}


class Snapshot(BaseModel):
    """D56: a deleted meal, as DELETE /api/meals/{id} gave it, to put back."""

    recipe_id: int | None = None
    logged_at: str = Field(pattern=r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}$")
    liked: int | None = Field(None, ge=0, le=1)
    name: str | None = Field(None, max_length=200)
    calories: float | None = Field(None, ge=0, le=5000)
    protein_g: float | None = Field(None, ge=0, le=500)
    carbs_g: float | None = Field(None, ge=0, le=1000)
    fat_g: float | None = Field(None, ge=0, le=500)
    servings: float | None = Field(None, gt=0, le=10)
    pot: float | None = Field(None, gt=1, le=50)  # D74
    portions: float | None = Field(None, gt=0, le=50)
    ingredients: list[dict] = Field(default_factory=list, max_length=30)
    products: list[dict] = Field(default_factory=list, max_length=20)


@app.post("/api/meals/restore")
def restore_meal(body: Snapshot):
    """D56: Undo a delete: the meal back as it was, at its own time."""
    items = [MealIngredient(**i).model_dump() for i in body.ingredients]
    products = [MealProduct(**p).model_dump() for p in body.products]
    with connect() as con:
        cur = con.execute(
            "INSERT INTO meal_log (recipe_id, logged_at, liked, name, calories, protein_g, carbs_g, fat_g, servings,"
            " pot, portions) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (body.recipe_id, body.logged_at, body.liked, body.name, body.calories, body.protein_g,
             body.carbs_g, body.fat_g, body.servings, body.pot, body.portions),
        )
        _write_parts(con, cur.lastrowid, items, products)
        con.commit()
    return {"restored": cur.lastrowid}


# D75: what's left of pots cooked ahead.

FRIDGE_DAYS = 4  # cooked food keeps three to four days in the fridge


def _leftover(row) -> dict:
    days = row["fridge_days"]
    return {
        "id": row["id"], "name": row["name"], "pot": row["pot"], "portions_left": row["portions_left"],
        "made_at": row["made_at"], "frozen": bool(row["frozen"]),
        "fridge_days": None if row["frozen"] else round(days, 1),
        # In the fridge longer than cooked food keeps: ask, don't offer it as dinner.
        "stale": not row["frozen"] and days > FRIDGE_DAYS,
        "per_portion": {k: row[k] for k in foods.MACROS},
    }


def _leftovers(con) -> list[dict]:
    # Rows eaten up stay a day, so Undo can put a portion back; then they go.
    con.execute("DELETE FROM leftovers WHERE portions_left <= 0 AND julianday('now') - julianday(made_at) > 1")
    rows = con.execute(
        """SELECT *, julianday('now') - julianday(fridge_since) AS fridge_days FROM leftovers
           WHERE portions_left > 0 ORDER BY frozen, made_at, id"""
    ).fetchall()
    return [_leftover(r) for r in rows]


@app.get("/api/leftovers")
def get_leftovers():
    """D75: cooked portions in the kitchen: fridge first, oldest first."""
    with connect() as con:
        items = _leftovers(con)
        con.commit()
    return {"items": items, "fridge_days": FRIDGE_DAYS}


class Eat(BaseModel):
    portions: float = Field(1, gt=0, le=50)
    logged_at: str | None = None  # D56: on another day


@app.post("/api/leftovers/{leftover_id:int}/eat")
def eat_leftover(leftover_id: int, body: Eat | None = None):
    """D75: log a portion of a pot in the kitchen, as a share of the same pot (D74), and count it down."""
    body = body or Eat()
    with connect() as con:
        row = con.execute("SELECT * FROM leftovers WHERE id = ?", (leftover_id,)).fetchone()
        if row is None or row["portions_left"] <= 0:
            raise HTTPException(404, f"no portions left of {leftover_id}")
        if body.portions > row["portions_left"] + 1e-9:
            raise HTTPException(422, f"Only {row['portions_left']:g} left.")
        parts = json.loads(row["parts"])
        meal = MealAdd(name=row["name"], ingredients=parts["ingredients"] or None, products=parts["products"] or None,
                       pot=row["pot"], portions=body.portions, logged_at=body.logged_at)
        values, items, products = _meal_values(meal)
        meal_id = _insert_meal(con, meal, values, items, products)
        left = round(row["portions_left"] - body.portions, 3)
        con.execute("UPDATE leftovers SET portions_left = ? WHERE id = ?", (left, leftover_id))
        con.commit()
    stats.event("leftover_eaten")
    return {"meal_log_id": meal_id, "portions_left": left, **values}


class LeftoverChange(BaseModel):
    portions_left: float | None = Field(None, ge=0, le=50)  # Undo, or a correction
    frozen: bool | None = None


@app.put("/api/leftovers/{leftover_id:int}")
def change_leftover(leftover_id: int, body: LeftoverChange):
    """D75: put a portion back (Undo), or move it to the freezer and back.

    Out of the freezer, the fridge days start again.
    """
    with connect() as con:
        row = con.execute("SELECT frozen FROM leftovers WHERE id = ?", (leftover_id,)).fetchone()
        if row is None:
            raise HTTPException(404, f"no leftover {leftover_id}")
        if body.portions_left is not None:
            con.execute("UPDATE leftovers SET portions_left = ? WHERE id = ?", (body.portions_left, leftover_id))
        if body.frozen is not None and body.frozen != bool(row["frozen"]):
            con.execute(
                "UPDATE leftovers SET frozen = ?, fridge_since = CASE WHEN ? THEN fridge_since ELSE datetime('now') END"
                " WHERE id = ?",
                (int(body.frozen), int(body.frozen), leftover_id),
            )
            if body.frozen:
                stats.event("leftover_frozen")
        con.commit()
        items = _leftovers(con)
        con.commit()
    return {"items": items}


@app.delete("/api/leftovers/{leftover_id:int}")
def remove_leftover(leftover_id: int):
    """D75: it's gone (eaten without logging, or thrown away)."""
    with connect() as con:
        if con.execute("DELETE FROM leftovers WHERE id = ?", (leftover_id,)).rowcount == 0:
            raise HTTPException(404, f"no leftover {leftover_id}")
        con.commit()
        items = _leftovers(con)
        con.commit()
    stats.event("leftover_gone")
    return {"items": items}


@app.get("/api/day")
def day_summary(
    date: str | None = Query(None, pattern=r"^\d{4}-\d{2}-\d{2}$"),
    tz: int | None = Query(None, ge=-840, le=840),
):
    """One day's meals and macro totals vs the profile targets.

    With tz (the client's UTC offset in minutes, D40) days are the user's local
    days; without it, the server's.
    """
    if tz is None:
        day = date or _date.today().isoformat()
        shift = "localtime"
    else:
        day = date or progress.local_today(tz).isoformat()
        shift = f"{tz:+d} minutes"
    with connect() as con:
        rows = con.execute(
            """SELECT ml.id, ml.recipe_id, ml.logged_at, ml.liked,
                      COALESCE(ml.name, r.name)           AS name,
                      COALESCE(ml.calories, r.calories)   AS calories,
                      COALESCE(ml.protein_g, r.protein_g) AS protein_g,
                      COALESCE(ml.carbs_g, r.carbs_g)     AS carbs_g,
                      COALESCE(ml.fat_g, r.fat_g)         AS fat_g,
                      ml.servings, ml.pot, ml.portions
               FROM meal_log ml
               LEFT JOIN recipes r ON r.id = ml.recipe_id
               WHERE date(ml.logged_at, ?) = ?
               ORDER BY ml.logged_at""",
            (shift, day),
        ).fetchall()
        profile, est = adaptive.profile_with_burn(con, tz or 0)
        made_of = _meal_ingredients(con, [r["id"] for r in rows])
    meals = [dict(r) for r in rows]
    for m in meals:
        m["ingredients"] = made_of.get(m["id"], [])
        # D49: cooked recipes teach the feed, and so do meals built from
        # two or more real ingredients; typed numbers and single foods don't.
        m["rateable"] = m["recipe_id"] is not None or foods.teaches_taste(
            [i["canonical"] for i in m["ingredients"] if i["canonical"]]
        )
        # D60: why not, said for this meal ("Skyr, banana" isn't a single food).
        m["rate_note"] = None if m["rateable"] else foods.rate_note(m["ingredients"])
    totals = {
        key: round(sum(m[key] or 0.0 for m in meals), 1)
        for key in ("calories", "protein_g", "carbs_g", "fat_g")
    }
    return {
        "date": day,
        "meals": meals,
        "totals": totals,
        "targets": goals.targets(profile) if profile is not None else None,
        "plan": goals.plan(profile) if profile is not None else None,  # D39
        "burn": est,  # D45
    }


def _meal_ingredients(con, ids: list[int]) -> dict[int, list[dict]]:
    if not ids:
        return {}
    out: dict[int, list[dict]] = {}
    for r in con.execute(
        f"SELECT meal_id, canonical, grams, cooked, canned FROM meal_ingredients"
        f" WHERE meal_id IN ({','.join('?' * len(ids))}) ORDER BY rowid",
        ids,
    ):
        out.setdefault(r["meal_id"], []).append(
            {"canonical": r["canonical"], "name": foods.label(r["canonical"]),
             "grams": r["grams"], "cooked": bool(r["cooked"]), "canned": bool(r["canned"]), "product": False}
        )
    for r in con.execute(  # D51: products after the USDA ingredients
        f"SELECT meal_id, name, barcode, grams, canonical, calories_100g, protein_g_100g, carbs_g_100g,"
        f" fat_g_100g, meals FROM meal_products"
        f" WHERE meal_id IN ({','.join('?' * len(ids))}) ORDER BY rowid",
        ids,
    ):
        out.setdefault(r["meal_id"], []).append(
            {"canonical": r["canonical"], "name": r["name"], "grams": r["grams"],
             "cooked": False, "canned": False, "product": True,
             # D56: what's needed to edit the meal again
             "barcode": r["barcode"], "meals": r["meals"], "per_100g": {
                 "calories": r["calories_100g"], "protein_g": r["protein_g_100g"],
                 "carbs_g": r["carbs_g_100g"], "fat_g": r["fat_g_100g"]}}
        )
    return out


@app.get("/api/progress")
def progress_summary(tz: int = Query(0, ge=-840, le=840)):
    """Streak, the last 14 days by class, 30-day totals and the weekly recap (D40).

    tz is the client's offset from UTC in minutes (east positive), so days are
    the user's local days.
    """
    with connect() as con:
        profile, _ = adaptive.profile_with_burn(con, tz)
        if profile is None:
            return {"progress": None}
        return {"progress": progress.summary(con, profile, tz)}


class DayCheck(BaseModel):
    complete: bool | None  # None clears the answer


@app.put("/api/days/{day}/check")
def check_day(day: str, body: DayCheck):
    """D42: the user's answer to "Done for today?" for one local day."""
    try:
        _date.fromisoformat(day)
    except ValueError:
        raise HTTPException(422, "day must be YYYY-MM-DD")
    with connect() as con:
        progress.set_check(con, day, body.complete)
    return {"day": day, "complete": body.complete}


class WeighIn(BaseModel):
    weight_kg: float = Field(ge=35, le=250)


@app.get("/api/weight")
def weight_summary(tz: int = Query(0, ge=-840, le=840)):
    """D41: weigh-ins, the trend and the projection to the goal weight."""
    with connect() as con:
        profile, est = adaptive.profile_with_burn(con, tz)
        return weight.summary(con, profile, tz) | {"burn": est}


@app.post("/api/weight")
def log_weight(body: WeighIn, tz: int = Query(0, ge=-840, le=840)):
    with connect() as con:
        weight.log(con, body.weight_kg)
        profile, est = adaptive.profile_with_burn(con, tz)
        return weight.summary(con, profile, tz) | {"burn": est}


@app.delete("/api/weight/{entry_id}")
def delete_weight(entry_id: int, tz: int = Query(0, ge=-840, le=840)):
    with connect() as con:
        weight.remove(con, entry_id)
        profile, est = adaptive.profile_with_burn(con, tz)
        return weight.summary(con, profile, tz) | {"burn": est}


@app.get("/api/nutrition/barcode/{code}")
def barcode_lookup(code: str):
    """Barcode -> per-100g nutrition (products cache, then Open Food Facts)."""
    if not code.isdigit() or not 6 <= len(code) <= 14:
        raise HTTPException(422, f"not a barcode: {code!r}")
    stats.event("barcode_lookup")
    with connect() as con:
        try:
            product = nutrition.lookup(con, code)
        except nutrition.OffUnavailable as e:
            raise HTTPException(502, f"Open Food Facts unreachable: {e}")
    if product is None:
        raise HTTPException(404, f"barcode {code} not on Open Food Facts")
    return {"product": _with_last(product)}


def _barcode(code: str | None) -> str | None:
    return code if code and code.isdigit() and 6 <= len(code) <= 14 else None


@app.post("/api/nutrition/scan")
async def nutrition_scan(photo: UploadFile = File(...), barcode: str | None = Form(None)):
    """Product photo -> per-100g nutrition.

    Haiku reads the printed barcode digits and/or the Nährwerttabelle; a
    resolvable barcode makes Open Food Facts authoritative (and caches the
    product), otherwise the label values are returned as proposals.

    `barcode` (D48) is one the app already has for this product: read on the
    device from this photo, or from an earlier photo of the same pack whose
    product isn't on Open Food Facts. A label read without a barcode of its
    own is returned under it, so the app can remember it.
    """
    if demo.enabled():
        stats.event("label_scan_tried")
        if not demo.scanning():
            raise HTTPException(403, demo.SCAN_OFF)
        refused = demo.take_scan(demo.current_id.get())  # D38: caps
        if refused:
            raise HTTPException(429, refused)
    from . import vision

    raw = await _read_photo(photo)
    try:
        scan = vision.extract_product(raw, photo.content_type)
    except Exception as e:
        raise HTTPException(502, f"vision extraction failed: {e}")

    code = _barcode(scan.barcode) or _barcode(barcode)
    product, off_down = None, False
    if code:
        with connect() as con:
            try:
                product = nutrition.lookup(con, code)
            except nutrition.OffUnavailable:
                off_down = True  # fall back to the label values
    if product is not None and product["calories_100g"] is not None:
        return {"product": _with_last(product)}

    label = scan.per_100g
    if label is None or label.calories is None:
        raise HTTPException(404, {"message": _no_label_message(code, product, off_down), "barcode": code})
    return {
        "product": _with_last({
            "barcode": code,
            "name": scan.product_name or (product or {}).get("name"),
            "brand": (product or {}).get("brand"),
            "calories_100g": label.calories,
            "protein_g_100g": label.protein_g,
            "carbs_g_100g": label.carbs_g,
            "fat_g_100g": label.fat_g,
            "source": "label",
            # D36: a sum check, shown as a warning before the values are used
            "check": nutrition.label_check(label.calories, label.protein_g, label.carbs_g, label.fat_g),
        })
    }


def _no_label_message(code: str | None, product: dict | None, off_down: bool) -> str:
    """D48: say what was found, and what photo to take next."""
    table = "Take a photo of the nutrition table instead (often on the back or side of the pack)"
    if code is None:
        return (
            "Couldn't find a barcode or a nutrition table in the photo. "
            "Try a closer, sharper photo of either one."
        )
    if off_down:
        return f"Found barcode {code}, but Open Food Facts couldn't be reached just now. {table}."
    if product is not None:
        return f"Found barcode {code} on Open Food Facts, but it has no nutrition values there yet. {table}."
    return f"Found barcode {code}, but this product isn't on Open Food Facts yet. {table}."


class SavedProduct(BaseModel):
    """D48: label values the user chose to use, kept under the product's barcode."""

    barcode: str = Field(pattern=r"^\d{6,14}$")
    name: str | None = Field(None, max_length=200)
    calories_100g: float = Field(ge=0, le=900)
    protein_g_100g: float = Field(ge=0, le=100)
    carbs_g_100g: float = Field(ge=0, le=100)
    fat_g_100g: float = Field(ge=0, le=100)


@app.post("/api/nutrition/products")
def save_product(body: SavedProduct):
    """Remember a label reading for a barcode Open Food Facts doesn't have (D48)."""
    product = body.model_dump() | {"brand": None, "source": "saved"}
    with connect() as con:
        existing = nutrition.cached(con, body.barcode)
        if existing is not None and existing["source"] == "openfoodfacts" and existing["calories_100g"] is not None:
            raise HTTPException(409, "this barcode is already on Open Food Facts")
        nutrition.cache(con, product)
    return {"product": product}


@app.delete("/api/nutrition/products/{code}")
def forget_product(code: str):
    """Forget a remembered label reading (D48); Open Food Facts entries stay."""
    with connect() as con:
        con.execute("DELETE FROM products WHERE barcode = ? AND source = 'saved'", (code,))
        con.commit()
    return {"forgotten": code}


@app.get("/api/taste")
def taste_profile():
    """The learned taste profile: meal count + defining ingredients."""
    with connect() as con:
        vec, n_meals = taste.taste_vector(con)
    if vec is None:
        return {"meals_logged": 0, "profile": []}
    return {"meals_logged": n_meals, "profile": taste.nearest_ingredients(vec)}


def _recipe_names(ids: list[int]) -> dict[int, str]:
    if not ids:
        return {}
    with connect() as con:
        rows = con.execute(
            f"SELECT id, name FROM recipes WHERE id IN ({','.join('?' * len(ids))})", ids
        ).fetchall()
    return {r["id"]: r["name"] for r in rows}


@app.get("/stats.json")
def usage_stats_json():
    """Public, anonymous usage totals of the demo (D33)."""
    if not stats.enabled():
        raise HTTPException(404, "usage totals are only kept on the public demo")
    return stats.summary(_recipe_names)


@app.get("/stats", response_class=HTMLResponse)
def usage_stats_page():
    if not stats.enabled():
        raise HTTPException(404, "usage totals are only kept on the public demo")
    return stats_page.render(stats.summary(_recipe_names))


# Serve the built frontend when it exists, so one port (and one tunnel)
# carries the whole app. Mounted last: API routes above take precedence.
_DIST = Path(__file__).resolve().parents[2] / "frontend" / "dist"
if _DIST.is_dir():
    app.mount("/", StaticFiles(directory=_DIST, html=True), name="app")
