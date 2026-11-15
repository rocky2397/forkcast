"""Streaks, day tracking and the weekly recap (D40).

Every logged day is put in one class, measured against what you burn (TDEE),
not against the target, so the counts say what happened whatever the goal:

  deficit       more than MAINTENANCE_BAND kcal below what you burn
  maintenance   within MAINTENANCE_BAND kcal of it
  surplus       more than MAINTENANCE_BAND kcal above it
  below_minimum under your daily minimum (resting burn, and 1,200 / 1,500 kcal)
  not_logged    less than half of the target logged: probably forgotten

The streak counts days *on target* (within TARGET_BAND of your daily target):
consistency, never "less". A day below your minimum is not on target, so
eating far too little can't build a streak. A not-logged day neither breaks
nor extends it, and today only counts once it is on target.

Days are local days: the client sends its UTC offset. Past days are judged
against the current profile.

D42: the user can say a day's log is complete or not ("Done for today?"). A
confirmed day is never "not logged", however little is in it; a day marked
incomplete always is. Without an answer the half-the-target rule decides.
The recap adds the week's average energy balance (eaten minus burned, over
logged days only) next to the plan's, with a rough kg estimate.
"""

from collections.abc import Mapping
from datetime import date, datetime, timedelta, timezone
import sqlite3

from . import goals

MAINTENANCE_BAND = 100.0  # kcal either side of what you burn
TARGET_BAND = 0.10  # on target: within 10% of the daily target
NOT_LOGGED_SHARE = 0.5  # under half the target logged: probably incomplete
PROTEIN_MET_SHARE = 0.9
STRIP_DAYS = 14
TOTAL_DAYS = 30
RECAP_DAYS = 7


def local_today(tz_minutes: int) -> date:
    return (datetime.now(timezone.utc) + timedelta(minutes=tz_minutes)).date()


def day_status(calories: float, target: float, burn: float, minimum: float, check: int | None = None) -> str:
    if check == 0 or (check is None and calories < NOT_LOGGED_SHARE * target):
        return "not_logged"
    if calories < minimum:
        return "below_minimum"
    if calories < burn - MAINTENANCE_BAND:
        return "deficit"
    if calories > burn + MAINTENANCE_BAND:
        return "surplus"
    return "maintenance"


def on_target(calories: float, target: float, status: str) -> bool:
    return status not in ("not_logged", "below_minimum") and abs(calories - target) <= TARGET_BAND * target


def _daily_rows(con: sqlite3.Connection, start: date, tz_minutes: int) -> dict[str, dict]:
    """Totals per local day from start on, with each recipe's first-ever cook day."""
    shift = f"{int(tz_minutes):+d} minutes"
    rows = con.execute(
        """SELECT date(ml.logged_at, ?) AS day,
                  SUM(COALESCE(ml.calories, r.calories, 0))   AS calories,
                  SUM(COALESCE(ml.protein_g, r.protein_g, 0)) AS protein_g,
                  COUNT(*)                                    AS meals,
                  SUM(ml.recipe_id IS NOT NULL)               AS cooked,
                  SUM(COALESCE(ml.liked, 0) = 1)              AS liked
           FROM meal_log ml LEFT JOIN recipes r ON r.id = ml.recipe_id
           WHERE date(ml.logged_at, ?) >= ?
           GROUP BY day""",
        (shift, shift, start.isoformat()),
    ).fetchall()
    return {r["day"]: dict(r) for r in rows}


def _checks(con: sqlite3.Connection, start: date) -> dict[str, int]:
    rows = con.execute("SELECT day, complete FROM day_check WHERE day >= ?", (start.isoformat(),)).fetchall()
    return {r["day"]: int(r["complete"]) for r in rows}


def set_check(con: sqlite3.Connection, day: str, complete: bool | None) -> None:
    """Record the user's answer to "Done for today?" (None clears it)."""
    if complete is None:
        con.execute("DELETE FROM day_check WHERE day = ?", (day,))
    else:
        con.execute(
            "INSERT INTO day_check (day, complete) VALUES (?, ?) ON CONFLICT(day) DO UPDATE SET complete = excluded.complete",
            (day, int(complete)),
        )
    con.commit()


def _new_recipes(con: sqlite3.Connection, start: date, tz_minutes: int) -> int:
    """Recipes cooked for the first time ever on or after start."""
    shift = f"{int(tz_minutes):+d} minutes"
    return con.execute(
        """SELECT COUNT(*) FROM (
               SELECT recipe_id, MIN(date(logged_at, ?)) AS first_day
               FROM meal_log WHERE recipe_id IS NOT NULL GROUP BY recipe_id)
           WHERE first_day >= ?""",
        (shift, start.isoformat()),
    ).fetchone()[0]


def summary(con: sqlite3.Connection, profile: Mapping, tz_minutes: int = 0) -> dict:
    today = local_today(tz_minutes)
    target_row = goals.targets(profile)
    target = float(target_row["calories"])
    protein_target = float(target_row["protein_g"])
    burn = goals.burn(profile)
    minimum = goals.minimum_calories(profile)
    first = today - timedelta(days=TOTAL_DAYS)
    rows = _daily_rows(con, first, tz_minutes)
    checks = _checks(con, first)

    def day(d: date) -> dict:
        r = rows.get(d.isoformat())
        kcal = float(r["calories"]) if r else 0.0
        check = checks.get(d.isoformat()) if r else None  # an empty day can't be "complete"
        status = day_status(kcal, target, burn, minimum, check)
        in_progress = d == today and check is None and not on_target(kcal, target, status)
        return {
            "date": d.isoformat(),
            "calories": round(kcal),
            "protein_g": round(float(r["protein_g"])) if r else 0,
            "meals": int(r["meals"]) if r else 0,
            "confirmed": None if check is None else bool(check),
            "status": "today" if in_progress else status,
            "on_target": on_target(kcal, target, status),
        }

    # Streak: back from today; today counts only once on target.
    streak = 0
    d = today
    while d >= first:
        info = day(d)
        if info["on_target"]:
            streak += 1
        elif info["status"] not in ("not_logged", "today"):
            break
        d -= timedelta(days=1)

    past = [day(today - timedelta(days=i)) for i in range(1, TOTAL_DAYS + 1)]
    totals = {k: sum(1 for x in past if x["status"] == k)
              for k in ("deficit", "maintenance", "surplus", "below_minimum", "not_logged")}
    totals["on_target"] = sum(1 for x in past if x["on_target"])
    totals["days"] = TOTAL_DAYS

    week = [today - timedelta(days=i) for i in range(RECAP_DAYS)]
    week_rows = [rows.get(x.isoformat()) for x in week]
    week_days = [day(x) for x in week]
    logged = [x for x in week_days if x["status"] not in ("not_logged", "today") or x["on_target"]]
    recap = {
        "days": RECAP_DAYS,
        "cooked": sum(int(r["cooked"]) for r in week_rows if r),
        "typed": sum(int(r["meals"]) - int(r["cooked"]) for r in week_rows if r),
        "new_recipes": _new_recipes(con, week[-1], tz_minutes),
        "liked": sum(int(r["liked"]) for r in week_rows if r),
        "days_logged": len(logged),
        "days_on_target": sum(1 for x in week_days if x["on_target"]),
        "protein_days": sum(1 for x in logged if x["protein_g"] >= PROTEIN_MET_SHARE * protein_target),
    }
    # D42: the week's energy balance, eaten minus burned, over logged days only.
    balance_days = [x for x in logged if x["status"] not in ("not_logged", "today")]
    plan = goals.plan(profile)
    planned = (target - burn) if plan is None else (plan["calories"] - plan["burn"])
    if balance_days:
        avg = sum(x["calories"] - burn for x in balance_days) / len(balance_days)
        recap["balance"] = {
            "days": len(balance_days),
            "avg_per_day": round(avg),
            "planned_per_day": round(planned),
            "est_kg": round(avg * len(balance_days) / goals.KCAL_PER_KG, 2),
        }
    else:
        recap["balance"] = None
    return {
        "today": today.isoformat(),
        "target": round(target),
        "burn": round(burn),
        "minimum": round(minimum),
        "streak": streak,
        "strip": [day(today - timedelta(days=i)) for i in range(STRIP_DAYS - 1, -1, -1)],
        "totals": totals,
        "recap": recap,
    }
