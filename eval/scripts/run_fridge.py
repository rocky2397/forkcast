"""Test 8: can a photo of a whole fridge fill the kitchen list?

usage: python run_fridge.py <model> <out.jsonl> --budget 0.50 [--effort low]
           [--repeats 3] [--limit N]
           [--truth eval/data/fridge_truth.json] [--photos eval/data/fridge]

Runs Forkcast's own scanner (backend/app/vision.py, unchanged prompt and
schema, only the model swapped) on the fridge photos named in the answer key,
`repeats` times each, and sends every proposal through the app's own matcher,
exactly as the scan route does. Each row records what the model said, what the
matcher made of it, tokens and time. Scoring is in score_fridge.py.

The answer key (eval/data/fridge_truth.json) is written before any scanner
output is seen; see eval/data/fridge/README.md.

Every call is billed: the aicook test split (51 photos) with two runs on
Haiku 4.5, Haiku 5.5 and Sonnet 5.5 is about 300 calls, roughly $2 at
November 2026 list prices (see score_fridge.py). Try one photo per model
first (--limit 1).

--budget is a hard cap in dollars for this output file, earlier rows
included, priced from the tokens each response reports. A call only starts if
what is spent, plus what the calls already running may cost, plus this one
stays under the cap; a call is assumed to cost as much as the dearest one so
far (before any, a generous 6,000 tokens in and 2,000 out). A model without a
price in score_fridge.PRICE isn't run. If the first three calls all
fail (a refused or unknown model), the run stops.
Needs ANTHROPIC_API_KEY in the environment and the Epicure weights (HF_HOME)
for the matcher. Rows already in out.jsonl are skipped, so a run resumes.
"""

import argparse
import json
import mimetypes
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "backend"))

from app import embeddings, normalize, vision  # noqa: E402
from app.normalize import Normalizer  # noqa: E402
from score_fridge import PRICE  # noqa: E402  (same folder)


def dollars(model: str, tokens_in: int, tokens_out: int) -> float:
    pin, pout = PRICE[model]
    return (tokens_in * pin + tokens_out * pout) / 1e6


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("model")
    ap.add_argument("out", type=Path)
    ap.add_argument("--effort", default="-", help='"-" sends none (the model default)')
    ap.add_argument("--repeats", type=int, default=3)
    ap.add_argument("--truth", type=Path, default=REPO / "eval" / "data" / "fridge_truth.json")
    ap.add_argument("--photos", type=Path, default=REPO / "eval" / "data" / "fridge")
    ap.add_argument("--limit", type=int, default=0, help="only the first N photos")
    ap.add_argument("--budget", type=float, required=True, help="hard cap in dollars for this file")
    args = ap.parse_args()
    if args.model not in PRICE:
        sys.exit(f"no price for {args.model}: add it to score_fridge.PRICE first")

    photos = [p["file"] for p in json.loads(args.truth.read_text())["photos"]]
    if args.limit:
        photos = photos[: args.limit]
    todo = [(f, r) for f in photos for r in range(args.repeats)]
    spent = 0.0
    if args.out.exists():
        rows = [json.loads(line) for line in args.out.read_text().splitlines() if line.strip()]
        done = {(row["photo"], row["run"]) for row in rows}
        todo = [t for t in todo if t not in done]
        spent = sum(dollars(args.model, r.get("input_tokens", 0), r.get("output_tokens", 0)) for r in rows)
    print(f"{len(photos)} photos x {args.repeats} runs, {len(todo)} calls to make, "
          f"${spent:.3f} of ${args.budget:.2f} already spent", flush=True)

    normalizer = Normalizer(embeddings.vocabulary())
    options = {"output_config": {"effort": args.effort}} if args.effort != "-" else {}

    # Record each response's usage without changing the scanner.
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
    state = {"spent": spent, "stopped": "", "results": [], "running": 0,
             "per_call": dollars(args.model, 6000, 2000)}

    def run(task: tuple[str, int]) -> None:
        name, n = task
        with lock:
            # Wait while running calls might use up the room; stop once
            # nothing is running and there is still no room.
            while not state["stopped"] and state["spent"] + (state["running"] + 1) * state["per_call"] > args.budget:
                if state["running"] == 0:
                    state["stopped"] = f"budget of ${args.budget:.2f} reached"
                else:
                    lock.wait()
            if state["stopped"]:
                return
            state["running"] += 1
        path = args.photos / name
        media = mimetypes.guess_type(path.name)[0] or "image/jpeg"
        began = time.perf_counter()
        usage.value = None
        record = {"photo": name, "run": n, "model": args.model, "effort": args.effort}
        try:
            result = vision.extract_items(path.read_bytes(), media, args.model, **options)
            record["items"] = [
                {"name": i.name, "quantity": i.quantity, "confidence": i.confidence,
                 "canonical": normalize.packaged(normalizer, i.name)}  # as the scan route
                for i in result.items
            ]
        except Exception as e:  # recorded, scored as a failed scan
            record["error"] = f"{type(e).__name__}: {e}"[:300]
        record["seconds"] = round(time.perf_counter() - began, 2)
        if usage.value is not None:
            record["input_tokens"] = usage.value.input_tokens
            record["output_tokens"] = usage.value.output_tokens
        with lock:
            state["running"] -= 1
            cost = dollars(args.model, record.get("input_tokens", 0), record.get("output_tokens", 0))
            state["spent"] += cost
            if len(state["results"]) == 0 and cost:
                state["per_call"] = cost  # the first real cost replaces the guess
            state["per_call"] = max(state["per_call"], cost)
            state["results"].append("error" not in record)
            if len(state["results"]) >= 3 and not any(state["results"][:3]):
                state["stopped"] = state["stopped"] or "the first three calls failed: " + record.get("error", "")
            with args.out.open("a") as f:
                f.write(json.dumps(record, ensure_ascii=False) + "\n")
            lock.notify_all()

    with ThreadPoolExecutor(max_workers=4) as pool:
        for k, _ in enumerate(pool.map(run, todo), 1):
            if k % 10 == 0:
                print(f"  {k}/{len(todo)}", flush=True)
    print(f"{state['stopped'] or 'done'}; ${state['spent']:.3f} spent in this file", flush=True)


if __name__ == "__main__":
    main()
