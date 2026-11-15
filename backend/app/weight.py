"""Weigh-ins, the weight trend and the projection to the goal weight (D41).

Day-to-day weight swings by a kilo or two with water, salt and digestion, so
single weigh-ins say little. The trend is an exponential moving average with
a time constant of TREND_DAYS (about 10% per day, as in The Hacker's Diet),
weighted by the time between weigh-ins, so irregular weigh-ins work too.

The actual pace is a straight-line fit through the raw weigh-ins of the last
RATE_WINDOW_DAYS, once they span at least MIN_SPAN_DAYS: the fit evens out
the noise, and unlike the trend's slope it doesn't lag (the trend trails a
steady loss, which made people look behind when they weren't). It is compared with the
plan's pace (D39): ahead, on track, behind or stalled, and turned into a goal
date at the actual pace next to the plan's (the plan's date allows for its
pace shrinking with the weight, D44). Losing faster than 1% of body
weight a week is flagged: faster isn't better.

Every weigh-in also sets the profile weight to the trend, so the daily target
and the plan follow the body rather than one morning's scale.
"""

import math
import sqlite3
from collections.abc import Mapping
from datetime import datetime, timedelta

from . import goals
from .progress import local_today

TREND_DAYS = 9.5  # time constant: 1 - exp(-1/9.5) is about 10% a day
RATE_WINDOW_DAYS = 21
MIN_SPAN_DAYS = 7
CHART_DAYS = 84
SAFE_LOSS_SHARE = 0.01  # of body weight per week
KEEP_BAND_KG = 1.0
ON_TRACK = (0.5, 1.5)  # actual pace as a share of the planned pace
STALLED_KG_PER_WEEK = 0.05


def _local(ts: str, tz_minutes: int) -> datetime:
    return datetime.strptime(ts, "%Y-%m-%d %H:%M:%S") + timedelta(minutes=tz_minutes)


def trend(points: list[tuple[datetime, float]]) -> list[float]:
    """The smoothed weight at each weigh-in."""
    out: list[float] = []
    for i, (when, kg) in enumerate(points):
        if i == 0:
            out.append(kg)
            continue
        days = max((when - points[i - 1][0]).total_seconds() / 86400.0, 0.0)
        a = 1.0 - math.exp(-days / TREND_DAYS) if days > 0 else 0.1
        out.append(out[-1] + a * (kg - out[-1]))
    return out


def weekly_rate(points: list[tuple[datetime, float]], smooth: list[float], now: datetime) -> float | None:
    """kg per week, a line through the last few weeks' weigh-ins (None: too little data)."""
    start = now - timedelta(days=RATE_WINDOW_DAYS)
    xs = [((w - start).total_seconds() / 86400.0, kg) for w, kg in points if w >= start]
    if len(xs) < 2 or xs[-1][0] - xs[0][0] < MIN_SPAN_DAYS:
        return None
    mx = sum(x for x, _ in xs) / len(xs)
    my = sum(y for _, y in xs) / len(xs)
    var = sum((x - mx) ** 2 for x, _ in xs)
    if var == 0:
        return None
    slope = sum((x - mx) * (y - my) for x, y in xs) / var  # kg per day
    return slope * 7.0


def current_trend(con: sqlite3.Connection) -> float | None:
    rows = con.execute("SELECT logged_at, weight_kg FROM weight_log ORDER BY logged_at, id").fetchall()
    if not rows:
        return None
    pts = [(datetime.strptime(r["logged_at"], "%Y-%m-%d %H:%M:%S"), float(r["weight_kg"])) for r in rows]
    return trend(pts)[-1]


def summary(con: sqlite3.Connection, profile: Mapping | None, tz_minutes: int = 0) -> dict:
    rows = con.execute("SELECT id, logged_at, weight_kg FROM weight_log ORDER BY logged_at, id").fetchall()
    today = local_today(tz_minutes)
    now = datetime.combine(today, datetime.min.time()) + timedelta(hours=12)
    if not rows:
        return {"entries": [], "trend_kg": None, "rate_kg_per_week": None, "status": None,
                "projection": None, "today": today.isoformat()}
    pts = [(_local(r["logged_at"], tz_minutes), float(r["weight_kg"])) for r in rows]
    smooth = trend(pts)
    rate = weekly_rate(pts, smooth, now)
    first_shown = today - timedelta(days=CHART_DAYS)
    entries = [
        {"id": r["id"], "date": p[0].date().isoformat(), "weight_kg": p[1], "trend_kg": round(t, 2)}
        for r, p, t in zip(rows, pts, smooth)
        if p[0].date() >= first_shown
    ]
    now_kg = smooth[-1]
    out = {
        "today": today.isoformat(),
        "entries": entries,
        "trend_kg": round(now_kg, 1),
        "rate_kg_per_week": None if rate is None else round(rate, 2),
        "status": None,
        "too_fast": rate is not None and rate < -SAFE_LOSS_SHARE * now_kg,
        "projection": None,
    }
    plan = goals.plan(profile) if profile is not None else None
    if plan is None:
        return out
    goal = float(plan["goal_weight_kg"])
    remaining = goal - now_kg
    planned = plan["kg_per_week"]
    plan_date = None
    if plan["direction"] != "keep" and planned > 0:
        share = None if plan["limited"] else plan["pace_share"]
        left = goals.weeks_to_goal(now_kg, goal, planned, share)
        plan_date = today + timedelta(weeks=left) if left is not None else None
    actual_date = None
    if plan["direction"] == "keep" or abs(remaining) < 0.5:
        status = "at_goal" if abs(remaining) <= KEEP_BAND_KG else "drifting"
    elif rate is None:
        status = "not_enough_data"
    else:
        toward = rate if remaining > 0 else -rate  # kg a week in the goal's direction
        ratio = toward / planned if planned > 0 else 0.0
        # Wide bands on purpose: three weeks of normal day-to-day swings put a
        # true 0.5 kg/week anywhere from about 0.25 to 0.75 (simulated), so a
        # narrow band would flip the label for no real reason.
        status = ("ahead" if ratio >= ON_TRACK[1] else "on_track" if ratio >= ON_TRACK[0]
                  else "behind" if toward > STALLED_KG_PER_WEEK else "stalled")
        if toward > STALLED_KG_PER_WEEK:
            actual_date = today + timedelta(weeks=abs(remaining) / toward)
    out["status"] = status
    out["projection"] = {
        "goal_kg": goal,
        "remaining_kg": round(remaining, 1),
        "planned_kg_per_week": planned * (1 if remaining > 0 else -1),
        "plan_date": plan_date.isoformat() if plan_date else None,
        "actual_date": actual_date.isoformat() if actual_date else None,
    }
    return out


def log(con: sqlite3.Connection, weight_kg: float) -> float:
    """Record a weigh-in and move the profile weight to the new trend."""
    con.execute("INSERT INTO weight_log (weight_kg) VALUES (?)", (weight_kg,))
    t = current_trend(con)
    con.execute("UPDATE profile SET weight_kg = ? WHERE id = 1", (round(t, 1),))
    con.commit()
    return t


def remove(con: sqlite3.Connection, entry_id: int) -> None:
    con.execute("DELETE FROM weight_log WHERE id = ?", (entry_id,))
    t = current_trend(con)
    if t is not None:
        con.execute("UPDATE profile SET weight_kg = ? WHERE id = 1", (round(t, 1),))
    con.commit()

