"""Score Test 8 runs (see run_fridge.py).

usage: python score_fridge.py [--truth eval/data/fridge_truth.json] <run.jsonl> [<run.jsonl> ...]

For each scan, after the app's matcher:

  found       visible items in the answer key that some proposal matched
  wrong       proposals whose ingredient isn't in the fridge (not in the key's
              visible or hidden lists): you'd have to untick them
  no match    proposals the matcher turned into no ingredient (the confirm
              screen can't add them either way)
  fixes       wrong + visible items missed: the taps and typing left after
              the scan, against typing every visible item yourself

Items behind others ("hidden" in the key) aren't held against the scanner,
but naming one counts as right. A key entry is one ingredient or a list of
those that count ("red_pepper" or ["red_pepper", "bell_pepper"]).

Also, for the planned "Confident / Not sure" split: at each confidence line,
how many right and wrong proposals land above it. And how often the same
photo gives the same list twice (repeats), tokens, seconds and cost per scan.
Intervals are Wilson 95%; with ten photos they are wide.
"""

import json
import math
import statistics
import sys
from collections import defaultdict
from pathlib import Path

TRUTH = Path(__file__).resolve().parents[1] / "data" / "fridge_truth.json"
# $ per million tokens (input, output), list prices read from
# platform.claude.com/docs/en/about-claude/pricing on 22 November 2026.
PRICE = {
    "claude-haiku-4-5": (1.00, 5.00),
    "claude-haiku-5-5": (0.10, 0.50),  # prompts up to 100,000 tokens
    "claude-sonnet-5-5": (2.00, 10.00),
    "claude-opus-5-5": (4.00, 20.00),
}
LINES = (0.5, 0.7, 0.8, 0.9)


def wilson(k: int, n: int) -> str:
    if n == 0:
        return "-"
    p, z = k / n, 1.96
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return f"{100 * p:.0f}% ({100 * max(0.0, c - h):.0f} to {100 * min(1.0, c + h):.0f})"


def accepted(entries: list) -> list[set[str]]:
    return [set(e) if isinstance(e, list) else {e} for e in entries]


def score(path: Path, truth: dict) -> None:
    rows = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
    model, effort = rows[0]["model"], rows[0]["effort"]
    found = visible = wrong = nomatch = failed = 0
    fixes, typed, tin, tout, secs = [], [], [], [], []
    above = {t: [0, 0] for t in LINES}  # line -> [right, wrong] at or above it
    missed = defaultdict(int)
    wrong_names = defaultdict(int)
    lists = defaultdict(list)  # photo -> each run's set of ingredients
    for r in rows:
        key = truth[r["photo"]]
        seen = accepted(key["visible"])
        ok = set().union(*seen, *accepted(key["hidden"]))
        if "error" in r:
            failed += 1
            continue
        got = {i["canonical"] for i in r["items"] if i["canonical"]}
        lists[r["photo"]].append(got)
        lost = [e for e in seen if not e & got]
        found += len(seen) - len(lost)
        visible += len(seen)
        for e in lost:
            names = sorted(e, key=len)
            missed[names[0] + (" (or a kind of it)" if len(names) > 3 else "/".join([""] + names[1:]))] += 1
        bad = 0
        for i in r["items"]:
            c = i["canonical"]
            if c is None:
                nomatch += 1
                continue
            right = c in ok
            if not right:
                bad += 1
                wrong_names[f"{i['name']} -> {c}"] += 1
            for t in LINES:
                if i["confidence"] >= t:
                    above[t][0 if right else 1] += 1
        wrong += bad
        fixes.append(bad + len(lost))
        typed.append(len(seen))
        tin.append(r.get("input_tokens", 0))
        tout.append(r.get("output_tokens", 0))
        secs.append(r["seconds"])
    scans = len(rows) - failed
    pin, pout = PRICE.get(model, (math.nan, math.nan))
    cost = (statistics.mean(tin) * pin + statistics.mean(tout) * pout) / 1e6 if tin else math.nan
    same = [len(set.intersection(*s)) / max(1, len(set.union(*s))) for s in lists.values() if len(s) > 1]

    print(f"\n== {model}, effort {effort}: {scans} scans of {len(lists)} photos ({path.name})")
    print(f"  found          {wilson(found, visible)} of visible items")
    print(f"  wrong          {wrong / max(1, scans):.1f} per scan   no match {nomatch / max(1, scans):.1f} per scan")
    if fixes:
        print(f"  fixes          {statistics.mean(fixes):.1f} per scan, against typing {statistics.mean(typed):.1f} items")
    print("  confidence     line: right / wrong proposals at or above it")
    for t in LINES:
        print(f"    {t:.1f}         {above[t][0]} / {above[t][1]}")
    if same:
        print(f"  same list      {100 * statistics.mean(same):.0f}% of ingredients shared between runs of a photo")
    print(f"  failed scans   {failed}")
    if tin:
        print(f"  tokens         {statistics.mean(tin):.0f} in, {statistics.mean(tout):.0f} out per scan")
        print(f"  seconds        median {statistics.median(secs):.1f}, slowest {max(secs):.1f}")
        print(f"  cost           ${cost:.4f} per scan, ${200 * cost:.2f} for the demo's 200 a day")
    print("  most missed:   " + ", ".join(f"{k} x{v}" for k, v in sorted(missed.items(), key=lambda kv: -kv[1])[:10]))
    print("  most wrong:    " + ", ".join(f"{k} x{v}" for k, v in sorted(wrong_names.items(), key=lambda kv: -kv[1])[:10]))


if __name__ == "__main__":
    args = sys.argv[1:]
    key = TRUTH
    if args[:1] == ["--truth"]:
        key, args = Path(args[1]), args[2:]
    truth = {p["file"]: p for p in json.loads(key.read_text())["photos"]}
    for p in args:
        score(Path(p), truth)
