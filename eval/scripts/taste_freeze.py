"""Freeze the stage 3 users before the engine ever runs on them.

usage: python taste_freeze.py <kaggle_dir> <corpus.db> <out.json>

Every food.com user with at least 10 rated corpus recipes is eligible. A
seeded shuffle puts half in "dev" (to check the pipeline works) and half in
"test" (the numbers that get reported). The file is committed before any
score is computed, so the test users cannot be picked after the fact.
"""
import json
import random
import sys

from taste_data import HISTORY_SHARE, MIN_RATINGS, corpus_ids, user_ratings

SEED = 20261115

raw_dir, corpus, out = sys.argv[1:4]
ids = corpus_ids(raw_dir, corpus)
users = user_ratings(raw_dir, ids)
eligible = sorted((u for u, r in users.items() if len(r) >= MIN_RATINGS), key=int)
random.Random(SEED).shuffle(eligible)
half = len(eligible) // 2
frozen = {
    "seed": SEED,
    "rule": f">= {MIN_RATINGS} rated corpus recipes; earliest {HISTORY_SHARE:.0%} is history, rest hidden",
    "recipes_matched": len(ids),
    "dev": sorted(eligible[:half], key=int),
    "test": sorted(eligible[half:], key=int),
}
json.dump(frozen, open(out, "w"), indent=0)
print(f"{len(ids)} corpus recipes matched; {len(eligible)} users -> "
      f"{len(frozen['dev'])} dev, {len(frozen['test'])} test -> {out}")
