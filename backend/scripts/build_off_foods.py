#!/usr/bin/env python
"""Values for everyday foods the USDA table lacks, from German packs (D55).

    python backend/scripts/build_off_foods.py <cache dir>

Oat drink, muesli, low-fat quark, skyr, 1.5% milk and yogurt (D63) are staples here and missing from
the USDA's SR Legacy (or only there as a US brand). For each, the 12
most-scanned products sold in Germany with all four values per 100 g, from
an Open Food Facts category search cached in <cache dir> (the same pages
eval/scripts/sample_foods.py writes), give the median of each value. The
result, off_foods.csv next to this script, is merged into
app/ingredient_nutrition.json by build_ingredient_nutrition.py, and the app
says where the numbers come from ("Open Food Facts: median of 12 products
sold in Germany").

Data (c) Open Food Facts contributors, ODbL.
"""

import csv
import json
import re
import statistics
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = HERE / "off_foods.csv"
TOP = 12

# key in the app, Open Food Facts category, which products count (values, name)
KINDS = [
    ("oat_milk", "oat-based-drinks", lambda v, n: True),
    ("muesli", "mueslis", lambda v, n: v["fat_g"] <= 10.0),  # not crunchy muesli, which is granola
    ("quark", "quarks", lambda v, n: v["fat_g"] <= 1.0),  # Magerquark, under 1% fat
    ("skyr", "skyrs", lambda v, n: v["carbs_g"] <= 6.0),  # plain, not fruit skyr
    # D63: German milk at 1.5% fat; the USDA has 1% and 2%. A stage 7 dev kind,
    # so building from it doesn't touch the held-out half.
    ("low_fat_milk", "semi-skimmed-milks", lambda v, n: 1.2 <= v["fat_g"] <= 1.8),
    # D63: yogurt at 1.5 to 1.8% fat. The USDA's low-fat yogurt has added milk
    # solids (63 kcal, 7 g carbs), German ones don't (about 52 kcal). A stage 7
    # held-out kind: its results say yogurt no longer counts as unseen.
    ("low_fat_yogurt", "plain-yogurts", lambda v, n: 1.0 <= v["fat_g"] <= 2.0 and not GREEK.search(n)),
]
GREEK = re.compile(r"greek|griech", re.I)
FIELDS = {"kcal": "energy-kcal", "protein_g": "proteins", "carbs_g": "carbohydrates", "fat_g": "fat", "fibre_g": "fiber"}


def values(p: dict) -> dict | None:
    nut = p.get("nutriments") or {}
    out = {}
    for ours, off in FIELDS.items():
        v = nut.get(f"{off}_100g")
        if v is None:
            if ours == "fibre_g":
                out[ours] = 0.0  # often left off for dairy and drinks
                continue
            return None
        out[ours] = float(v)
    return out if out["kcal"] > 0 else None


def main() -> None:
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    cache = Path(sys.argv[1])
    rows = []
    for key, category, keep in KINDS:
        products = json.loads((cache / f"{category}.json").read_text()).get("products", [])
        picked = [v for p in products if (v := values(p)) and keep(v, p.get("product_name") or "")][:TOP]
        med = {k: round(statistics.median(v[k] for v in picked), 1) for k in FIELDS}
        rows.append({"canonical": key, **med, "n": len(picked), "category": category})
        print(f"{key:10} {len(picked)} products: {med}")
    with open(OUT, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["canonical", *FIELDS, "n", "category"])
        w.writeheader()
        w.writerows(rows)


if __name__ == "__main__":
    main()
