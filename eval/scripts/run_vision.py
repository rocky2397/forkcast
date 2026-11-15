"""Stage 4: does the photo scanner name groceries correctly?

usage: python run_vision.py <GroceryStoreDataset dir> <model> <effort|-> <out.jsonl>
           [--per-class N] [--split test] [--limit N]

Runs Forkcast's own scanner (backend/app/vision.py, unchanged prompt and
schema) on photos from the Grocery Store Dataset (Klasson et al., WACV 2019,
MIT licence): 5,125 phone photos taken in Swedish grocery stores, 81 kinds of
fruit, vegetables and carton products. Every proposal then goes through the
app's own ingredient matcher, exactly as in the app, and the row records what
the model said, what the matcher made of it, tokens and time.

The sample is the first N photos per class of the chosen split, in file order,
so every model sees the same photos. The answer key is
eval/data/vision_gold.json, written from the vocabulary alone before any
scanner output was seen. Scoring is in score_vision.py.

effort: "-" sends no effort (the model's default); otherwise e.g. "low".
Needs Anthropic credentials in the environment and the Epicure weights
(HF_HOME) for the matcher. Rows already in out.jsonl are skipped, so an
interrupted run resumes.
"""

import argparse
import json
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "backend"))

from app import embeddings, vision  # noqa: E402
from app.normalize import Normalizer  # noqa: E402


def sample(dataset: Path, split: str, per_class: int) -> list[tuple[str, str]]:
    names = {}
    for line in (dataset / "dataset" / "classes.csv").read_text().splitlines()[1:]:
        cols = line.split(",")
        names[int(cols[1])] = cols[0]
    taken: dict[int, int] = {}
    rows = []
    for line in (dataset / "dataset" / f"{split}.txt").read_text().splitlines():
        path, fine, _coarse = (x.strip() for x in line.split(","))
        fine = int(fine)
        if taken.get(fine, 0) < per_class:
            taken[fine] = taken.get(fine, 0) + 1
            rows.append((path, names[fine]))
    return rows


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("dataset", type=Path)
    ap.add_argument("model")
    ap.add_argument("effort")
    ap.add_argument("out", type=Path)
    ap.add_argument("--per-class", type=int, default=5)
    ap.add_argument("--split", default="test")
    ap.add_argument("--limit", type=int, default=0)
    args = ap.parse_args()

    rows = sample(args.dataset, args.split, args.per_class)
    if args.limit:
        rows = rows[: args.limit]
    done = set()
    if args.out.exists():
        done = {json.loads(line)["photo"] for line in args.out.read_text().splitlines() if line.strip()}
    todo = [r for r in rows if r[0] not in done]
    print(f"{len(rows)} photos, {len(done)} already done, {len(todo)} to run", flush=True)

    normalizer = Normalizer(embeddings.vocabulary())
    options = {"output_config": {"effort": args.effort}} if args.effort != "-" else {}

    # Record each response's usage without changing the scanner: wrap the
    # client's parse call, keyed by thread.
    client = vision._client()
    real_parse = client.messages.parse
    usage = threading.local()

    def recording_parse(*a, **kw):
        response = real_parse(*a, **kw)
        usage.value = response.usage
        return response

    client.messages.parse = recording_parse
    lock = threading.Lock()
    args.out.parent.mkdir(parents=True, exist_ok=True)

    def run(row: tuple[str, str]) -> None:
        path, label = row
        raw = (args.dataset / "dataset" / path).read_bytes()
        began = time.perf_counter()
        usage.value = None
        record = {"photo": path, "label": label, "model": args.model, "effort": args.effort}
        try:
            result = vision.extract_items(raw, "image/jpeg", args.model, **options)
            record["items"] = [
                {"name": i.name, "quantity": i.quantity, "confidence": i.confidence,
                 "canonical": normalizer.match(i.name)}
                for i in result.items
            ]
        except Exception as e:  # recorded, scored as a failure
            record["error"] = f"{type(e).__name__}: {e}"[:300]
        record["seconds"] = round(time.perf_counter() - began, 2)
        u = usage.value
        if u is not None:
            record["input_tokens"] = u.input_tokens
            record["output_tokens"] = u.output_tokens
        with lock:
            with args.out.open("a") as f:
                f.write(json.dumps(record, ensure_ascii=False) + "\n")

    with ThreadPoolExecutor(max_workers=6) as pool:
        for n, _ in enumerate(pool.map(run, todo), 1):
            if n % 25 == 0:
                print(f"  {n}/{len(todo)}", flush=True)
    print("done", flush=True)


if __name__ == "__main__":
    main()
