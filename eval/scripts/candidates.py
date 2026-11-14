"""Shortlist vocabulary names for each string to speed up labelling.

A deliberately naive retriever (shared words + character trigrams). It is NOT
Forkcast's matcher and never calls it, so labels stay blind to predictions.
The labeller may pick any vocabulary name, not only shortlisted ones.
"""
import json, re, sys
vocab = [l.strip() for l in open(sys.argv[2]) if l.strip()]
def words(s): return set(re.findall(r"[a-z]+", s.lower().replace("_", " ")))
def grams(s):
    s = " " + re.sub(r"[^a-z ]", " ", s.lower().replace("_", " ")) + " "
    return {s[i:i+3] for i in range(len(s) - 2)}
V = [(n, words(n), grams(n)) for n in vocab]
seen = set()
for line in open(sys.argv[1]):
    r = json.loads(line)
    if r["text"] in seen: continue
    seen.add(r["text"])
    w, g = words(r["text"]), grams(r["text"])
    score = lambda x: 2 * len(w & x[1]) + len(g & x[2]) / (len(g | x[2]) or 1)
    top = [n for n, *_ in sorted(V, key=score, reverse=True)[:12]]
    print(json.dumps({"text": r["text"], "candidates": top}))
