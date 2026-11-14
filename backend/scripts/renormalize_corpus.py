#!/usr/bin/env python
"""Re-apply the current normalizer to an existing recipe corpus (D24).

A matcher fix leaves the imported corpus wrong: "cherry tomatoes" was stored as
`cherry` in 530 rows, so ranking, substitutions and taste learning all read it
as the fruit. Re-importing from the source dataset takes far longer than
rewriting the affected rows, and only `recipe_ingredients.canonical` and the
`recipes.matched_frac` derived from it can change.

Dry run by default; `--apply` writes, after copying the file next to itself.

    python backend/scripts/renormalize_corpus.py data/corpus.db
    python backend/scripts/renormalize_corpus.py data/corpus.db --apply

Note both local databases carry the recipe tables: `connect()` attaches
corpus.db but SQLite resolves unqualified names against main first, so the dev
app reads recipes out of forkcast.db. Pass each file you intend to fix.
"""

import argparse
import shutil
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import embeddings  # noqa: E402
from app.normalize import Normalizer  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("db", type=Path, help="database holding the recipe tables")
    ap.add_argument("--apply", action="store_true", help="write the changes")
    ap.add_argument("--limit", type=int, default=25, help="how many moves to print")
    args = ap.parse_args()

    if not args.db.is_file():
        print(f"no such database: {args.db}")
        return 1

    normalizer = Normalizer(embeddings.vocabulary())
    con = sqlite3.connect(args.db)
    con.row_factory = sqlite3.Row

    rows = con.execute(
        "SELECT raw, canonical, COUNT(*) AS n FROM recipe_ingredients GROUP BY raw, canonical"
    ).fetchall()
    moves = [
        (r["n"], r["raw"], r["canonical"], new)
        for r in rows
        if (new := normalizer.match(r["raw"])) != r["canonical"]
    ]
    moves.sort(reverse=True, key=lambda m: m[0])

    affected_rows = sum(n for n, *_ in moves)
    print(f"{args.db}: {len(moves)} distinct strings, {affected_rows} ingredient rows would change")
    for n, raw, old, new in moves[: args.limit]:
        print(f"  {n:6}x  {raw!r:44} {old} -> {new}")
    if len(moves) > args.limit:
        print(f"  ... {len(moves) - args.limit} more")

    # Only a null <-> value flip can move matched_frac, which gates the feed.
    null_flips = sum(n for n, _, old, new in moves if (old is None) != (new is None))
    print(f"\n{null_flips} rows cross the matched/unmatched boundary (matched_frac is recomputed)")

    if not args.apply:
        print("\ndry run; pass --apply to write")
        return 0

    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    backup = args.db.with_name(f"{args.db.stem}-prenorm-{stamp}{args.db.suffix}")
    print(f"\nbacking up to {backup.name} ...")
    shutil.copy2(args.db, backup)

    with con:
        con.executemany(
            "UPDATE recipe_ingredients SET canonical = ? WHERE raw = ?",
            [(new, raw) for _, raw, _, new in moves],
        )
        con.execute(
            """UPDATE recipes SET matched_frac = (
                   SELECT CAST(SUM(ri.canonical IS NOT NULL) AS REAL) / COUNT(*)
                   FROM recipe_ingredients ri WHERE ri.recipe_id = recipes.id
               )
               WHERE id IN (SELECT recipe_id FROM recipe_ingredients WHERE raw IN (%s))"""
            % ",".join("?" * len(moves)),
            [raw for _, raw, _, _ in moves],
        )
    con.execute("VACUUM")
    full = con.execute("SELECT COUNT(*) c FROM recipes WHERE matched_frac = 1.0").fetchone()["c"]
    total = con.execute("SELECT COUNT(*) c FROM recipes").fetchone()["c"]
    print(f"done. fully matched recipes: {full}/{total} ({full / total:.1%})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
