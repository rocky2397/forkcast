"""Score stage 7: the app's values for a typed food against EU labels.

usage: python score_foods.py <foods.json> [--split dev|held-out|all] [--table ingredient_nutrition.json] [--out rows.jsonl]

For each kind of food in the frozen sample (sample_foods.py), the word a
person types goes through the app exactly as in Log a meal: the matcher (D47
German words included), then app/ingredient_nutrition.json (D49), in the
cooked form for foods bought ready to eat. Each product's label is the
reference. --table scores another version of the table (the one before a
fix), so before and after run on the same products.

Reported, per split:
- found: the word reached an ingredient with values;
- calories within 10% of the label;
- carbs within 3 g per 100 g;
- the median difference for each value, per 100 g.
A word the app can't find, or finds without values, counts as wrong on every
value: in the app, that's a food you can't log this way.
"""

import json
import statistics
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1] / "backend"))

from app import embeddings, foods  # noqa: E402
from app.normalize import Normalizer  # noqa: E402

VALUES = ("calories", "protein_g", "carbs_g", "fat_g")
KCAL_SHARE = 0.10
CARBS_G = 3.0


def app_values(normalizer: Normalizer, typed: str, form: str):
    canonical = normalizer.match(typed)
    food = foods.food(canonical) if canonical else None
    if food is None:
        return canonical, None, None
    use = food["cooked"] if form == "cooked" and food["cooked"] else food
    return canonical, use["usda"], use["per_100g"]


def main() -> None:
    args = sys.argv[1:]
    opt = {}
    for flag in ("--split", "--table", "--out"):
        if flag in args:
            i = args.index(flag)
            opt[flag] = args[i + 1]
            del args[i : i + 2]
    if len(args) != 1:
        sys.exit(__doc__)
    split = opt.get("--split", "dev")
    if "--table" in opt:
        foods.TABLE = Path(opt["--table"])
        foods.table.cache_clear()
    kinds = json.loads(Path(args[0]).read_text())
    normalizer = Normalizer(embeddings.vocabulary())

    rows, per_kind = [], []
    for k in kinds:
        if split != "all" and k["split"] != split:
            continue
        canonical, usda, app = app_values(normalizer, k["typed"], k["form"])
        errs = []
        for p in k["products"]:
            label = p["label"]
            row = {"kind": k["kind"], "typed": k["typed"], "split": k["split"], "code": p["code"],
                   "product": p["name"], "canonical": canonical, "usda": usda, "label": label, "app": app}
            if app:
                row["diff"] = {v: round(app[v] - label[v], 1) for v in VALUES}
                row["kcal_ok"] = abs(app["calories"] - label["calories"]) <= KCAL_SHARE * label["calories"]
                row["carbs_ok"] = abs(app["carbs_g"] - label["carbs_g"]) <= CARBS_G
            else:
                row["kcal_ok"] = row["carbs_ok"] = False
            rows.append(row)
            errs.append(row)
        if errs:
            kcal = [r["diff"]["calories"] for r in errs if "diff" in r]
            carbs = [r["diff"]["carbs_g"] for r in errs if "diff" in r]
            per_kind.append((k["kind"], k["typed"], canonical, len(errs),
                             statistics.median(kcal) if kcal else None,
                             statistics.median(carbs) if carbs else None,
                             sum(r["kcal_ok"] for r in errs)))

    n = len(rows)
    found = sum(1 for r in rows if r["app"])
    print(f"split: {split}, {n} products in {len(per_kind)} kinds, table: {foods.TABLE.name}")
    print(f"  found:                 {found}/{n} ({100 * found / n:.0f}%)")
    print(f"  calories within 10%:   {sum(r['kcal_ok'] for r in rows)}/{n} ({100 * sum(r['kcal_ok'] for r in rows) / n:.0f}%)")
    print(f"  carbs within 3 g:      {sum(r['carbs_ok'] for r in rows)}/{n} ({100 * sum(r['carbs_ok'] for r in rows) / n:.0f}%)")
    for v in VALUES:
        d = [abs(r["diff"][v]) for r in rows if "diff" in r]
        unit = "kcal" if v == "calories" else "g"
        print(f"  median |{v}| off:  {statistics.median(d):.1f} {unit}" if d else f"  median |{v}|: -")
    print()
    print(f"  {'kind':22} {'typed':18} {'app':18} {'n':>2} {'kcal off':>9} {'carbs off':>9} {'kcal ok':>7}")
    for kind, typed, canonical, cnt, kcal, carbs, ok in per_kind:
        fmt = lambda x: "-" if x is None else f"{x:+.0f}"
        print(f"  {kind:22} {typed:18} {str(canonical):18} {cnt:>2} {fmt(kcal):>9} {fmt(carbs):>9} {ok:>4}/{cnt}")
    if "--out" in opt:
        Path(opt["--out"]).write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows))


if __name__ == "__main__":
    main()
