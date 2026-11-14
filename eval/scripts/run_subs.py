"""Run Forkcast's substitution engine on the stage 2 cases.

usage: python run_subs.py <forkcast_checkout> <cases.jsonl> <out.json>

Calls app.substitutions.suggest(missing, candidates) exactly as the app does
for the feed and the recipe page. Writes {case: suggestion or null}.
"""
import json, sys
src, cases, out = sys.argv[1:4]
sys.path.insert(0, src + "/backend")
from app import substitutions
res = {}
for c in map(json.loads, open(cases)):
    res[c["case"]] = substitutions.suggest(c["missing"], c["candidates"])
json.dump(res, open(out, "w"), indent=1)
print(sum(v is not None for v in res.values()), "of", len(res), "cases got a suggestion ->", out)
