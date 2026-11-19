"""Freeze the stage 7 sample: single-ingredient foods sold in Germany.

usage: python sample_foods.py <cache dir> <out foods.json> [--cached-only | --fresh-after <frozen.json>]

Stage 7 asks whether the values Forkcast gives a typed ingredient (D49, from
the USDA's tables) match the label on what people here buy. KINDS below was
written before any value was compared: each kind of food, the Open Food Facts
category it is sold under, the German word a person would type for it, and
whether it is bought ready to eat (canned chickpeas are cooked; the app's
"weighed cooked" form is then the fair comparison). The words are what people
type, not what the app happens to match: a word the app can't find is a miss.

For each kind: the 4 most-scanned products sold in Germany with all four
values per 100 g, energy above 0 and one or two ingredients (salt allowed),
from the Open Food Facts search API (raw pages cached in <cache dir>, not
committed). Open Food Facts allows about 10 searches a minute, so this waits
between searches. Kinds are split into a dev half and a held-out half with a
fixed seed before anything is scored: a fix is designed on dev and judged on
held-out.

--cached-only freezes the kinds already in the cache and lists the others as
not fetched. Used for the November 2026 sample: Open Food Facts throttled the
search after 21 of the 33 kinds, and the 21 were frozen as they were, before
any value was compared, each keeping its half from the split of all 33.

--fresh-after freezes only the kinds missing from an earlier frozen sample,
marked "fresh": the 12 kinds fetched once Open Food Facts answered again. No
fix was designed on them, so they judge D53 a second time.

Data (c) Open Food Facts contributors, ODbL.
"""

import json
import random
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

# (kind, Open Food Facts category, what a person types, form)
KINDS = [
    ("rolled oats", "rolled-oats", "Haferflocken", "raw"),
    ("whole milk", "whole-milks", "Vollmilch", "raw"),
    ("semi-skimmed milk", "semi-skimmed-milks", "fettarme Milch", "raw"),
    ("rice", "rices", "Reis", "raw"),
    ("basmati rice", "basmati-rices", "Basmatireis", "raw"),
    ("dry pasta", "dry-pastas", "Nudeln", "raw"),
    ("dry lentils", "lentils", "Linsen", "raw"),
    ("canned chickpeas", "canned-chickpeas", "Kichererbsen", "cooked"),
    ("canned kidney beans", "canned-red-kidney-beans", "Kidneybohnen", "cooked"),
    ("wheat flour", "wheat-flours", "Weizenmehl", "raw"),
    ("sugar", "white-sugars", "Zucker", "raw"),
    ("butter", "butters", "Butter", "raw"),
    ("olive oil", "extra-virgin-olive-oils", "Olivenöl", "raw"),
    ("sunflower oil", "sunflower-oils", "Sonnenblumenöl", "raw"),
    ("rapeseed oil", "rapeseed-oils", "Rapsöl", "raw"),
    ("plain yogurt", "plain-yogurts", "Naturjoghurt", "raw"),
    ("whipping cream", "whipping-creams", "Schlagsahne", "raw"),
    ("mozzarella", "mozzarella", "Mozzarella", "raw"),
    ("gouda", "goudas", "Gouda", "raw"),
    ("feta", "feta", "Feta", "raw"),
    ("almonds", "almonds", "Mandeln", "raw"),
    ("walnuts", "walnuts", "Walnüsse", "raw"),
    ("hazelnuts", "hazelnuts", "Haselnüsse", "raw"),
    ("raisins", "raisins", "Rosinen", "raw"),
    ("honey", "honeys", "Honig", "raw"),
    ("frozen spinach", "frozen-spinachs", "Spinat", "raw"),
    ("frozen peas", "frozen-peas", "Erbsen", "raw"),
    ("passata", "tomato-passata", "passierte Tomaten", "raw"),
    ("low-fat quark", "quarks", "Magerquark", "raw"),
    ("couscous", "couscous", "Couscous", "raw"),
    ("quinoa", "quinoa", "Quinoa", "raw"),
    ("coconut milk", "coconut-milks", "Kokosmilch", "raw"),
    ("flaxseed", "flax-seeds", "Leinsamen", "raw"),
]

PER_KIND = 4
SEED = 7
FIELDS = {"calories": "energy-kcal", "protein_g": "proteins", "carbs_g": "carbohydrates",
          "fat_g": "fat", "fibre_g": "fiber"}
# The classic search endpoint: the v2 one answered 503 for most searches in November 2026.
SEARCH = ("https://world.openfoodfacts.org/cgi/search.pl?action=process&json=1"
          "&tagtype_0=categories&tag_contains_0=contains&tag_0={tag}"
          "&tagtype_1=countries&tag_contains_1=contains&tag_1=germany"
          "&fields=code,product_name,ingredients_n,nutriments&sort_by=unique_scans_n&page_size=60")
AGENT = "Forkcast-eval/0.1 (food-logging evaluation)"


def search(tag: str, cache: Path) -> dict:
    path = cache / f"{tag}.json"
    if path.is_file():
        return json.loads(path.read_text())
    req = urllib.request.Request(SEARCH.format(tag=urllib.parse.quote(tag)), headers={"User-Agent": AGENT})
    for attempt in range(8):
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                data = json.load(resp)
            path.write_text(json.dumps(data))
            time.sleep(20)  # Open Food Facts is often overloaded: go slow
            return data
        except Exception as e:  # rate limit or a hiccup: wait and retry
            print(f"  {tag}: {e}, waiting")
            time.sleep(60 * (attempt + 1))
    raise SystemExit(f"Open Food Facts didn't answer for {tag}")


def values(p: dict) -> dict | None:
    nut = p.get("nutriments") or {}
    out = {}
    for ours, off in FIELDS.items():
        v = nut.get(f"{off}_100g")
        if v is None:
            if ours == "fibre_g":
                continue  # fibre is optional on EU labels
            return None
        out[ours] = float(v)
    return out if out["calories"] > 0 else None


def main() -> None:
    args = sys.argv[1:]
    cached_only = "--cached-only" in args
    args = [a for a in args if a != "--cached-only"]
    done: set[str] = set()
    if "--fresh-after" in args:
        i = args.index("--fresh-after")
        done = {k["kind"] for k in json.loads(Path(args[i + 1]).read_text())}
        del args[i : i + 2]
    if len(args) != 2:
        sys.exit(__doc__)
    cache, out = Path(args[0]), Path(args[1])
    cache.mkdir(parents=True, exist_ok=True)
    order = list(range(len(KINDS)))
    random.Random(SEED).shuffle(order)
    held_out = set(order[: len(order) // 2])
    kinds, skipped = [], []
    for i, (kind, tag, word, form) in enumerate(KINDS):
        if cached_only and not (cache / f"{tag}.json").is_file():
            skipped.append(kind)
            continue
        if kind in done:
            continue
        data = search(tag, cache)
        picked = []
        for p in data.get("products", []):
            v = values(p)
            n = p.get("ingredients_n")
            if v and isinstance(n, int) and n <= 2 and p.get("code") not in {q["code"] for q in picked}:
                picked.append({"code": p["code"], "name": p.get("product_name") or "", "label": v})
            if len(picked) == PER_KIND:
                break
        print(f"{kind:22} {tag:26} {data.get('count', 0):6} listed, {len(picked)} kept")
        split = "fresh" if done else ("held-out" if i in held_out else "dev")
        kinds.append({"kind": kind, "category": tag, "typed": word, "form": form,
                      "split": split, "products": picked})
    if skipped:
        print(f"not fetched (Open Food Facts throttled the search): {', '.join(skipped)}")
    out.write_text(json.dumps(kinds, indent=1, ensure_ascii=False) + "\n")
    print(f"{sum(len(k['products']) for k in kinds)} products in {len(kinds)} kinds -> {out}")


if __name__ == "__main__":
    main()
