"""Stage-1 scorecard: ingredient matching and "cookable now" precision.

usage: python score.py old=<checkout> cur=<checkout> fixed=<checkout> [--details]

For each named version: runs that checkout's matcher on the labelled strings
(development set data/strings_labeled.jsonl and held-out set
data/holdout_labeled.jsonl), and scores the engine outputs
labeling/cookable_<version>.json and labeling/holdout_cookable_<version>.json
(made by run_cookable.py) against the cookable judgements.
"""
import json, os, subprocess, sys
from collections import defaultdict

versions = [a.split("=", 1) for a in sys.argv[1:] if "=" in a]
details = "--details" in sys.argv
STRINGS = {"dev": "data/strings_labeled.jsonl", "held-out": "data/holdout_labeled.jsonl"}
rows = {k: [json.loads(l) for l in open(p)] for k, p in STRINGS.items()}

PREDICT = """
import json, sys
sys.path.insert(0, sys.argv[1] + "/backend")
from app import embeddings
from app.normalize import Normalizer
n = Normalizer(embeddings.vocabulary())
print(json.dumps({t: n.match(t) for t in json.load(sys.stdin)}))
"""
texts = sorted({r["text"] for rs in rows.values() for r in rs})
def predict(src):  # a fresh interpreter per checkout, so versions never share imports
    out = subprocess.run([sys.executable, "-I", "-c", PREDICT, src], input=json.dumps(texts),
                         capture_output=True, text=True, check=True)
    return json.loads(out.stdout)
preds = {name: predict(src) for name, src in versions}

def outcome(pred, gold):
    if pred is None: return "missed" if gold else "abstain"
    return "correct" if pred in gold else "wrong"

def stats(sub, p):
    c = defaultdict(int)
    for r in sub: c[outcome(p[r["text"]], r["gold"])] += 1
    n = len(sub); g = sum(1 for r in sub if r["gold"])
    return (c["correct"] + c["abstain"]) / n, c["wrong"] / n, c["correct"] / g
pct = lambda x: f"{100*x:5.1f}"

print("INGREDIENT MATCHING   accuracy / wrong-match rate / recall   (%)")
print(" " * 30 + "".join(f"{name:>22}" for name, _ in versions))
for split, rs in rows.items():
    for label, f in [("A food.com rows", "A"), ("B food.com tail", "B"), ("C grocery names", "C"), ("all", None)]:
        sub = [r for r in rs if f is None or r["set"] == f]
        cells = "".join(f"{' / '.join(pct(x) for x in stats(sub, preds[name])):>22}" for name, _ in versions)
        print(f"  {split:9} {label:17} n={len(sub):3}{cells}")

def load_labels(path):
    out = {}
    for line in open(path):
        k, rid, ok, note = (line.rstrip("\n").split("\t") + [""])[:4]
        out[(k, int(rid))] = (ok == "yes", note)
    return out
labels = {**load_labels("labeling/cookable_labels.tsv"), **load_labels("labeling/holdout_cookable_labels.tsv")}

print("\nCOOKABLE NOW   precision@20 (listed recipes that are really cookable)")
for split, prefix in [("dev", "cookable"), ("held-out", "holdout_cookable")]:
    for name, _ in versions:
        res = json.load(open(f"labeling/{prefix}_{name}.json"))
        ok = tot = 0; parts = []
        for k, d in res.items():
            good = sum(labels[(k, r["id"])][0] for r in d["recipes"]); ok += good; tot += len(d["recipes"])
            parts.append(f"{k} {good}/{len(d['recipes'])}")
        print(f"  {split:9} {name:6} {ok:2}/{tot} = {pct(ok/tot)}%   ({', '.join(parts)})")

if details and len(versions) >= 2:
    a, b = versions[-2][0], versions[-1][0]
    for split, rs in rows.items():
        print(f"\nWRONG MATCHES, {b}, {split}")
        for t in sorted({r["text"] for r in rs if outcome(preds[b][r["text"]], r["gold"]) == "wrong"}):
            g = next(r["gold"] for r in rs if r["text"] == t)
            print(f"  {t!r} -> {preds[b][t]}   gold {g or '∅'}")
        print(f"\nCHANGED {a} -> {b}, {split}")
        seen = set()
        for r in rs:
            t = r["text"]; x, y = preds[a][t], preds[b][t]
            if x != y and t not in seen:
                seen.add(t); print(f"  {t!r}: {x} -> {y}   [{outcome(x, r['gold'])} -> {outcome(y, r['gold'])}]")
    for split, prefix in [("dev", "cookable"), ("held-out", "holdout_cookable")]:
        print(f"\nFALSE 'COOKABLE', {b}, {split}")
        for k, d in json.load(open(f"labeling/{prefix}_{b}.json")).items():
            for r in d["recipes"]:
                ok, note = labels[(k, r["id"])]
                if not ok: print(f"  {k}: {r['name']!r} — missing {note}")
