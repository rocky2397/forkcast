"""Re-run only the matcher on a stage 4 run: same model output, current matcher.

usage: python rematch_vision.py <in.jsonl> <out.jsonl>

Lets a matcher change be judged on exactly the proposals the model already
made, without calling the model again.
"""
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "backend"))

from app import embeddings, normalize  # noqa: E402

n = normalize.Normalizer(embeddings.vocabulary())
with open(sys.argv[2], "w") as out:
    for line in open(sys.argv[1]):
        r = json.loads(line)
        for i in r.get("items", []):
            i["canonical"] = normalize.packaged(n, i["name"])
        out.write(json.dumps(r, ensure_ascii=False) + "\n")
