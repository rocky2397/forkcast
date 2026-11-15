"""Stage 3: does Forkcast's taste ranking know what a real person likes?

usage: python run_taste.py <forkcast_checkout> <kaggle_dir> <corpus.db> <users.json> <dev|test> <out.json>

Replays real food.com users. Each user's earliest 70% of ratings becomes
their cooking history in the app's own meal log (5 stars = liked,
3 stars or fewer = disliked, 4 stars = cooked without a rating), dated so
that the day of their first hidden rating is today. The app's own, unchanged
taste code then scores recipes: whatever the checkout has (taste_profile from
D31 on, the taste_vector centroid before it, so older commits stay
reproducible). Two questions are asked about the hidden 30%:

  next   Does it pick the recipes they went on to rate out of 100 random
         recipes? Share of (hidden, random) pairs ranked the right way round.
  loved  Among the hidden recipes, does it put the 5-star ones above the
         ones they gave 3 stars or fewer? Share of such pairs ranked right.

50% is a coin flip. Each score is averaged per user, so heavy raters don't
dominate, with a 95% interval from resampling users. Baselines that ignore
the person:
  popular  how many ratings the recipe has from everyone outside this split
  crowd    the recipe's average stars from everyone outside this split
  average  closeness to the average recipe (the same maths as taste, but
           with everyone's cooking instead of yours)
"""
import hashlib
import json
import random
import sqlite3
import sys
from collections import defaultdict
from datetime import date, datetime, timezone

import numpy as np

src, raw_dir, corpus, users_file, split, out = sys.argv[1:7]
sys.path.insert(0, src + "/backend")
from app import taste  # noqa: E402

from taste_data import corpus_ids, split_history, user_ratings  # noqa: E402

N_RANDOM = 100
BOOT = 2000
TODAY = datetime.now(timezone.utc).date()


def liked(stars: int):
    return 1 if stars == 5 else 0 if stars <= 3 else None


def pair_share(pos: list[float], neg: list[float]) -> float:
    """Share of (pos, neg) pairs with pos ranked above neg; ties count half."""
    p = np.asarray(pos)[:, None]
    n = np.asarray(neg)[None, :]
    return float(((p > n) + 0.5 * (p == n)).mean())


def interval(values: np.ndarray, rng: np.random.Generator) -> list[float]:
    idx = rng.integers(0, len(values), size=(BOOT, len(values)))
    means = values[idx].mean(axis=1)
    return [round(float(np.percentile(means, 2.5)) * 100, 1), round(float(np.percentile(means, 97.5)) * 100, 1)]


frozen = json.load(open(users_file))
chosen = set(frozen[split])
ids = corpus_ids(raw_dir, corpus)
users = user_ratings(raw_dir, ids)

# Baselines come only from people outside this split.
count: dict[int, int] = defaultdict(int)
stars_sum: dict[int, int] = defaultdict(int)
for u, rs in users.items():
    if u in chosen:
        continue
    for _, rid, s in rs:
        count[rid] += 1
        stars_sum[rid] += s
total = sum(count.values())
mean_stars = sum(stars_sum.values()) / total


def crowd(rid: int) -> float:
    return stars_sum[rid] / count[rid] if count[rid] else mean_stars


con = sqlite3.connect(f"file:{corpus}?mode=ro", uri=True)
con.row_factory = sqlite3.Row
con.execute("CREATE TEMP TABLE meal_log (recipe_id INTEGER, liked INTEGER, logged_at TEXT)")

# The average recipe, for the "average" baseline.
canon: dict[int, list[str]] = defaultdict(list)
for r in con.execute("SELECT recipe_id, canonical FROM recipe_ingredients WHERE canonical IS NOT NULL"):
    canon[r["recipe_id"]].append(r["canonical"])
vecs = {rid: v for rid, cs in canon.items() if (v := taste.recipe_vector(cs)) is not None}
avg = np.mean(list(vecs.values()), axis=0)
avg /= np.linalg.norm(avg)
all_ids = [r[0] for r in con.execute("SELECT id FROM recipes")]


def average(rid: int) -> float:
    v = vecs.get(rid)
    return float(v @ avg) if v is not None else 0.0


methods = ["forkcast", "popular", "crowd", "average"]
scores = {"next": defaultdict(list), "loved": defaultdict(list)}
no_profile = 0
for u in sorted(chosen, key=int):
    history, hidden = split_history(users[u])
    # Replay at the moment of the first hidden rating: that day becomes today,
    # so the app's 30-day fading sees the same ages the person had then.
    now = date.fromisoformat(hidden[0][0])
    con.execute("DELETE FROM temp.meal_log")
    con.executemany(
        "INSERT INTO temp.meal_log VALUES (?, ?, ?)",
        [(rid, liked(s), (TODAY - (now - date.fromisoformat(d))).isoformat()) for d, rid, s in history],
    )
    if hasattr(taste, "taste_profile"):
        vec = taste.taste_profile(con)
    else:
        vec, _ = taste.taste_vector(con)
    if vec is None:
        no_profile += 1
        continue

    seen = {rid for _, rid, _ in users[u]}
    rng = random.Random(int(hashlib.sha256(f"{frozen['seed']}:{u}".encode()).hexdigest(), 16))
    randoms = []
    while len(randoms) < N_RANDOM:
        rid = rng.choice(all_ids)
        if rid not in seen and rid not in randoms:
            randoms.append(rid)
    hidden_ids = [rid for _, rid, _ in hidden]
    fk = taste.score_recipes(con, list(set(hidden_ids + randoms)), vec)
    by = {
        "forkcast": fk.get,
        "popular": lambda r: count[r],
        "crowd": crowd,
        "average": average,
    }
    for m in methods:
        f = by[m]
        scores["next"][m].append(pair_share([f(r) for r in hidden_ids], [f(r) for r in randoms]))
        loved = [f(rid) for _, rid, s in hidden if s == 5]
        not_loved = [f(rid) for _, rid, s in hidden if s <= 3]
        if loved and not_loved:
            scores["loved"][m].append(pair_share(loved, not_loved))

boot = np.random.default_rng(frozen["seed"])
report = {"split": split, "users": len(chosen), "no_taste_profile": no_profile}
for test, per in scores.items():
    block = {"users": len(per["forkcast"])}
    for m in methods:
        v = np.asarray(per[m])
        block[m] = {
            "pct": round(float(v.mean()) * 100, 1),
            "interval": interval(v, boot),
            "users_above_coin_flip_pct": round(float((v > 0.5).mean()) * 100, 1),
        }
    fk = np.asarray(per["forkcast"])
    for m in methods[1:]:
        d = fk - np.asarray(per[m])
        block[f"forkcast_minus_{m}"] = {"pts": round(float(d.mean()) * 100, 1), "interval": interval(d, boot)}
    report[test] = block

json.dump(report, open(out, "w"), indent=1)
print(json.dumps(report, indent=1))
