"""Import the food.com corpus (KingName1/food.com parquet shards) into SQLite.

Nutrition arrives as % daily value; converted to grams/mg using the FDA
reference values the source dataset was built against. Calories are kcal
as-is. Values are per serving per the upstream dataset's convention.

Run from repo root:  .venv/bin/python backend/scripts/import_recipes.py
"""

import json
import sys
from functools import lru_cache
from pathlib import Path

import pandas as pd
from huggingface_hub import HfApi, hf_hub_download

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.db import connect  # noqa: E402
from app.normalize import Normalizer  # noqa: E402
from app import embeddings  # noqa: E402

REPO = "KingName1/food.com"

# %DV -> absolute amounts (FDA daily values used by the source dataset)
DV = {"fat_g": 65, "sat_fat_g": 20, "sugar_g": 50, "sodium_mg": 2400, "protein_g": 50, "carbs_g": 300}


def main():
    norm = Normalizer(embeddings.vocabulary())

    @lru_cache(maxsize=100_000)
    def match(raw: str):
        return norm.match(raw)

    api = HfApi()
    shards = sorted(
        f.path for f in api.list_repo_tree(REPO, repo_type="dataset", recursive=True)
        if f.path.endswith(".parquet")
    )
    print(f"{len(shards)} shards")

    # The pipeline writes the recipe tables, so it needs them in main rather
    # than in the read-only attached corpus (D15).
    con = connect(attach_corpus=False)
    con.execute("DELETE FROM recipe_ingredients")
    con.execute("DELETE FROM recipes")

    rid = 0
    total_ing = matched_ing = 0
    for shard in shards:
        p = hf_hub_download(REPO, shard, repo_type="dataset")
        df = pd.read_parquet(p, columns=[
            "name", "minutes", "n_steps", "steps", "description", "ingredients",
            "n_ingredients", "calories", "total fat (PDV)", "sugar (PDV)",
            "sodium (PDV)", "protein (PDV)", "saturated fat (PDV)", "carbohydrates (PDV)",
        ])
        recipes_rows, ing_rows = [], []
        for r in df.itertuples(index=False):
            parts = [s.strip() for s in str(r.ingredients).split(",") if s.strip()]
            if not parts or not isinstance(r.name, str):
                continue
            rid += 1
            hits = 0
            for raw in parts:
                canonical = match(raw)
                ing_rows.append((rid, raw, canonical))
                total_ing += 1
                if canonical:
                    hits += 1
                    matched_ing += 1
            steps = r.steps.tolist() if hasattr(r.steps, "tolist") else list(r.steps or [])
            recipes_rows.append((
                rid, r.name.strip(), int(r.minutes), int(r.n_steps),
                json.dumps(steps), r.description if isinstance(r.description, str) else None,
                float(r.calories),
                float(getattr(r, "_8")) / 100 * DV["fat_g"],       # total fat (PDV)
                float(getattr(r, "_12")) / 100 * DV["sat_fat_g"],  # saturated fat (PDV)
                float(getattr(r, "_9")) / 100 * DV["sugar_g"],     # sugar (PDV)
                float(getattr(r, "_10")) / 100 * DV["sodium_mg"],  # sodium (PDV)
                float(getattr(r, "_11")) / 100 * DV["protein_g"],  # protein (PDV)
                float(getattr(r, "_13")) / 100 * DV["carbs_g"],    # carbohydrates (PDV)
                len(parts), hits / len(parts),
            ))
        con.executemany(
            "INSERT INTO recipes (id,name,minutes,n_steps,steps,description,calories,"
            "fat_g,sat_fat_g,sugar_g,sodium_mg,protein_g,carbs_g,n_ingredients,matched_frac)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", recipes_rows)
        con.executemany(
            "INSERT INTO recipe_ingredients (recipe_id,raw,canonical) VALUES (?,?,?)", ing_rows)
        con.commit()
        print(f"{shard}: +{len(recipes_rows)} (total {rid})")

    print(f"\nrecipes: {rid}")
    print(f"ingredient match rate: {matched_ing/total_ing:.1%}")
    full = con.execute("SELECT COUNT(*) FROM recipes WHERE matched_frac = 1.0").fetchone()[0]
    print(f"fully matched recipes: {full} ({full/rid:.1%})")
    con.close()


if __name__ == "__main__":
    main()
