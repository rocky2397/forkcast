"""Forkcast API — Phase 1 scaffold.

Run from the repo root:
  .venv/bin/uvicorn app.main:app --app-dir backend --reload
"""

from contextlib import asynccontextmanager
from datetime import date as _date

from fastapi import FastAPI, File, HTTPException, Query, UploadFile
from pydantic import BaseModel, Field
from typing import Literal

from . import embeddings, goals, recipes, taste
from .db import connect
from .normalize import Normalizer

normalizer: Normalizer | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global normalizer
    normalizer = Normalizer(embeddings.vocabulary())  # also warms the cooc model
    yield


app = FastAPI(title="Forkcast API", lifespan=lifespan)

# Single-user app on a private LAN; permissive CORS is acceptable here and
# lets the phone reach the API during development (revisit with auth).
from fastapi.middleware.cors import CORSMiddleware  # noqa: E402

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health():
    return {"status": "ok", "vocab_size": len(embeddings.vocabulary())}


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
            {"raw": i["raw"], "canonical": i["canonical"], "in_inventory": bool(i["in_inventory"])}
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
    return {"count": len(results), "personalized": taste_vec is not None, "recipes": results}


@app.post("/api/vision/scan")
async def vision_scan(photo: UploadFile = File(...)):
    """Groceries photo -> proposed items (nothing committed; client confirms)."""
    from . import vision

    if photo.content_type not in ("image/jpeg", "image/png", "image/webp", "image/gif"):
        raise HTTPException(415, f"unsupported image type: {photo.content_type}")
    raw = await photo.read()
    if len(raw) > 20_000_000:
        raise HTTPException(413, "image too large")
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
            """SELECT ml.id, ml.recipe_id, ml.logged_at,
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


@app.get("/api/taste")
def taste_profile():
    """The learned taste profile: meal count + defining ingredients."""
    with connect() as con:
        vec, n_meals = taste.taste_vector(con)
    if vec is None:
        return {"meals_logged": 0, "profile": []}
    return {"meals_logged": n_meals, "profile": taste.nearest_ingredients(vec)}
