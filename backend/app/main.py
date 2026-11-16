"""Forkcast API — Phase 1 scaffold.

Run from the repo root:
  .venv/bin/uvicorn app.main:app --app-dir backend --reload
"""

import asyncio
import os
import time
from contextlib import asynccontextmanager, suppress
from datetime import date as _date
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, Query, Request, Response, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.concurrency import run_in_threadpool
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from typing import Literal

from . import adaptive, auth, demo, embeddings, goals, nutrition, progress, recipes, shopping, stats, stats_page, substitutions, taste, weight
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
    items: list[str]


@app.get("/api/inventory")
def get_inventory():
    with connect() as con:
        rows = con.execute("SELECT canonical, added_at FROM inventory ORDER BY canonical").fetchall()
    # family: the food class (D28), so the kitchen screen can group and colour items
    return {"items": [{**dict(r), "family": NAME_TO_CLASS.get(r["canonical"])} for r in rows]}


@app.post("/api/inventory")
def add_inventory(body: InventoryAdd):
    added, unknown = [], []
    with connect() as con:
        for raw in body.items:
            canonical = normalizer.match(raw)
            if canonical is None:
                unknown.append(raw)
                continue
            con.execute("INSERT OR IGNORE INTO inventory (canonical) VALUES (?)", (canonical,))
            added.append(canonical)
        con.commit()
    for canonical in added:
        stats.event("ingredient_added", item=canonical, stage="added")
    # D46: "Did you mean…?" for what wasn't recognised (never counted or stored).
    suggestions = {raw: normalizer.suggest(raw) for raw in unknown}
    return {"added": added, "unknown": unknown, "suggestions": {k: v for k, v in suggestions.items() if v}}


@app.delete("/api/inventory/{name}")
def remove_inventory(name: str):
    canonical = normalizer.match(name) or name
    with connect() as con:
        cur = con.execute("DELETE FROM inventory WHERE canonical = ?", (canonical,))
        con.commit()
    if cur.rowcount == 0:
        raise HTTPException(404, f"not in inventory: {name!r}")
    stats.event("ingredient_removed")
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
                "sub": (
                    substitutions.suggest(i["canonical"], cands)
                    if i["canonical"] and not i["in_inventory"]
                    else None
                ),
            }
            for i in ings
        ],
    }


class CookedIn(BaseModel):
    used_up: list[str] = Field(default_factory=list, max_length=50)


@app.post("/api/recipes/{recipe_id:int}/cooked")
def log_cooked(recipe_id: int, body: CookedIn | None = None):
    """Log a cook; optionally deplete inventory items the cook used up.

    used_up entries not currently in the inventory are ignored, so a stale
    checklist (item already removed on another device) can't fail the log.
    """
    used_up = body.used_up if body else []
    with connect() as con:
        if con.execute("SELECT 1 FROM recipes WHERE id = ?", (recipe_id,)).fetchone() is None:
            raise HTTPException(404, f"no recipe {recipe_id}")
        stats.event("recipe_cooked", item=recipe_id, stage="cooked")
        cur = con.execute("INSERT INTO meal_log (recipe_id) VALUES (?)", (recipe_id,))
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
            results = results[:limit]
        if profile is not None:
            _annotate_like_your(con, results, matches)
        _annotate_subs(con, results)
        _annotate_signature(con, results)
    return {
        "count": len(results),
        "personalized": profile is not None,
        "macro_focus": budget["focus"] if budget else None,
        "recipes": results,
    }


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
        items, truncated = shopping.suggest(
            con, profile=profile, basket_size=basket, max_missing=max_missing
        )
    return {
        "personalized": profile is not None,
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


def _annotate_like_your(con, results: list[dict], matches: dict) -> None:
    """Name the cooked dish a recipe is closest to, when it is close (D31)."""
    named = {rid: d for rid, (_, d) in matches.items() if d is not None}
    if not named:
        return
    ids = sorted(set(named.values()))
    names = dict(con.execute(
        f"SELECT id, name FROM recipes WHERE id IN ({','.join('?' * len(ids))})", ids
    ).fetchall())
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


@app.post("/api/vision/scan")
async def vision_scan(photo: UploadFile = File(...)):
    """Groceries photo -> proposed items (nothing committed; client confirms)."""
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
    proposals = []
    for item in result.items:
        proposals.append({
            "seen": item.name,
            "quantity": item.quantity,
            "confidence": item.confidence,
            "canonical": packaged(normalizer, item.name),  # D35: read off a product
        })
    return {"proposals": proposals}


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
def put_profile(body: ProfileIn, tz: int = Query(0, ge=-840, le=840)):
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
    stats.event("profile_saved")  # that it changed, never the values
    return {"profile": adaptive.public(profile), "targets": goals.targets(profile),
            "plan": goals.plan(profile), "burn": est}


class MealAdd(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    calories: float = Field(ge=0, le=5000)
    protein_g: float = Field(ge=0, le=500)
    carbs_g: float = Field(ge=0, le=1000)
    fat_g: float = Field(ge=0, le=500)


@app.post("/api/meals")
def add_meal(body: MealAdd):
    with connect() as con:
        cur = con.execute(
            "INSERT INTO meal_log (name, calories, protein_g, carbs_g, fat_g) VALUES (?, ?, ?, ?, ?)",
            (body.name, body.calories, body.protein_g, body.carbs_g, body.fat_g),
        )
        con.commit()
    stats.event("meal_typed")  # that one was typed, never what
    return {"logged": True, "meal_log_id": cur.lastrowid}


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
    with connect() as con:
        cur = con.execute("DELETE FROM meal_log WHERE id = ?", (meal_id,))
        con.commit()
    if cur.rowcount == 0:
        raise HTTPException(404, f"no logged meal {meal_id}")
    return {"deleted": meal_id}


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
                      COALESCE(ml.fat_g, r.fat_g)         AS fat_g
               FROM meal_log ml
               LEFT JOIN recipes r ON r.id = ml.recipe_id
               WHERE date(ml.logged_at, ?) = ?
               ORDER BY ml.logged_at""",
            (shift, day),
        ).fetchall()
        profile, est = adaptive.profile_with_burn(con, tz or 0)
    meals = [dict(r) for r in rows]
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
    return {"product": product}


@app.post("/api/nutrition/scan")
async def nutrition_scan(photo: UploadFile = File(...)):
    """Product photo -> per-100g nutrition.

    Haiku reads the printed barcode digits and/or the Nährwerttabelle; a
    resolvable barcode makes Open Food Facts authoritative (and caches the
    product), otherwise the label values are returned as proposals.
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

    product = None
    if scan.barcode and scan.barcode.isdigit() and 6 <= len(scan.barcode) <= 14:
        with connect() as con:
            try:
                product = nutrition.lookup(con, scan.barcode)
            except nutrition.OffUnavailable:
                product = None  # fall back to the label values
    if product is not None and product["calories_100g"] is not None:
        return {"product": product}

    label = scan.per_100g
    if label is None or label.calories is None:
        raise HTTPException(
            404, "could not read a barcode or nutrition table from the photo"
        )
    return {
        "product": {
            "barcode": scan.barcode,
            "name": scan.product_name,
            "brand": None,
            "calories_100g": label.calories,
            "protein_g_100g": label.protein_g,
            "carbs_g_100g": label.carbs_g,
            "fat_g_100g": label.fat_g,
            "source": "label",
            # D36: a sum check, shown as a warning before the values are used
            "check": nutrition.label_check(label.calories, label.protein_g, label.carbs_g, label.fat_g),
        }
    }


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
