"""Score stage 4 runs (see run_vision.py).

usage: python score_vision.py <run.jsonl> [<run.jsonl> ...]

For each photo the question is: after the app's matcher, is the photographed
item among the scanner's proposals? Store photos also show neighbouring
products, so extra proposals are counted but not held against the scanner.

  found        some proposal's matched ingredient is in the answer key
  said, lost   the model named the item (its words appear in a proposal), but
               the matcher turned it into the wrong ingredient or none:
               a matcher problem, not a vision one (approximate, word-based)
  missed       neither

Also: proposals per photo, failed calls, tokens, seconds and cost per scan
at list prices. Intervals are Wilson 95%.
"""

import json
import math
import statistics
import sys
from collections import defaultdict
from pathlib import Path

GOLD = json.loads((Path(__file__).resolve().parents[1] / "data" / "vision_gold.json").read_text())["classes"]
PRICE = {  # $ per million tokens (input, output), list prices
    "claude-haiku-4-5": (1.00, 5.00),
    "claude-haiku-5-5": (0.10, 0.50),
}
# Words that show the model named the item, per answer-key ingredient.
SAID = {
    "fruit_juice": ["juice"], "plant_based_milk": ["oat", "soy"], "soy_yogurt": ["soy", "yog"],
    "yogurt": ["yog", "oatghurt"], "eggplant": ["aubergine", "eggplant"], "bell_pepper": ["pepper"],
    "tangerine": ["satsuma", "mandarin", "tangerine", "clementine"], "buttermilk": ["sour milk", "buttermilk", "fermented milk", "filmj", "kefir"],
    "beet": ["beet"], "honeydew_melon": ["honeydew", "melon"], "sweet_potato": ["sweet potato"],
}


def wilson(k: int, n: int) -> str:
    if n == 0:
        return "-"
    p, z = k / n, 1.96
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return f"{100 * p:.0f}% ({100 * max(0.0, c - h):.0f}-{100 * min(1.0, c + h):.0f})"


def said(label: str, items: list[dict]) -> bool:
    words = []
    for a in GOLD[label]["accepted"]:
        words += SAID.get(a, [a.replace("_", " ")])
    names = " ".join(i["name"].lower() for i in items)
    return any(w in names for w in words)


def score(path: Path) -> None:
    rows = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
    model, effort = rows[0]["model"], rows[0]["effort"]
    group = defaultdict(lambda: [0, 0])
    found = lost = failed = 0
    per_photo, tin, tout, secs = [], [], [], []
    misses = defaultdict(list)
    for r in rows:
        g = r["photo"].split("/")[1]  # Fruit, Vegetables, Packages
        group[g][1] += 1
        if "error" in r:
            failed += 1
            misses[r["label"]].append("ERROR")
            continue
        items = r["items"]
        per_photo.append(len(items))
        tin.append(r.get("input_tokens", 0))
        tout.append(r.get("output_tokens", 0))
        secs.append(r["seconds"])
        accepted = set(GOLD[r["label"]]["accepted"])
        if any(i["canonical"] in accepted for i in items):
            found += 1
            group[g][0] += 1
        else:
            if said(r["label"], items):
                lost += 1
            misses[r["label"]].append("; ".join(f"{i['name']}->{i['canonical']}" for i in items) or "(nothing)")
    n = len(rows)
    pin, pout = PRICE.get(model, (math.nan, math.nan))
    cost = (statistics.mean(tin) * pin + statistics.mean(tout) * pout) / 1e6 if tin else math.nan
    print(f"\n== {model}, effort {effort}: {n} photos ({path.name})")
    print(f"  found          {wilson(found, n)}")
    for g in sorted(group):
        print(f"    {g:<12} {wilson(*group[g])}")
    print(f"  said, lost     {lost} photos (model named it, matcher lost it)")
    print(f"  missed         {n - found - lost - failed}   failed calls {failed}")
    if per_photo:
        print(f"  proposals      {statistics.mean(per_photo):.1f} per photo")
        print(f"  tokens         {statistics.mean(tin):.0f} in, {statistics.mean(tout):.0f} out per scan")
        print(f"  seconds        median {statistics.median(secs):.1f}, slowest {max(secs):.1f}")
        print(f"  cost           ${cost:.5f} per scan, ${1000 * cost:.2f} per 1,000 scans")
    print("  classes with misses (photos missed: what was proposed):")
    for label in sorted(misses, key=lambda k: -len(misses[k])):
        print(f"    {label} x{len(misses[label])}: {misses[label][0][:140]}")


if __name__ == "__main__":
    for p in sys.argv[1:]:
        score(Path(p))
