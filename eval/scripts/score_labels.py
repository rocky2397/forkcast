"""Score a stage 5 run (see run_labels.py).

usage: python score_labels.py <run.jsonl> [--details]

A value counts as read right when it is within rounding of the database:
kcal within max(1 kcal, 2%), grams within max(0.2 g, 3%). A database value
with a "<" modifier ("< 0.5 g") is right for any reading up to it.

Wrong readings are sorted into the mistakes the prompt warns about:
  kJ          kcal read as kilojoules (about 4.2 times too high)
  portion     every value off by the same factor: the per-portion column
  missing     the reader returned nothing for it
  other       anything else
"""

import json
import math
import statistics
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "backend"))

FIELDS = ("calories", "protein_g", "carbs_g", "fat_g")
LABEL = {"calories": "kcal", "protein_g": "protein", "carbs_g": "carbs", "fat_g": "fat"}


def close(field: str, read, truth: dict) -> bool:
    if read is None:
        return False
    t = truth[field]
    if truth.get(field + "_modifier") == "<":
        return read <= t + 1e-9
    tol = max(1.0, 0.02 * t) if field == "calories" else max(0.2, 0.03 * t)
    return abs(read - t) <= tol + 1e-9


def wilson(k: int, n: int) -> str:
    if n == 0:
        return "-"
    p, z = k / n, 1.96
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return f"{100 * p:.0f}% ({100 * max(0.0, c - h):.0f}-{100 * min(1.0, c + h):.0f})"


def kind(r: dict) -> str:
    read, truth = r["read"], r["truth"]
    if all(read[f] is None for f in FIELDS):
        return "missing"
    kcal = read["calories"]
    # 4.184 kJ per kcal; labels round both, so small values drift (58 kJ / 14 kcal)
    if kcal is not None and truth["calories"] > 0 and 3.6 <= kcal / truth["calories"] <= 4.8:
        return "kJ"
    ratios = [read[f] / truth[f] for f in FIELDS if read[f] and truth[f] > 1]
    if len(ratios) >= 3 and statistics.pstdev(ratios) < 0.05 and abs(statistics.mean(ratios) - 1) > 0.1:
        return "portion"
    return "other"


def adds_up(read: dict) -> bool:
    """The app's own calorie sum check (D36, app/nutrition.py label_check)."""
    from app.nutrition import label_check

    return label_check(*(read[x] for x in FIELDS)) is None


def _dev_table(rows: list[dict], title: str) -> None:
    print(f"\n  how far off, {title} ({len(rows)} products; reader minus database, per 100 g):")
    print(f"    {'':8} {'typical':>9} {'average':>9} {'worst 10%':>10} {'within 5%':>10} {'within 10%':>11} {'within 20%':>11}")
    for f in FIELDS:
        pairs = [(r["read"][f], r["truth"][f]) for r in rows if r["read"][f] is not None]
        if not pairs:
            continue
        err = sorted(abs(a - b) for a, b in pairs)
        unit = "kcal" if f == "calories" else "g"
        floor = 1.0 if f == "calories" else 0.2  # rounding on labels
        within = [sum(1 for a, b in pairs if abs(a - b) <= max(floor, x * b)) / len(pairs) for x in (0.05, 0.10, 0.20)]
        p90 = err[min(len(err) - 1, int(0.9 * len(err)))]
        print(f"    {LABEL[f]:8} {statistics.median(err):>6.1f} {unit:<3}{statistics.mean(err):>6.1f} {unit:<3}"
              f"{p90:>7.1f} {unit:<3}{100 * within[0]:>9.0f}%{100 * within[1]:>10.0f}%{100 * within[2]:>10.0f}%")
    missing = sum(1 for r in rows for f in FIELDS if r["read"][f] is None)
    if missing:
        print(f"    (values not read at all: {missing})")


def deviation(ok: list[dict]) -> None:
    _dev_table(ok, "all readings")
    passed = [r for r in ok if adds_up(r["read"])]
    _dev_table(passed, "readings that pass the sum check")


def main() -> None:
    path = Path(sys.argv[1])
    details = "--details" in sys.argv
    rows = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
    ok = [r for r in rows if "read" in r]
    failed = len(rows) - len(ok)
    print(f"== {rows[0]['model']}: {len(rows)} products ({path.name}), failed calls {failed}")
    n = len(rows)
    for f in FIELDS:
        k = sum(close(f, r["read"][f], r["truth"]) for r in ok)
        print(f"  {LABEL[f]:<8} read right {wilson(k, n)}")
    all4 = [r for r in ok if all(close(f, r["read"][f], r["truth"]) for f in FIELDS)]
    print(f"  all four right    {wilson(len(all4), n)}")
    wrong = [r for r in ok if r not in all4]
    kinds = Counter(kind(r) for r in wrong)
    print(f"  wrong products    {len(wrong)}: " + ", ".join(f"{k} {v}" for k, v in kinds.most_common()))
    errs = [abs(r["read"]["calories"] - r["truth"]["calories"]) for r in ok if r["read"]["calories"] is not None]
    if errs:
        print(f"  kcal error per 100 g: median {statistics.median(errs):.0f}, "
              f"over 10% off in {sum(1 for r in ok if r['read']['calories'] is not None and abs(r['read']['calories'] - r['truth']['calories']) > 0.1 * r['truth']['calories'])} products")
    tin = [r["input_tokens"] for r in ok if "input_tokens" in r]
    tout = [r["output_tokens"] for r in ok if "output_tokens" in r]
    if tin:
        cost = (statistics.mean(tin) * 1.0 + statistics.mean(tout) * 5.0) / 1e6  # Haiku 4.5 list price
        print(f"  tokens {statistics.mean(tin):.0f} in, {statistics.mean(tout):.0f} out; "
              f"about ${cost:.4f} per scan; median {statistics.median(r['seconds'] for r in ok):.1f} s")
    deviation(ok)
    if details:
        print("\n  wrong products (read vs database):")
        for r in wrong:
            cells = []
            for f in FIELDS:
                mark = "" if close(f, r["read"][f], r["truth"]) else "*"
                cells.append(f"{LABEL[f]} {r['read'][f]}/{r['truth'][f]}{mark}")
            print(f"    {r['code']} [{kind(r)}] {r['name'][:30]}: " + ", ".join(cells))


if __name__ == "__main__":
    main()
