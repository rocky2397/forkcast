"""Shared loading for the stage 3 taste eval.

Joins Kaggle's "Food.com Recipes and User Interactions" (Majumder et al.,
EMNLP 2019) to the corpus. The corpus numbers its recipes 1..N and does not
keep food.com's ids, so a recipe is matched on (name, minutes, n_steps), with
the description breaking the rare tie. Ratings of 0 are reviews without a
star rating and are dropped.

Only RAW_recipes.csv and RAW_interactions.csv are read; neither is
redistributed here (download them from Kaggle, sign-in required).
"""
import collections
import csv
import sqlite3

csv.field_size_limit(10**9)

MIN_RATINGS = 10     # a user needs this many rated corpus recipes
HISTORY_SHARE = 0.7  # the earliest 70% become the cooking history; the rest is hidden


def corpus_ids(raw_dir: str, corpus: str) -> dict[int, int]:
    """food.com recipe id -> corpus recipe id, for unambiguous matches."""
    raw = collections.defaultdict(list)
    with open(f"{raw_dir}/RAW_recipes.csv", newline="") as f:
        for r in csv.DictReader(f):
            raw[(r["name"], r["minutes"], r["n_steps"])].append((int(r["id"]), r["description"]))
    con = sqlite3.connect(f"file:{corpus}?mode=ro", uri=True)
    out = {}
    for cid, name, minutes, n_steps, desc in con.execute(
        "SELECT id, name, minutes, n_steps, description FROM recipes"
    ):
        cands = raw.get((name or "", str(minutes), str(n_steps)), [])
        if len(cands) > 1:
            cands = [c for c in cands if (c[1] or "") == (desc or "")]
        if len(cands) == 1:
            out[cands[0][0]] = cid
    return out


def user_ratings(raw_dir: str, ids: dict[int, int]) -> dict[str, list[tuple[str, int, int]]]:
    """user id -> [(date, corpus recipe id, stars)] sorted by date, corpus recipes only."""
    users = collections.defaultdict(list)
    with open(f"{raw_dir}/RAW_interactions.csv", newline="") as f:
        for r in csv.DictReader(f):
            cid = ids.get(int(r["recipe_id"]))
            if cid is not None and r["rating"] != "0":
                users[r["user_id"]].append((r["date"], cid, int(r["rating"])))
    for v in users.values():
        v.sort()
    return users


def split_history(ratings: list[tuple[str, int, int]]):
    """(history, hidden): the earliest 70% by date, then the rest."""
    cut = int(len(ratings) * HISTORY_SHARE)
    return ratings[:cut], ratings[cut:]
