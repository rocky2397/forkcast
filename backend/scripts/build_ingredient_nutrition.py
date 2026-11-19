#!/usr/bin/env python
"""Map Forkcast's ingredients onto USDA foods and write their nutrition (D49).

    python backend/scripts/build_ingredient_nutrition.py <sr_legacy_dir> [--review N]

<sr_legacy_dir> is the unpacked USDA FoodData Central "SR Legacy" download
(FoodData_Central_sr_legacy_food_csv_2018-04, public domain, from
https://fdc.nal.usda.gov/download-datasets). It isn't in the repo; only the
result is: app/ingredient_nutrition.json, with each ingredient's USDA food,
calories and macros per 100 g, and the USDA's own portions (1 medium banana
is 118 g).

Each ingredient gets one USDA food. A word-match picks a candidate (all the
ingredient's words in the food's name, raw and plain forms first); the picks
checked by hand live in usda_picks.csv next to this script and win over the
word-match; a row with form "cooked" adds the cooked form. An empty fdc_id
means "no good USDA match": the ingredient is left out rather than given the
wrong food.

--review N prints the N ingredients used most in recipes with what they got,
for checking by eye; nothing is written.
"""
import csv
import json
import re
import sqlite3
import sys
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

from app import embeddings  # noqa: E402
from app.db import CORPUS_PATH  # noqa: E402

PICKS = HERE / "usda_picks.csv"
OUT = HERE.parent / "app" / "ingredient_nutrition.json"

NUTRIENTS = {"1008": "kcal", "1003": "protein_g", "1005": "carbs_g", "1004": "fat_g"}

# Categories that hold dishes, brands or baby food, never a plain ingredient.
SKIP_CATEGORIES = {"3", "21", "22", "24", "25", "26", "27"}

# Words that mean a processed or prepared form; plain forms are preferred.
PROCESSED = {
    "frozen", "canned", "dehydrated", "dried", "cooked", "boiled", "baked", "fried",
    "roasted", "braised", "broiled", "stewed", "imitation", "low", "reduced", "lite",
    "light", "nonfat", "fat-free", "sweetened", "unsweetened", "prepared", "mix",
    "babyfood", "with", "includes", "drained", "solids", "liquids", "pickled",
    "salted", "smoked", "cured", "toasted", "microwaved", "steamed", "glazed",
    "enriched", "unenriched", "fortified", "vitamin", "added", "industrial",
    "commercial", "restaurant", "home-prepared", "retail", "separable", "lean",
    "trimmed", "choice", "select", "all", "grades", "packed", "syrup", "juice",
    "heavy", "concentrate", "diluted", "undiluted", "instant", "regular",
}


# Words that mean a different thing altogether.
AWAY = {"substitute", "meatless", "imitation", "topping", "spread", "dressing", "candie",
        "candy", "beverage", "babyfood", "soup", "cookie", "cracker", "bun", "biscuit",
        "sandwich", "pie", "cake", "smoothie", "sauce", "salami", "wurst", "peel", "oil",
        "flour", "bran", "extract", "drink", "cereal", "bar", "pudding", "snack", "liver",
        "giblet", "heart", "gizzard", "kidney", "mix", "fat-free", "nonfat", "dry"}


def _sing(w: str) -> str:
    if len(w) > 4 and w.endswith("ies"):
        return w[:-3] + "y"
    if len(w) > 4 and w.endswith(("oes", "ches", "shes", "sses")):
        return w[:-2]
    if len(w) > 3 and w.endswith("s") and not w.endswith(("ss", "us")):
        return w[:-1]
    return w


def _words(text: str) -> list[str]:
    return [_sing(w) for w in re.findall(r"[a-z]+(?:-[a-z]+)?", text.lower())]


def load_usda(src: Path):
    foods = {}
    with open(src / "food.csv", newline="") as f:
        for r in csv.DictReader(f):
            if r["food_category_id"] not in SKIP_CATEGORIES:
                foods[r["fdc_id"]] = {"description": r["description"], "category": r["food_category_id"]}
    values: dict[str, dict] = defaultdict(dict)
    with open(src / "food_nutrient.csv", newline="") as f:
        for r in csv.DictReader(f):
            key = NUTRIENTS.get(r["nutrient_id"])
            if key and r["fdc_id"] in foods:
                values[r["fdc_id"]][key] = float(r["amount"])
    portions: dict[str, list] = defaultdict(list)
    with open(src / "food_portion.csv", newline="") as f:
        for r in sorted(csv.DictReader(f), key=lambda r: (r["fdc_id"], int(r["seq_num"] or 0))):
            grams = float(r["gram_weight"] or 0)
            # "1 medium (7" to 7-7/8" long)" -> "1 medium": the grams say the rest.
            modifier = re.sub(r"\s*\([^)]*\)", "", r["modifier"]).strip(" ,")
            modifier = re.sub(r'(\d+-\d+/\d+|\d+/\d+|\d+(?:\.\d+)?)"', _cm, modifier)
            label = " ".join(p for p in (_amount(r["amount"]), modifier) if p)
            have = [p[0] for p in portions[r["fdc_id"]]]
            if r["fdc_id"] in foods and grams > 0 and label and label not in have:
                portions[r["fdc_id"]].append([label, round(grams, 1)])
    complete = {i for i, v in values.items() if len(v) == len(NUTRIENTS)}
    return {i: f for i, f in foods.items() if i in complete}, values, portions


def _cm(m: re.Match) -> str:
    """2-1/4" -> "6 cm": the portion sizes are American, the readers aren't."""
    whole, _, frac = m.group(1).partition("-") if "/" in m.group(1) and "-" in m.group(1) else ("0", "", m.group(1))
    if "/" in frac:
        n, d = frac.split("/")
        inches = float(whole) + float(n) / float(d)
    else:
        inches = float(frac)
    return f"{max(1, round(inches * 2.54))} cm"


def _amount(a: str) -> str:
    if not a:
        return ""
    x = float(a)
    return f"{x:g}"


def candidates(canonical: str, foods: dict) -> list[tuple[float, str]]:
    want = canonical.split("_")
    want = [_sing(w) for w in want]
    head = want[-1]
    out = []
    for fdc, food in foods.items():
        desc = food["description"]
        # "without salt" doesn't make a food salty: drop what follows "without".
        words = _words(re.sub(r"\bwithout( added)? [a-z ]+", "", desc.lower()))
        if not all(w in words for w in want):
            continue
        first = _words(desc.split(",")[0])
        score = 0.0
        if head in first:
            score += 3
        if first and first[0] == head:
            score += 1
        if first == want or first == want[::-1]:
            score += 3
        elif all(w in first for w in want):
            score += 2
        if re.search(r"\b[A-Z]{3,}\b", desc):  # a brand: KRAFT, NABISCO, ...
            score -= 4
        if any(w in words and w not in want for w in AWAY):
            score -= 4
        if "raw" in words:
            score += 2
        extra = [w for w in words if w not in want and w != "raw"]
        score -= sum(1.5 for w in extra if w in PROCESSED)
        score -= 0.3 * len(extra)
        out.append((score, fdc))
    out.sort(key=lambda s: (-s[0], len(foods[s[1]]["description"])))
    return out


def read_picks() -> tuple[dict[str, str | None], dict[str, str]]:
    """(canonical -> fdc_id or None, canonical -> fdc_id of its cooked form)."""
    plain: dict[str, str | None] = {}
    cooked: dict[str, str] = {}
    if PICKS.is_file():
        with open(PICKS, newline="") as f:
            for r in csv.DictReader(f):
                if r["form"] == "cooked":
                    cooked[r["canonical"]] = r["fdc_id"]
                else:
                    plain[r["canonical"]] = r["fdc_id"] or None
    return plain, cooked


def usage() -> dict[str, int]:
    con = sqlite3.connect(f"file:{CORPUS_PATH}?mode=ro", uri=True)
    return dict(con.execute(
        "SELECT canonical, COUNT(*) FROM recipe_ingredients WHERE canonical IS NOT NULL GROUP BY 1"
    ))


def main() -> None:
    args = sys.argv[1:]
    if not args:
        sys.exit(__doc__)
    src = Path(args[0])
    review = int(args[args.index("--review") + 1]) if "--review" in args else None
    foods, values, portions = load_usda(src)
    picks, cooked = read_picks()
    used = usage()
    vocab = embeddings.vocabulary()

    chosen: dict[str, tuple[str, str]] = {}  # canonical -> (fdc_id, 'hand' | 'auto')
    for c in vocab:
        if c in picks:
            if picks[c] is not None:
                chosen[c] = (picks[c], "hand")
            continue
        cands = candidates(c, foods)
        if cands:
            chosen[c] = (cands[0][1], "auto")

    if review is not None:
        top = sorted(vocab, key=lambda c: -used.get(c, 0))[:review]
        for c in top:
            fdc, how = chosen.get(c, (None, "-"))
            desc = foods[fdc]["description"] if fdc else "(none)"
            kcal = values[fdc]["kcal"] if fdc else ""
            print(f"{c}\t{how}\t{fdc or ''}\t{kcal}\t{desc}")
        return

    def food(fdc: str) -> dict:
        return {
            "fdc_id": int(fdc),
            "usda": foods[fdc]["description"],
            **{k: round(values[fdc][k], 1) for k in NUTRIENTS.values()},
            "portions": portions.get(fdc, [])[:6],
        }

    out = {}
    for c in sorted(chosen):
        fdc, how = chosen[c]
        out[c] = {**food(fdc), "picked": how}
        if c in cooked:  # rice, pasta, beans...: weighed dry or cooked differ 2-3x
            out[c]["cooked"] = food(cooked[c])
    with open(OUT, "w") as f:
        f.write("{\n")
        f.write(",\n".join(f"  {json.dumps(k)}: {json.dumps(v, ensure_ascii=False)}" for k, v in out.items()))
        f.write("\n}\n")
    hand = sum(1 for v in out.values() if v["picked"] == "hand")
    print(f"{len(out)} of {len(vocab)} ingredients mapped ({hand} by hand) -> {OUT}")


if __name__ == "__main__":
    main()
