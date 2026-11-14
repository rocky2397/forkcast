"""Stage 2 cases: one missing ingredient, and what the kitchen could offer instead.

usage: python build_sub_cases.py <forkcast_checkout> <corpus.db> <kitchens.json> <out.jsonl>
           [--per-kitchen 30] [--max-same 3]

For each kitchen, walks the base "Missing <= 1" list (app.recipes.cookable,
fewest missing then most ingredients) and keeps recipes missing exactly one
non-staple ingredient. The candidates are what the app passes to the
substitution engine: the kitchen inventory minus anything already in the
recipe. Pantry staples are left out, because the engine never offers them and
the app assumes you have them anyway.

The output holds no substitution suggestion: the engine is run separately,
after labelling (run_subs.py). A missing ingredient is kept at most
--max-same times per kitchen so the set isn't dominated by one item.
"""
import argparse, json, sqlite3, sys
ap = argparse.ArgumentParser()
ap.add_argument("src"); ap.add_argument("corpus"); ap.add_argument("kitchens"); ap.add_argument("out")
ap.add_argument("--per-kitchen", type=int, default=30)
ap.add_argument("--max-same", type=int, default=3)
a = ap.parse_args()
sys.path.insert(0, a.src + "/backend")
from app import embeddings, recipes
from app.normalize import Normalizer

norm = Normalizer(embeddings.vocabulary())
con = sqlite3.connect(f"file:{a.corpus}?mode=ro", uri=True)
con.row_factory = sqlite3.Row
con.execute("CREATE TEMP TABLE inventory (canonical TEXT PRIMARY KEY)")
n = 0
with open(a.out, "w") as out:
    for kitchen, items in json.load(open(a.kitchens)).items():
        con.execute("DELETE FROM temp.inventory")
        inv = sorted({c for c in (norm.match(i) for i in items) if c})
        con.executemany("INSERT INTO temp.inventory VALUES (?)", [(c,) for c in inv])
        seen, kept = {}, 0
        for r in recipes.cookable(con, max_missing=1, limit=5000):
            if r["ingredients_missing"] != 1:
                continue
            missing = r["missing"][0]
            if seen.get(missing, 0) >= a.max_same:
                continue
            rows = con.execute("SELECT raw, canonical FROM recipe_ingredients WHERE recipe_id = ? ORDER BY rowid",
                               (r["id"],)).fetchall()
            in_recipe = {x["canonical"] for x in rows if x["canonical"]}
            cands = [c for c in inv if c not in in_recipe and c not in recipes.STAPLES]
            if not cands:
                continue
            seen[missing] = seen.get(missing, 0) + 1
            n += 1; kept += 1
            out.write(json.dumps({
                "case": f"{kitchen}-{kept:02d}", "kitchen": kitchen, "recipe_id": r["id"], "recipe": r["name"],
                "raw_ingredients": [x["raw"] for x in rows],
                "missing": missing,
                "missing_raw": [x["raw"] for x in rows if x["canonical"] == missing],
                "candidates": cands,
            }) + "\n")
            if kept >= a.per_kitchen:
                break
print(n, "cases ->", a.out)
