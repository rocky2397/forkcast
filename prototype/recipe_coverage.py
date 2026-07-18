"""Prototype: how well do real recipe ingredients map onto Epicure's 1,790-name vocabulary?

Streams a sample of food.com recipes (AkashPS11/recipes_data_food.com) and
tries to normalize each ingredient string to a canonical Epicure ingredient.

Matching cascade (cheap → fuzzier):
  1. exact match after basic cleanup
  2. singular/plural variants
  3. drop leading descriptors (fresh, chopped, ...) and retry
  4. longest canonical name contained in the string (token-boundary aware)

Run:  .venv/bin/python prototype/recipe_coverage.py [n_recipes]
"""

import json
import re
import sys
from collections import Counter

from huggingface_hub import snapshot_download
from datasets import load_dataset

N = int(sys.argv[1]) if len(sys.argv) > 1 else 3000

DESCRIPTORS = {
    "fresh", "freshly", "chopped", "diced", "minced", "sliced", "grated",
    "shredded", "ground", "dried", "frozen", "canned", "cooked", "raw",
    "large", "small", "medium", "boneless", "skinless", "lean", "extra",
    "light", "low-fat", "lowfat", "nonfat", "fat-free", "reduced-fat",
    "unsalted", "salted", "sweetened", "unsweetened", "hot", "cold", "warm",
    "ripe", "baby", "whole", "plain", "instant", "quick-cooking", "prepared",
    "packed", "firmly", "finely", "coarsely", "thinly", "roughly", "of",
}

R_VEC = re.compile(r'"(.*?)"')


def parse_r_vector(s):
    """food.com fields look like: c("a", "b", "c") — or a bare string."""
    if not isinstance(s, str):
        return []
    if s.startswith("c("):
        return R_VEC.findall(s)
    s = s.strip().strip('"')
    return [s] if s else []


def clean(term):
    t = term.lower().strip()
    t = re.sub(r"\(.*?\)", " ", t)          # parentheticals
    t = re.sub(r"[^a-z ]+", " ", t)          # punctuation/digits
    t = re.sub(r"\s+", " ", t).strip()
    return t


def variants(t):
    yield t
    if t.endswith("ies"):
        yield t[:-3] + "y"
    if t.endswith("es"):
        yield t[:-2]
    if t.endswith("s"):
        yield t[:-1]


def build_matcher(vocab_names):
    canon = {}  # cleaned spaced form -> canonical name
    for name in vocab_names:
        canon[name.replace("_", " ")] = name
    # canonical names sorted longest-first for containment pass
    by_len = sorted(canon.keys(), key=len, reverse=True)

    def match(raw):
        t = clean(raw)
        if not t:
            return None
        # 1+2: exact / plural variants
        for v in variants(t):
            if v in canon:
                return canon[v]
        # 3: strip descriptors
        toks = [w for w in t.split() if w not in DESCRIPTORS]
        stripped = " ".join(toks)
        for v in variants(stripped):
            if v in canon:
                return canon[v]
        # 4: longest canonical name contained as whole-word span
        hay = f" {stripped} "
        for c in by_len:
            if len(c) < 3:
                continue
            if f" {c} " in hay or (c.endswith("s") is False and f" {c}s " in hay):
                return canon[c]
        return None

    return match


def main():
    path = snapshot_download("Kaikaku/epicure-cooc")
    vocab = json.load(open(f"{path}/vocab.json"))
    match = build_matcher(vocab.keys())

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
            m = match(p)
            if m:
                matched_ing += 1
                hits += 1
            else:
                unmatched[clean(p)] += 1
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
