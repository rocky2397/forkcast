"""Test 8: the answer key for the aicook fridge photos.

usage: python build_aicook_truth.py <aicook v1 dir> [--split test] [--corrected]
           [--out eval/data/fridge_truth_aicook.json]

The aicook dataset (Karel Cornelis, Erasmus Brussels; MIT licence;
universe.roboflow.com/karel-cornelis-q2qqg/aicook-lcv4d, version 1, COCO
export) is 516 photos of one fridge, randomly filled from 30 kinds of
ingredient, every item boxed and labelled. Its own test split is 51 photos.

Each label maps to the Forkcast ingredients that count as right. This table
was written from the vocabulary alone, before any scanner output was seen.
Where the label is generic ("cheese", "mushrooms"), naming a specific kind
counts. Every labelled item counts as visible; the set has no hidden ones.

--corrected adds the two fixes in CORRECTIONS, made after the first runs
(see eval/RESULTS-stage8.md): crops of the labelled boxes showed that the
dataset's "butter" is a tub of Planta margarine and some of its "milk"
cartons are Alpro Soya. Both keys are kept and both scores reported.
"""

import argparse
import json
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
VOCAB = set((REPO / "eval" / "data" / "vocab.txt").read_text().split())

SOFT = {"cream_cheese", "cottage_cheese", "ricotta_cheese", "mascarpone_cheese",
        "goat_cheese", "plant_based_cheese"}
CHEESES = sorted(["cheese"] + [v for v in VOCAB if v.endswith("_cheese") and v not in SOFT])
MUSHROOMS = sorted(["mushroom"] + [v for v in VOCAB if v.endswith("_mushroom") and v != "shrimp_mushroom"])

ACCEPT = {
    "apple": ["apple"],
    "banana": ["banana"],
    "beef": ["beef"],
    "ground_beef": ["beef"],  # the vocabulary has no minced beef
    "blueberries": ["blueberry"],
    "bread": ["bread", "milk_bread", "pita_bread", "rye_bread"],
    "butter": ["butter"],
    "carrot": ["carrot"],
    "cheese": CHEESES,
    "goat_cheese": ["goat_cheese", "cheese"],
    "chicken": ["chicken"],
    "chicken_breast": ["chicken"],  # no separate cut in the vocabulary
    "chocolate": ["chocolate", "milk_chocolate", "white_chocolate"],
    "corn": ["corn"],
    "eggs": ["egg"],
    "flour": ["flour"],
    "green_beans": ["green_bean"],
    "ham": ["ham"],
    "heavy_cream": ["cream"],
    "lime": ["lime"],
    "milk": ["milk"],
    "mushrooms": MUSHROOMS,
    "onion": ["onion", "red_onion"],
    "potato": ["potato"],
    "shrimp": ["shrimp"],
    "spinach": ["spinach"],
    "strawberries": ["strawberry"],
    "sugar": ["sugar", "brown_sugar"],
    "sweet_potato": ["sweet_potato", "purple_sweet_potato"],
    "tomato": ["tomato"],
}


# Found by looking at the labelled boxes after the first runs, not before.
CORRECTIONS = {
    "butter": ["butter", "margarine"],  # the tub is Planta margarine
    "milk": ["milk", "soy_milk", "plant_based_milk"],  # some cartons are Alpro Soya
}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("dataset", type=Path)
    ap.add_argument("--split", default="test")
    ap.add_argument("--out", type=Path, default=None)
    ap.add_argument("--corrected", action="store_true", help="apply CORRECTIONS")
    args = ap.parse_args()
    if args.corrected:
        ACCEPT.update(CORRECTIONS)
    name = "fridge_truth_aicook_corrected.json" if args.corrected else "fridge_truth_aicook.json"
    args.out = args.out or REPO / "eval" / "data" / name

    for label, names in ACCEPT.items():
        missing = [n for n in names if n not in VOCAB]
        assert not missing, f"{label}: not in the vocabulary: {missing}"

    coco = json.loads((args.dataset / args.split / "_annotations.coco.json").read_text())
    cats = {c["id"]: c["name"] for c in coco["categories"]}
    labels: dict[int, set[str]] = {}
    for a in coco["annotations"]:
        labels.setdefault(a["image_id"], set()).add(cats[a["category_id"]])
    photos = []
    for img in sorted(coco["images"], key=lambda i: i["file_name"]):
        found = sorted(labels.get(img["id"], ()))
        # chicken and chicken_breast (or beef and ground_beef) in one photo
        # are one Forkcast ingredient: count it once.
        visible = []
        for x in found:
            entry = ACCEPT[x] if len(ACCEPT[x]) > 1 else ACCEPT[x][0]
            if entry not in visible:
                visible.append(entry)
        photos.append({"file": img["file_name"], "labels": found, "visible": visible, "hidden": []})
    args.out.write_text(json.dumps({
        "source": "aicook v1 (Karel Cornelis, MIT licence), split " + args.split
                  + (", with the corrections in build_aicook_truth.py" if args.corrected else ""),
        "photos": photos,
    }, indent=1, ensure_ascii=False) + "\n")
    print(f"{len(photos)} photos, {sum(len(p['labels']) for p in photos)} labelled kinds -> {args.out}")


if __name__ == "__main__":
    main()
