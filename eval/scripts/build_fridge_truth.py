"""Test 8: turn the fridge lists into the answer key.

usage: python build_fridge_truth.py [--photos eval/data/fridge] [--out eval/data/fridge_truth.json]

Reads each fridge-NN.txt (see eval/data/fridge/README.md) and maps every line
to a Forkcast ingredient with the app's matcher. Lines it can't map, or maps
doubtfully, are printed: fix them by hand in the JSON (the "as_written" lists
keep the original words) before the first scanner run, never after.

Needs the Epicure weights (HF_HOME) for the matcher. Makes no API calls.
"""

import argparse
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "backend"))

from app import embeddings  # noqa: E402
from app.normalize import Normalizer  # noqa: E402


def read_list(path: Path) -> dict[str, list[str]]:
    parts: dict[str, list[str]] = {"visible": [], "hidden": []}
    part = "visible"
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        if line.startswith("#"):
            part = "hidden" if "hidden" in line.lower() else "visible"
            continue
        parts[part].append(line)
    return parts


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--photos", type=Path, default=REPO / "eval" / "data" / "fridge")
    ap.add_argument("--out", type=Path, default=REPO / "eval" / "data" / "fridge_truth.json")
    args = ap.parse_args()

    normalizer = Normalizer(embeddings.vocabulary())
    photos = []
    for txt in sorted(args.photos.glob("fridge-*.txt")):
        image = next((p.name for p in args.photos.glob(txt.stem + ".*") if p.suffix.lower() != ".txt"), None)
        if image is None:
            print(f"{txt.name}: no photo next to it, skipped")
            continue
        written = read_list(txt)
        entry = {"file": image, "as_written": written}
        for part, lines in written.items():
            mapped = []
            for line in lines:
                c = normalizer.match(line)
                print(f"  {image} {part:<7} {line!r:<30} -> {c}")
                if c and c not in mapped:
                    mapped.append(c)
            entry[part] = mapped
        photos.append(entry)
    args.out.write_text(json.dumps({"photos": photos}, indent=2, ensure_ascii=False) + "\n")
    print(f"\n{len(photos)} photos written to {args.out}. Check every line above by hand.")


if __name__ == "__main__":
    main()
