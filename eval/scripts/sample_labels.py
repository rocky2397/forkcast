"""Freeze the stage 5 sample from an Open Food Facts search result.

usage: python sample_labels.py <search_1.json> [<search_2.json> ...] <out products.json> [--n 150]

Input: pages of the Open Food Facts search API (products sold in Germany with
completed nutrition facts, most scanned first), with the fields code,
product_name, nutriments and images. Keeps products that have a German
nutrition photo ("nutrition_de", the cropped table a contributor selected) and
all four values per 100 g, drops zero-energy products (water, which would be
free points), and writes the first N in popularity order. The database's
values are typed in by Open Food Facts contributors, so they are a reference,
not ground truth: score_labels.py reports disagreements, and they are checked
by eye (RESULTS-stage5.md).
"""

import json
import sys
from pathlib import Path

FIELDS = {"calories": "energy-kcal", "protein_g": "proteins", "carbs_g": "carbohydrates", "fat_g": "fat"}


def image_url(code: str, rev) -> str:
    path = code if len(code) <= 8 else f"{code[0:3]}/{code[3:6]}/{code[6:9]}/{code[9:]}"
    return f"https://images.openfoodfacts.org/images/products/{path}/nutrition_de.{rev}.full.jpg"


def main() -> None:
    args = sys.argv[1:]
    n = 150
    if "--n" in args:
        i = args.index("--n")
        n = int(args[i + 1])
        del args[i : i + 2]
    *pages, out = args
    seen, keep = set(), []
    for page in pages:
        for p in json.loads(Path(page).read_text())["products"]:
            code = p.get("code")
            img = (p.get("images") or {}).get("nutrition_de")
            nut = p.get("nutriments") or {}
            if not code or code in seen or not img or not img.get("rev"):
                continue
            truth = {}
            for ours, off in FIELDS.items():
                v = nut.get(f"{off}_100g")
                if v is None:
                    break
                truth[ours] = float(v)
                mod = nut.get(f"{off}_modifier")
                if mod:
                    truth[ours + "_modifier"] = mod
            if len(truth) < 4 or truth["calories"] <= 0:
                continue
            seen.add(code)
            keep.append({"code": code, "name": p.get("product_name") or "", "image": image_url(code, img["rev"]), "truth": truth})
    keep = keep[:n]
    Path(out).write_text(json.dumps(keep, indent=1, ensure_ascii=False) + "\n")
    print(f"kept {len(keep)} products")


if __name__ == "__main__":
    main()
