"""Prototype: how well do real recipe ingredients map onto Epicure's 1,790-name vocabulary?

Streams a sample of food.com recipes (AkashPS11/recipes_data_food.com) and
normalizes each ingredient string via backend.app.normalize.Normalizer.

Run:  .venv/bin/python prototype/recipe_coverage.py [n_recipes]
"""

import json
import re
import sys
from collections import Counter
from pathlib import Path

from huggingface_hub import snapshot_download
from datasets import load_dataset

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from app.normalize import Normalizer, _clean  # noqa: E402

N = int(sys.argv[1]) if len(sys.argv) > 1 else 3000
R_VEC = re.compile(r'"(.*?)"')


def parse_r_vector(s):
    """food.com fields look like: c("a", "b", "c") — or a bare string."""
    if not isinstance(s, str):
        return []
    if s.startswith("c("):
        return [x for x in R_VEC.findall(s) if x and x != "character(0)"]
    s = s.strip().strip('"')
    return [s] if s and s != "character(0)" else []


def main():
    path = snapshot_download("Kaikaku/epicure-cooc")
    vocab = json.load(open(f"{path}/vocab.json"))
    norm = Normalizer(vocab.keys())

    ds = load_dataset("AkashPS11/recipes_data_food.com", split="train", streaming=True)

    total_ing = matched_ing = 0
    recipe_cov = []
    unmatched = Counter()
    n = 0
    for row in ds:
        parts = parse_r_vector(row.get("RecipeIngredientParts"))
        if not parts:
            continue
        hits = 0
        for p in parts:
            total_ing += 1
            if norm.match(p):
                matched_ing += 1
                hits += 1
            else:
                unmatched[_clean(p)] += 1
        recipe_cov.append(hits / len(parts))
        n += 1
        if n >= N:
            break

    full = sum(1 for c in recipe_cov if c == 1.0)
    ge80 = sum(1 for c in recipe_cov if c >= 0.8)
    print(f"recipes sampled:        {n}")
    print(f"ingredient mentions:    {total_ing}")
    print(f"ingredient match rate:  {matched_ing/total_ing:.1%}")
    print(f"recipes fully matched:  {full/n:.1%}")
    print(f"recipes >=80% matched:  {ge80/n:.1%}")
    print("\ntop 25 unmatched terms:")
    for term, cnt in unmatched.most_common(25):
        print(f"  {cnt:5d}  {term}")


if __name__ == "__main__":
    main()
