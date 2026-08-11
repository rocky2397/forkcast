"""Split the combined dev database into a read-only corpus and user data (D15).

The corpus (~110 MB of recipes) is identical for every deployment and ships
inside the container image; the user tables are a few KB that have to survive
redeploys on a persistent disk.

Non-destructive: reads the source DB and writes new files. The original keeps
working locally as a single file — connect() only uses corpus.db when it
exists at the configured path.

    python backend/scripts/split_corpus.py                       # -> data/corpus.db
    python backend/scripts/split_corpus.py --user-db data/user.db  # also seed user data
"""

import argparse
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.db import CORPUS_SCHEMA, USER_SCHEMA  # noqa: E402

CORPUS_TABLES = ["recipes", "recipe_ingredients"]
USER_TABLES = ["inventory", "meal_log", "products", "profile"]


def _copy(src: Path, dest: Path, schema: str, tables: list[str]) -> None:
    if dest.exists():
        dest.unlink()
    dest.parent.mkdir(parents=True, exist_ok=True)

    con = sqlite3.connect(dest)
    con.executescript(schema)
    con.execute("ATTACH DATABASE ? AS src", (str(src),))
    for table in tables:
        con.execute(f"INSERT INTO main.{table} SELECT * FROM src.{table}")
        n = con.execute(f"SELECT COUNT(*) FROM main.{table}").fetchone()[0]
        print(f"  {table:<20}{n:>9,} rows")
    con.commit()
    con.execute("DETACH DATABASE src")
    con.execute("VACUUM")  # compact, and drop the free pages the copy left
    con.close()
    print(f"  -> {dest}  ({dest.stat().st_size / 1e6:.0f} MB)\n")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--source", type=Path, default=Path("data/forkcast.db"))
    ap.add_argument("--corpus-db", type=Path, default=Path("data/corpus.db"))
    ap.add_argument(
        "--user-db",
        type=Path,
        help="also write the user tables to this file (to seed a fresh disk)",
    )
    args = ap.parse_args()

    if not args.source.is_file():
        sys.exit(f"no such database: {args.source}")

    print(f"corpus  <- {args.source}")
    _copy(args.source, args.corpus_db, CORPUS_SCHEMA, CORPUS_TABLES)

    if args.user_db:
        print(f"user    <- {args.source}")
        _copy(args.source, args.user_db, USER_SCHEMA, USER_TABLES)


if __name__ == "__main__":
    main()
