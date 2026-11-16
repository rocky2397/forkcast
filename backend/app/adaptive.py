"""What you really burn, learned from your own meals and weigh-ins (D45).

Every target starts from a formula (Mifflin-St Jeor x activity, goals.py),
which for one person is often 10% or more off: a few hundred kcal a day,
about the size of the whole deficit. Forkcast already has what it needs to
correct it: what you ate, which days were complete (D42), and how your
weight moved (D41). If you ate 2,000 kcal a day and your weight stayed
level, you burn about 2,000, whatever the formula said.

Over the last WINDOW_DAYS:

  measured burn = average intake on complete days
                  - weight change per day x 7,700 kcal per kg

The weight change is a straight-line fit through the raw weigh-ins, as for
the pace (D41). The measured burn is only as good as the data, so it is
blended with the formula by how much each can be trusted: the formula is
taken as about FORMULA_SD_SHARE off for a person, the measurement by its own
statistical error (weigh-in noise around the line, how many days the
weigh-ins span, how much daily intake varies). Two weeks of data move the
estimate about halfway; four weeks most of the way.

Guardrails: nothing until there are MIN_COMPLETE_DAYS complete days and
weigh-ins spanning MIN_SPAN_DAYS; never more than MAX_SHIFT from the formula,
because a log that misses snacks makes the burn look lower than it is, and
the daily minimum (D39) applies as before. Only complete days count:
a forgotten day says nothing about what you ate.
"""

import math
import sqlite3
from collections.abc import Mapping
from datetime import datetime, timedelta

from . import goals, progress

WINDOW_DAYS = 28
MIN_COMPLETE_DAYS = 10
MIN_SPAN_DAYS = 12
MIN_WEIGH_INS = 6
FORMULA_SD_SHARE = 0.10  # a formula is commonly about 10% off for one person
WEIGHT_NOISE_FLOOR_KG = 0.3  # never trust the fit more than this much daily swing allows
MAX_SHIFT = 0.15  # the learned burn stays within 15% of the formula


def estimate(formula: float, intake: list[float], weigh_ins: list[tuple[float, float]]) -> dict:
    """Blend the formula with what the data says.

    intake: kcal of each complete day in the window. weigh_ins: (day, kg),
    day counted from the window's start.
    """
    span = (weigh_ins[-1][0] - weigh_ins[0][0]) if len(weigh_ins) >= 2 else 0.0
    out = {
        "formula": round(formula),
        "burn": round(formula),
        "measured": None,
        "trust": 0.0,
        "limited": False,
        "complete_days": len(intake),
        "needed_days": MIN_COMPLETE_DAYS,
        "weigh_in_days": round(span),
        "needed_span": MIN_SPAN_DAYS,
        "window_days": WINDOW_DAYS,
    }
    if len(intake) < MIN_COMPLETE_DAYS or len(weigh_ins) < MIN_WEIGH_INS or span < MIN_SPAN_DAYS:
        return out

    n = len(weigh_ins)
    mx = sum(x for x, _ in weigh_ins) / n
    my = sum(y for _, y in weigh_ins) / n
    sxx = sum((x - mx) ** 2 for x, _ in weigh_ins)
    slope = sum((x - mx) * (y - my) for x, y in weigh_ins) / sxx  # kg per day
    resid = math.sqrt(sum((y - (my + slope * (x - mx))) ** 2 for x, y in weigh_ins) / max(n - 2, 1))
    slope_se = max(resid, WEIGHT_NOISE_FLOOR_KG) / math.sqrt(sxx)

    k = len(intake)
    mean_in = sum(intake) / k
    sd_in = math.sqrt(sum((c - mean_in) ** 2 for c in intake) / max(k - 1, 1))
    measured = mean_in - slope * goals.KCAL_PER_KG
    measured_se = math.hypot(slope_se * goals.KCAL_PER_KG, sd_in / math.sqrt(k))

    formula_sd = FORMULA_SD_SHARE * formula
    trust = formula_sd**2 / (formula_sd**2 + measured_se**2)
    blended = formula + trust * (measured - formula)
    low, high = formula * (1 - MAX_SHIFT), formula * (1 + MAX_SHIFT)
    final = min(max(blended, low), high)
    return out | {
        "burn": round(final),
        "measured": round(measured),
        "trust": round(trust, 2),
        "limited": final != blended,
    }


def learn(con: sqlite3.Connection, profile: Mapping, tz_minutes: int = 0) -> dict:
    """The estimate from this kitchen's last WINDOW_DAYS (today left out)."""
    formula = goals.formula_burn(profile)
    today = progress.local_today(tz_minutes)
    start = today - timedelta(days=WINDOW_DAYS)
    # Complete days are judged against the formula's targets, so the estimate
    # never feeds back into which days count.
    target = float(goals.targets(public(profile))["calories"])
    rows = progress._daily_rows(con, start, tz_minutes)
    checks = progress._checks(con, start)
    intake = []
    for i in range(WINDOW_DAYS):
        d = (start + timedelta(days=i)).isoformat()
        r = rows.get(d)
        if r is None:
            continue
        kcal = float(r["calories"])
        if progress.day_status(kcal, target, formula, 0.0, checks.get(d)) != "not_logged":
            intake.append(kcal)

    origin = datetime.combine(start, datetime.min.time())
    weigh_ins = []
    for r in con.execute("SELECT logged_at, weight_kg FROM weight_log ORDER BY logged_at, id"):
        when = datetime.strptime(r["logged_at"], "%Y-%m-%d %H:%M:%S") + timedelta(minutes=tz_minutes)
        if start <= when.date() < today:
            weigh_ins.append(((when - origin).total_seconds() / 86400.0, float(r["weight_kg"])))
    return estimate(formula, intake, weigh_ins)


def profile_with_burn(con: sqlite3.Connection, tz_minutes: int = 0) -> tuple[dict | None, dict | None]:
    """The profile, with the learned burn in burn_kcal once there is one, and
    the estimate itself (for the explanation on screen)."""
    row = con.execute("SELECT * FROM profile WHERE id = 1").fetchone()
    if row is None:
        return None, None
    profile = dict(row)
    est = learn(con, profile, tz_minutes)
    if est["measured"] is not None:
        profile["burn_kcal"] = est["burn"]
    return profile, est


def public(profile: Mapping) -> dict:
    """The profile as saved, without the learned burn."""
    return {k: profile[k] for k in profile.keys() if k != "burn_kcal"}
