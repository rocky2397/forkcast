"""Forkcast API — Phase 1 scaffold.

Run from the repo root:
  .venv/bin/uvicorn app.main:app --app-dir backend --reload
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Query

from . import embeddings
from .normalize import Normalizer

normalizer: Normalizer | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global normalizer
    normalizer = Normalizer(embeddings.vocabulary())  # also warms the cooc model
    yield


app = FastAPI(title="Forkcast API", lifespan=lifespan)


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
