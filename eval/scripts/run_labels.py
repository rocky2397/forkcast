"""Stage 5: does the label reader get the macros right?

usage: python run_labels.py <products.json> <image cache dir> <out.jsonl> [--limit N]

Runs Forkcast's label reader (backend/app/vision.py extract_product, unchanged
prompt and schema, the model the app uses) on photos of German nutrition
tables from Open Food Facts, and records what it read next to the values the
database holds for the same product.

products.json is the frozen sample made by sample_labels.py: barcode, the
nutrition photo's URL, and the database's kcal, protein, carbs and fat per
100 g (with "<" modifiers). Photos are downloaded once into the cache dir and
never committed (CC BY-SA, Open Food Facts contributors). Rows already in
out.jsonl are skipped, so an interrupted run resumes.

Needs Anthropic credentials in the environment.
"""

import argparse
import json
import sys
import threading
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "backend"))

from app import vision  # noqa: E402

AGENT = "ForkcastEval/1.0 (research eval)"


def fetch(url: str, dest: Path) -> bytes:
    if not dest.exists():
        req = urllib.request.Request(url, headers={"User-Agent": AGENT})
        with urllib.request.urlopen(req, timeout=60) as r:
            dest.write_bytes(r.read())
        time.sleep(0.2)  # be gentle with the image server
    return dest.read_bytes()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("products", type=Path)
    ap.add_argument("cache", type=Path)
    ap.add_argument("out", type=Path)
    ap.add_argument("--limit", type=int, default=0)
    args = ap.parse_args()

    products = json.loads(args.products.read_text())
    if args.limit:
        products = products[: args.limit]
    done = set()
    if args.out.exists():
        done = {json.loads(line)["code"] for line in args.out.read_text().splitlines() if line.strip()}
    todo = [p for p in products if p["code"] not in done]
    print(f"{len(products)} products, {len(done)} already done, {len(todo)} to run", flush=True)
    args.cache.mkdir(parents=True, exist_ok=True)

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

    def run(p: dict) -> None:
        record = {"code": p["code"], "name": p["name"], "truth": p["truth"], "model": vision.MODEL}
        try:
            raw = fetch(p["image"], args.cache / f"{p['code']}.jpg")
        except Exception as e:
            record["error"] = f"download: {e}"[:200]
            raw = None
        if raw is not None:
            began = time.perf_counter()
            usage.value = None
            try:
                scan = vision.extract_product(raw, "image/jpeg")
                per = scan.per_100g
                record["read"] = {
                    "calories": per.calories if per else None,
                    "protein_g": per.protein_g if per else None,
                    "carbs_g": per.carbs_g if per else None,
                    "fat_g": per.fat_g if per else None,
                }
                record["barcode_read"] = scan.barcode
            except Exception as e:  # scored as a failure
                record["error"] = f"{type(e).__name__}: {e}"[:300]
            record["seconds"] = round(time.perf_counter() - began, 2)
            if usage.value is not None:
                record["input_tokens"] = usage.value.input_tokens
                record["output_tokens"] = usage.value.output_tokens
        with lock:
            with args.out.open("a") as f:
                f.write(json.dumps(record, ensure_ascii=False) + "\n")

    with ThreadPoolExecutor(max_workers=4) as pool:
        for n, _ in enumerate(pool.map(run, todo), 1):
            if n % 25 == 0:
                print(f"  {n}/{len(todo)}", flush=True)
    print("done", flush=True)


if __name__ == "__main__":
    main()
