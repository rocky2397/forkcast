"""Sample the stage-1 ingredient strings from sources outside Forkcast's code.

  A  food.com rows, uniform over ingredient ROWS  -> row-level accuracy of the corpus
  B  food.com distinct strings, uniform           -> the long tail
  C  Instacart products, weighted by purchases    -> grocery names a person types
                                                     or a photo scan returns

Only raw text is sampled. No matcher output is read or stored here, so the
labels made from this file are blind to what Forkcast predicts.

usage: python sample_strings.py <corpus.db> <instacart_dir> <out.jsonl> [--seed N] [--sizes A,B,C] [--exclude other.jsonl]

The held-out set (data/holdout.jsonl) uses --seed 1114 --sizes 50,50,50
--exclude data/strings.jsonl, so none of its texts were seen while the D27 fix
was designed.
"""
import csv, json, random, sqlite3, sys
from collections import Counter
from pathlib import Path

import argparse
ap = argparse.ArgumentParser()
ap.add_argument("corpus"); ap.add_argument("insta", type=Path); ap.add_argument("out", type=Path)
ap.add_argument("--seed", type=int, default=20261114)
ap.add_argument("--sizes", default="100,75,100")
ap.add_argument("--exclude")
args = ap.parse_args()
corpus, insta, out = args.corpus, args.insta, args.out
SEED = args.seed
NA, NB, NC = map(int, args.sizes.split(","))
exclude = {json.loads(l)["text"] for l in open(args.exclude)} if args.exclude else set()
rng = random.Random(SEED)
con = sqlite3.connect(f"file:{corpus}?mode=ro", uri=True)
rows = []

# A: 100 ingredient rows, uniform over all rows (duplicates are kept on purpose:
# a frequent string should count as often as it appears in recipes)
n_rows = con.execute("SELECT MAX(rowid) FROM recipe_ingredients").fetchone()[0]
picked = []
while len(picked) < NA:
    r = con.execute("SELECT raw FROM recipe_ingredients WHERE rowid = ?",
                    (rng.randint(1, n_rows),)).fetchone()
    if r and r[0] and r[0].strip() and r[0].strip() not in exclude:
        picked.append(r[0].strip())
rows += [{"set": "A", "text": t} for t in picked]

# B: 75 distinct strings, uniform over the distinct list
distinct = sorted({r[0].strip() for r in con.execute("SELECT DISTINCT raw FROM recipe_ingredients") if r[0] and r[0].strip()} - exclude)
rows += [{"set": "B", "text": t} for t in rng.sample(distinct, NB)]

# C: 100 Instacart products from food departments, weighted by purchases
FOOD_DEPTS = {"produce", "dairy eggs", "meat seafood", "pantry", "canned goods",
              "dry goods pasta", "bakery", "frozen", "breakfast", "deli",
              "international", "bulk"}
dept = {r["department_id"]: r["department"] for r in csv.DictReader(open(insta / "departments.csv"))}
prod = {r["product_id"]: r["product_name"] for r in csv.DictReader(open(insta / "products.csv"))
        if dept.get(r["department_id"]) in FOOD_DEPTS and r["product_name"] not in exclude}
buys = Counter(r["product_id"] for r in csv.DictReader(open(insta / "order_products__train.csv"))
               if r["product_id"] in prod)
ids, weights = zip(*sorted(buys.items()))
seen = set()
while len(seen) < NC:
    seen.add(rng.choices(ids, weights)[0])
rows += [{"set": "C", "text": prod[i]} for i in sorted(seen, key=int)]

with out.open("w") as f:
    for i, r in enumerate(rows, 1):
        f.write(json.dumps({"id": f"s{i:03d}", **r}) + "\n")
print(f"{len(rows)} rows, {len({r['text'] for r in rows})} distinct texts -> {out}")
