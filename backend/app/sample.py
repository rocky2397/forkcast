"""Sample history for the README screenshots and GIF only (D43).

Two made-up people with six weeks of weigh-ins and logged days, generated
from a fixed seed, so the same history comes out every time and ends on the
day it is generated:

  lose  a woman losing weight at the steady pace: mostly days on target in a
        deficit, two weekend surpluses, one maintenance day, one forgotten day,
        weight falling about 0.42 kg a week (the plan, 0.75% of her weight,
        says about 0.53: on track)
  gain  a man gaining at the steady pace: mostly days on target in a surplus,
        one big day over target, one forgotten day, weight rising about
        0.25 kg a week (the plan, 0.5% of his weight, says about 0.34: on track)

Each persona's seed is one whose measured pace (D41) lands within 0.06 kg a
week of the true one: with half a kilo of daily swing, three weeks of a slow
gain can measure as nearly flat, which is real but makes a confusing example.

Realistic, not perfect: weigh-ins swing by about half a kilo, days scatter
around the target, and no day falls under the minimum (the screenshots
shouldn't make that look normal). The last five days are on target, so the
streak shows. This is sample data, used only by ops/screenshots.sh; the public demo and
real kitchens never get it.
"""

import random
import sqlite3
from datetime import datetime, timedelta

from . import goals

PERSONAS = {
    "lose": {
        "profile": {"sex": "f", "age": 31, "height_cm": 170, "activity": "moderate",
                    "goal": "cut", "goal_weight_kg": 64.0, "pace": "steady"},
        "start_kg": 73.5, "kg_per_week": -0.42,
        "surplus_days": (9, 16), "maintenance_days": (12,), "forgotten_days": (6,), "over_days": (),
        "seed": 5,
    },
    "gain": {
        "profile": {"sex": "m", "age": 24, "height_cm": 182, "activity": "active",
                    "goal": "bulk", "goal_weight_kg": 72.0, "pace": "steady"},
        "start_kg": 66.0, "kg_per_week": 0.25,
        "surplus_days": (), "maintenance_days": (10,), "forgotten_days": (7,), "over_days": (12,),
        "seed": 20,
    },
}
DAYS = 42
MEALS = (("Breakfast", 8, 0.25), ("Lunch", 13, 0.35), ("Dinner", 19, 0.40))


def _stamp(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%d %H:%M:%S")


def seed_history(con: sqlite3.Connection, persona: str, now: datetime, days: int = DAYS, seed: int | None = None,
                 upto: int | None = None) -> dict:
    """Replace the profile goal, weigh-ins and past days with the persona's.

    now is UTC; today's own meals are left alone. Returns the profile written.

    upto keeps only the first upto days of the same history, on the same
    dates: the README's "the plan redraws itself" strip shows one person at
    weeks 1, 3 and 6, each screenshot taken with the app's clock set to the
    day after the last day kept (backend/scripts/serve_for_screenshots.py).
    The history is generated in full either way, so the days kept are the
    same days, not a new person.
    """
    p = PERSONAS[persona]
    rnd = random.Random(f"{persona}-{p['seed'] if seed is None else seed}")
    upto = days if upto is None else max(1, min(upto, days))
    skipped = days - upto  # the last days of the full history, not written
    today = now.date()
    as_of = today - timedelta(days=skipped)  # the day after the last day kept

    # Weigh-ins: most mornings, about half a kilo of day-to-day swing.
    con.execute("DELETE FROM weight_log")
    weigh_ins = []
    for ago in range(days, 0, -1):
        if rnd.random() < 0.6 or ago in (days, 1):
            kg = p["start_kg"] + p["kg_per_week"] * (days - ago) / 7 + rnd.gauss(0, 0.35)
            when = datetime.combine(today - timedelta(days=ago), datetime.min.time()) + timedelta(hours=6, minutes=rnd.randint(0, 50))
            weigh_ins.append((when, round(kg, 1)))
    kept = [(w, kg) for w, kg in weigh_ins if w.date() < as_of]
    con.executemany("INSERT INTO weight_log (logged_at, weight_kg) VALUES (?, ?)", [(_stamp(w), kg) for w, kg in kept])

    from .weight import trend  # the same smoothing the app uses
    # Days are generated against the full history's targets, so the days kept
    # are identical whatever upto is; the profile weight is where the trend is.
    full = dict(p["profile"], weight_kg=round(trend(weigh_ins)[-1], 1))
    profile = dict(p["profile"], weight_kg=round(trend(kept)[-1], 1))
    con.execute("DELETE FROM profile")
    con.execute(
        """INSERT INTO profile (id, sex, age, height_cm, weight_kg, activity, goal, goal_weight_kg, pace)
           VALUES (1, :sex, :age, :height_cm, :weight_kg, :activity, :goal, :goal_weight_kg, :pace)""",
        profile,
    )

    target = goals.targets(full)
    burn = goals.burn(full)
    con.execute("DELETE FROM meal_log WHERE date(logged_at) < ?", (now.date().isoformat(),))
    con.execute("DELETE FROM day_check")
    for ago in range(days, 0, -1):
        day = today - timedelta(days=ago)
        if ago in p["forgotten_days"]:
            kcal, meals = target["calories"] * 0.35, MEALS[:1]
        elif ago in p["surplus_days"]:
            kcal, meals = burn + rnd.uniform(180, 380), MEALS
        elif ago in p["over_days"]:  # a big day: over target, breaks the streak
            kcal, meals = target["calories"] * 1.22, MEALS
        elif ago in p["maintenance_days"]:
            kcal, meals = burn + rnd.uniform(-60, 60), MEALS
        else:  # on target, the last five days for sure
            spread = 0.06 if ago <= 5 else 0.09
            kcal, meals = target["calories"] * (1 + rnd.uniform(-spread, spread)), MEALS
        protein = target["protein_g"] * rnd.uniform(0.85, 1.05) * kcal / target["calories"]
        if ago <= skipped:  # after the day this history stops (randomness already drawn)
            continue
        share_total = sum(s for _, _, s in meals)
        for name, hour, share in meals:
            k = share / share_total
            con.execute(
                "INSERT INTO meal_log (logged_at, name, calories, protein_g, carbs_g, fat_g) VALUES (?, ?, ?, ?, ?, ?)",
                (_stamp(datetime.combine(day, datetime.min.time()) + timedelta(hours=hour, minutes=rnd.randint(0, 40))),
                 name, round(kcal * k), round(protein * k), round(target["carbs_g"] * k), round(target["fat_g"] * k)),
            )
        if ago not in p["forgotten_days"]:
            con.execute("INSERT INTO day_check (day, complete) VALUES (?, 1)", (day.isoformat(),))
    con.commit()
    return profile
