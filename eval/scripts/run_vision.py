"""Stage 4: does the photo scanner name groceries correctly?

usage: python run_vision.py <GroceryStoreDataset dir> <model> <effort|-> <out.jsonl>
           [--per-class N] [--split test] [--limit N] [--budget 0.25]

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

--budget is a hard cap in dollars for this output file (earlier rows
included), as in run_fridge.py: a call only starts if what is spent, plus
what the running calls may cost, plus this one stays under it.
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
from app import normalize  # noqa: E402
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
    ap.add_argument("--budget", type=float, default=0.0, help="hard cap in dollars; 0 means none")
    args = ap.parse_args()
    from score_vision import PRICE  # same folder

    def dollars(r: dict) -> float:
        pin, pout = PRICE[args.model]
        return (r.get("input_tokens", 0) * pin + r.get("output_tokens", 0) * pout) / 1e6

    if args.budget and args.model not in PRICE:
        sys.exit(f"no price for {args.model} in score_vision.PRICE")

    rows = sample(args.dataset, args.split, args.per_class)
    if args.limit:
        rows = rows[: args.limit]
    done = set()
    spent = 0.0
    if args.out.exists():
        old = [json.loads(line) for line in args.out.read_text().splitlines() if line.strip()]
        done = {r["photo"] for r in old}
        spent = sum(dollars(r) for r in old) if args.budget else 0.0
    todo = [r for r in rows if r[0] not in done]
    print(f"{len(rows)} photos, {len(done)} already done, {len(todo)} to run", flush=True)

    normalizer = Normalizer(embeddings.vocabulary())
    # The app's own scan matching: packaged() from D35 on, plain match before.
    match = (lambda name: normalize.packaged(normalizer, name)) if hasattr(normalize, "packaged") else normalizer.match
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
    lock = threading.Condition()
    args.out.parent.mkdir(parents=True, exist_ok=True)
    state = {"spent": spent, "running": 0, "stopped": "",
             "per_call": dollars({"input_tokens": 6000, "output_tokens": 2000}) if args.budget else 0.0}

    def run(row: tuple[str, str]) -> None:
        path, label = row
        if args.budget:
            with lock:
                while not state["stopped"] and state["spent"] + (state["running"] + 1) * state["per_call"] > args.budget:
                    if state["running"] == 0:
                        state["stopped"] = f"budget of ${args.budget:.2f} reached"
                    else:
                        lock.wait()
                if state["stopped"]:
                    return
                state["running"] += 1
        raw = (args.dataset / "dataset" / path).read_bytes()
        began = time.perf_counter()
        usage.value = None
        record = {"photo": path, "label": label, "model": args.model, "effort": args.effort}
        try:
            result = vision.extract_items(raw, "image/jpeg", args.model, **options)
            record["items"] = [
                {"name": i.name, "quantity": i.quantity, "confidence": i.confidence,
                 "canonical": match(i.name)}
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
            if args.budget:
                state["running"] -= 1
                cost = dollars(record)
                state["spent"] += cost
                state["per_call"] = cost if cost and state["per_call"] > 10 * cost else max(state["per_call"], cost)
                lock.notify_all()
            with args.out.open("a") as f:
                f.write(json.dumps(record, ensure_ascii=False) + "\n")

    with ThreadPoolExecutor(max_workers=6) as pool:
        for n, _ in enumerate(pool.map(run, todo), 1):
            if n % 25 == 0:
                print(f"  {n}/{len(todo)}", flush=True)
    print(f"{state['stopped'] or 'done'}" + (f"; ${state['spent']:.3f} spent in this file" if args.budget else ""), flush=True)


if __name__ == "__main__":
    main()
