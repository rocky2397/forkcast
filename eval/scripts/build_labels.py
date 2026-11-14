"""Join blind labels (one TSV line per distinct text, in candidates order) onto
every sampled row. Fails loudly if a label names something outside the vocabulary.

usage: python build_labels.py [sample.jsonl candidates.jsonl labels.tsv out.jsonl]
(defaults: the stage-1 development set)"""
import json, sys
SAMPLE, CANDS, LABELS, OUT = sys.argv[1:5] if len(sys.argv) == 5 else (
    "data/strings.jsonl", "labeling/candidates.jsonl", "labeling/labels.tsv", "data/strings_labeled.jsonl")
vocab = {l.strip() for l in open("data/vocab.txt") if l.strip()}
texts = [json.loads(l)["text"] for l in open(CANDS)]
labels = {}
for line in open(LABELS):
    idx, gold, flag = (line.rstrip("\n").split("\t") + ["", ""])[:3]
    g = gold.split()
    bad = [x for x in g if x not in vocab]
    assert not bad, f"line {idx}: not in vocabulary: {bad}"
    lab = {"gold": g}
    if flag == "multi": lab["multi"] = True
    elif flag.startswith("unsure:"): lab["unsure"] = True; lab["note"] = flag[7:]
    labels[texts[int(idx) - 1]] = lab
assert len(labels) == len(texts), (len(labels), len(texts))
n = 0
with open(OUT, "w") as out:
    for line in open(SAMPLE):
        r = json.loads(line); out.write(json.dumps({**r, **labels[r["text"]]}) + "\n"); n += 1
print(n, "rows labelled;", sum(1 for l in labels.values() if l.get("unsure")), "distinct texts flagged unsure;",
      sum(1 for l in labels.values() if not l["gold"]), "with empty gold")
