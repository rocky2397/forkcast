#!/usr/bin/env python
"""Show exactly which ingredient strings a normalizer change moves (D24).

The matcher is a pile of heuristics, so "obviously better" rules routinely
make hundreds of strings worse: "last word wins" turns garlic clove into the
spice, "longest match wins" turns bread flour into flour. Nothing here decides
whether a change is good — it prints the moved strings and their row counts so
that judgement has evidence.

Usage, from the repo root:

    # before the change
    python backend/scripts/normalizer_diff.py --save /tmp/before.json

    # after editing normalize.py
    python backend/scripts/normalizer_diff.py --compare /tmp/before.json

Runs over every distinct ingredient string in the corpus, weighted by how many
recipe rows use it.
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import embeddings  # noqa: E402
from app.db import connect  # noqa: E402
from app.normalize import Normalizer  # noqa: E402


def corpus_strings() -> dict[str, int]:
    """Every distinct raw ingredient string -> how many recipe rows use it."""
    with connect() as con:
        return {
            row["raw"]: row["n"]
            for row in con.execute(
                "SELECT raw, COUNT(*) AS n FROM recipe_ingredients GROUP BY raw"
            )
        }


def current_matches(rows: dict[str, int]) -> dict[str, str | None]:
    normalizer = Normalizer(embeddings.vocabulary())
    return {raw: normalizer.match(raw) for raw in rows}


def main() -> int:
    ap = argparse.ArgumentParser()
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--save", metavar="FILE", help="write current matches as a baseline")
    g.add_argument("--compare", metavar="FILE", help="diff current matches against a baseline")
    ap.add_argument("--limit", type=int, default=60, help="how many moved strings to print")
    args = ap.parse_args()

    rows = corpus_strings()
    matches = current_matches(rows)
    print(f"{len(rows)} distinct strings, {sum(rows.values())} recipe rows")

    if args.save:
        Path(args.save).write_text(json.dumps(matches, indent=0, sort_keys=True))
        print(f"baseline written to {args.save}")
        return 0

    before = json.loads(Path(args.compare).read_text())
    moved = sorted(
        (
            (rows.get(raw, 0), raw, old, matches.get(raw))
            for raw, old in before.items()
            if matches.get(raw) != old
        ),
        reverse=True,
    )
    gone = [r for r in matches if r not in before]

    print(f"\n{len(moved)} strings moved, affecting {sum(n for n, *_ in moved)} recipe rows")
    if gone:
        print(f"({len(gone)} strings are new since the baseline and not compared)")
    for n, raw, old, new in moved[: args.limit]:
        print(f"  {n:6}x  {raw!r:44} {old} -> {new}")
    if len(moved) > args.limit:
        print(f"  ... {len(moved) - args.limit} more (raise --limit to see them)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
