"""Score substitution suggestions against the stage 2 labels.

usage: python score_subs.py <labels.tsv> <name>=<suggestions.json> ... [--details]
"""
import json, math, sys

def wilson(k, n, z=1.96):
    if n == 0:
        return (float("nan"), float("nan"))
    p = k / n; d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d; h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (c - h, c + h)

def load(path):
    gold = {}
    for line in open(path):
        if line.startswith("#") or not line.strip():
            continue
        f = (line.rstrip("\n").split("\t") + [""] * 5)[:5]
        gold[f[0]] = {"good": {x for x in f[1].split(",") if x}, "ok": {x for x in f[2].split(",") if x},
                      "flags": f[3], "note": f[4]}
    return gold

args = [a for a in sys.argv[1:] if a != "--details"]
gold = load(args[0])
for spec in args[1:]:
    name, path = spec.split("=", 1)
    pred = json.load(open(path))
    t = {"shown": 0, "good": 0, "ok": 0, "bad": 0, "missed": 0, "silent_ok": 0, "usable": 0, "usable_hit": 0}
    rows = []
    for case, g in gold.items():
        p = pred[case]
        usable = g["good"] | g["ok"]
        t["usable"] += bool(usable)
        if p is None:
            out = "missed" if usable else "silent_ok"
        else:
            t["shown"] += 1
            out = "good" if p in g["good"] else "ok" if p in g["ok"] else "bad"
            if out != "bad" and usable:
                t["usable_hit"] += 1
        t[out] += 1
        rows.append((case, p, out, g))
    n = len(gold); s = t["shown"]
    lo, hi = wilson(t["good"] + t["ok"], s)
    print(f"== {name}: {n} cases, {s} suggestions shown ({s / n:.0%})")
    if s:
        print(f"   precision of shown, lenient (good or ok): {t['good'] + t['ok']}/{s} = {(t['good'] + t['ok']) / s:.1%}"
              f"  [95% CI {lo:.0%}-{hi:.0%}]")
        print(f"   precision of shown, strict (good only):   {t['good']}/{s} = {t['good'] / s:.1%}")
    print(f"   bad suggestions: {t['bad']}/{n} cases = {t['bad'] / n:.1%}")
    print(f"   recall where a usable stand-in exists: {t['usable_hit']}/{t['usable']}"
          f" = {t['usable_hit'] / max(t['usable'], 1):.1%}")
    print(f"   correct silence: {t['silent_ok']}, missed: {t['missed']}")
    if "--details" in sys.argv:
        for case, p, out, g in rows:
            if out in ("bad", "missed") or p is not None:
                print(f"   {out:9} {case:18} -> {p}   good={sorted(g['good'])} ok={sorted(g['ok'])} {g['flags']}")
