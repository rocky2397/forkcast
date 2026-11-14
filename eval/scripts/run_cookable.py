"""Top-N "cookable now" recipes per test kitchen, from Forkcast's own engine.

usage: python run_cookable.py <forkcast_checkout> <corpus.db> <kitchens.json> <out.json>

The kitchen is typed in plain words and goes through that checkout's matcher,
exactly like the inventory box. The ranking is the base engine
(app.recipes.cookable: fewest missing, then most ingredients), with no taste or
macro re-ranking. Each recipe is stored with its RAW ingredient wording so it
can be judged without seeing what the matcher made of it.
"""
import json, sqlite3, sys
src, corpus, kitchens, out = sys.argv[1:5]
sys.path.insert(0, src + "/backend")
from app import embeddings, recipes
from app.normalize import Normalizer

norm = Normalizer(embeddings.vocabulary())
con = sqlite3.connect(f"file:{corpus}?mode=ro", uri=True)
con.row_factory = sqlite3.Row
con.execute("CREATE TEMP TABLE inventory (canonical TEXT PRIMARY KEY)")
result = {}
for name, items in json.load(open(kitchens)).items():
    con.execute("DELETE FROM temp.inventory")
    inv = {i: norm.match(i) for i in items}
    con.executemany("INSERT OR IGNORE INTO temp.inventory VALUES (?)", [(c,) for c in inv.values() if c])
    top = recipes.cookable(con, max_missing=0, limit=20)
    for r in top:
        r["raw_ingredients"] = [x[0] for x in con.execute(
            "SELECT raw FROM recipe_ingredients WHERE recipe_id = ? ORDER BY rowid", (r["id"],))]
    result[name] = {"inventory": inv, "recipes": [
        {k: r[k] for k in ("id", "name", "ingredients_needed", "raw_ingredients")} for r in top]}
json.dump(result, open(out, "w"), indent=1)
print({k: len(v["recipes"]) for k, v in result.items()}, "->", out)
