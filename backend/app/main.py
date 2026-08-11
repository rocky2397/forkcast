"""Forkcast API — Phase 1 scaffold.

Run from the repo root:
  .venv/bin/uvicorn app.main:app --app-dir backend --reload
"""

from contextlib import asynccontextmanager
from datetime import date as _date
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, Query, Request, Response, UploadFile
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from typing import Literal

from . import auth, embeddings, goals, nutrition, recipes, substitutions, taste
from .db import connect
from .normalize import Normalizer

normalizer: Normalizer | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global normalizer
    normalizer = Normalizer(embeddings.vocabulary())  # also warms the cooc model
    yield


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
    return {"status": "ok", "vocab_size": len(embeddings.vocabulary())}


class Login(BaseModel):
    password: str


@app.get("/api/session")
def session(request: Request):
    """Whether a password is configured, and whether this caller has passed it."""
    return {
        "required": auth.required(),
        "authenticated": not auth.required()
        or auth.valid_token(request.cookies.get(auth.COOKIE)),
    }


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
    return {"items": [dict(r) for r in rows]}


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
    return {"added": added, "unknown": unknown}


@app.delete("/api/inventory/{name}")
def remove_inventory(name: str):
    canonical = normalizer.match(name) or name
    with connect() as con:
        cur = con.execute("DELETE FROM inventory WHERE canonical = ?", (canonical,))
        con.commit()
    if cur.rowcount == 0:
        raise HTTPException(404, f"not in inventory: {name!r}")
    return {"removed": canonical}


@app.get("/api/recipes/{recipe_id:int}")
def recipe_detail(recipe_id: int):
    import json as _json

    with connect() as con:
        r = con.execute("SELECT * FROM recipes WHERE id = ?", (recipe_id,)).fetchone()
        if r is None:
            raise HTTPException(404, f"no recipe {recipe_id}")
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
                "sub": (
                    substitutions.suggest(i["canonical"], cands)
                    if i["canonical"] and not i["in_inventory"]
                    else None
                ),
            }
            for i in ings
        ],
    }


@app.post("/api/recipes/{recipe_id:int}/cooked")
def log_cooked(recipe_id: int):
    with connect() as con:
        if con.execute("SELECT 1 FROM recipes WHERE id = ?", (recipe_id,)).fetchone() is None:
            raise HTTPException(404, f"no recipe {recipe_id}")
        cur = con.execute("INSERT INTO meal_log (recipe_id) VALUES (?)", (recipe_id,))
        con.commit()
    return {"logged": True, "meal_log_id": cur.lastrowid, "recipe_id": recipe_id}


@app.get("/api/recipes/cookable")
def cookable_recipes(
    max_missing: int = Query(0, ge=0, le=3),
    assume_staples: bool = True,
    limit: int = Query(20, ge=1, le=100),
):
    """Recipes you can cook now (max_missing=0) or almost (1-3 missing).

    When cooks have been logged, results are re-ranked by taste similarity
    within each missing-count group (fewest-missing always wins first).
    """
    with connect() as con:
        taste_vec, n_meals = taste.taste_vector(con)
        pool = limit if taste_vec is None else min(limit * 8, 300)
        results = recipes.cookable(
            con, max_missing=max_missing, assume_staples=assume_staples, limit=pool
        )
        if taste_vec is not None:
            scores = taste.score_recipes(con, [r["id"] for r in results], taste_vec)
            for r in results:
                r["taste_sim"] = round(scores.get(r["id"], 0.0), 3)
            results.sort(key=lambda r: (r["ingredients_missing"], -r["taste_sim"]))
            results = results[:limit]
        _annotate_subs(con, results)
    return {"count": len(results), "personalized": taste_vec is not None, "recipes": results}


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
            "canonical": normalizer.match(item.name),
        })
    return {"proposals": proposals}


class ProfileIn(BaseModel):
    sex: Literal["m", "f"]
    age: int = Field(ge=14, le=100)
    height_cm: float = Field(ge=120, le=230)
    weight_kg: float = Field(ge=35, le=250)
    activity: Literal["sedentary", "light", "moderate", "active", "very_active"]
    goal: Literal["cut", "maintain", "bulk"]


@app.get("/api/profile")
def get_profile():
    with connect() as con:
        row = con.execute("SELECT * FROM profile WHERE id = 1").fetchone()
    if row is None:
        return {"profile": None, "targets": None}
    return {"profile": dict(row), "targets": goals.targets(row)}


@app.put("/api/profile")
def put_profile(body: ProfileIn):
    with connect() as con:
        con.execute(
            """INSERT INTO profile (id, sex, age, height_cm, weight_kg, activity, goal, updated_at)
               VALUES (1, ?, ?, ?, ?, ?, ?, datetime('now'))
               ON CONFLICT(id) DO UPDATE SET
                 sex = excluded.sex, age = excluded.age,
                 height_cm = excluded.height_cm, weight_kg = excluded.weight_kg,
                 activity = excluded.activity, goal = excluded.goal,
                 updated_at = excluded.updated_at""",
            (body.sex, body.age, body.height_cm, body.weight_kg, body.activity, body.goal),
        )
        con.commit()
    return {"profile": body.model_dump(), "targets": goals.targets(body.model_dump())}


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
def day_summary(date: str | None = Query(None, pattern=r"^\d{4}-\d{2}-\d{2}$")):
    """One day's meals and macro totals vs the profile targets."""
    day = date or _date.today().isoformat()
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
               WHERE date(ml.logged_at, 'localtime') = ?
               ORDER BY ml.logged_at""",
            (day,),
        ).fetchall()
        profile = con.execute("SELECT * FROM profile WHERE id = 1").fetchone()
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
    }


@app.get("/api/nutrition/barcode/{code}")
def barcode_lookup(code: str):
    """Barcode -> per-100g nutrition (products cache, then Open Food Facts)."""
    if not code.isdigit() or not 6 <= len(code) <= 14:
        raise HTTPException(422, f"not a barcode: {code!r}")
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


# Serve the built frontend when it exists, so one port (and one tunnel)
# carries the whole app. Mounted last: API routes above take precedence.
_DIST = Path(__file__).resolve().parents[2] / "frontend" / "dist"
if _DIST.is_dir():
    app.mount("/", StaticFiles(directory=_DIST, html=True), name="app")
