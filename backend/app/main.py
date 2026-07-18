"""Forkcast API — Phase 1 scaffold.

Run from the repo root:
  .venv/bin/uvicorn app.main:app --app-dir backend --reload
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel

from . import embeddings, recipes
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
    """Recipes you can cook now (max_missing=0) or almost (1-3 missing)."""
    with connect() as con:
        results = recipes.cookable(
            con, max_missing=max_missing, assume_staples=assume_staples, limit=limit
        )
    return {"count": len(results), "recipes": results}
