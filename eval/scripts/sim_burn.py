"""Does learning the burn from meals and weigh-ins beat the formula? (D45)

Simulated people, because real ones with weeks of honest logs and a known
true burn don't exist in any public dataset. Each person:

  - a random body and activity level; the formula gives their burn, but
    their true burn is off from it by a random 0-15% either way (uniform),
  - eats around a target (a deficit, maintenance or a surplus) with 12%
    day-to-day scatter, and logs 85% of days completely; the rest are
    forgotten or half-logged and left out, as the app does,
  - weighs in on about 60% of mornings; weight moves by energy balance
    (7,700 kcal per kg) plus water swings that carry over from day to day
    (AR(1), about 0.4 kg spread), which is harder than independent noise.

The estimator under test is the app's own adaptive.estimate. Reported: how
far the formula and the learned burn are from the true burn after 2, 3 and
4 weeks, with honest logs and with logs that miss 10% of what was eaten.

Two errors, in kcal a day:

  burn error  how far the burn estimate is from the true burn
  plan error  how far the person's real eating is from what their plan
              needs, if they eat to a target of burn estimate minus the
              planned deficit. For honest logs it equals the burn error.
              For someone whose log always misses 10%, eating to a logged
              target of T means really eating T / 0.9, so a burn that looks
              10% low is exactly what puts their real eating on plan.

Usage: python eval/scripts/sim_burn.py [people]   (default 2000, ~seconds)
"""

import random
import statistics
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "backend"))
from app import adaptive, goals  # noqa: E402

ACTIVITIES = list(goals.ACTIVITY_FACTORS)


def person(rnd: random.Random) -> dict:
    sex = rnd.choice("fm")
    height = rnd.gauss(166 if sex == "f" else 179, 7)
    return {"sex": sex, "age": rnd.randint(20, 60), "height_cm": height,
            "weight_kg": rnd.uniform(55, 105) if sex == "f" else rnd.uniform(65, 120),
            "activity": rnd.choice(ACTIVITIES)}


def simulate(rnd: random.Random, days: int, underlog: float) -> tuple[float, float, dict]:
    p = person(rnd)
    formula = goals.formula_burn(p)
    true_burn = formula * (1 + rnd.uniform(-0.15, 0.15))
    change = rnd.choice((-500, -300, 0, 0, 250))  # the plan: kcal a day vs burn
    target = formula + change
    weight = p["weight_kg"]
    water = 0.0
    intake, weigh_ins = [], []
    for day in range(days):
        ate = max(target * rnd.gauss(1, 0.12), 800)
        water = 0.6 * water + rnd.gauss(0, 0.32)
        if rnd.random() < 0.6:
            weigh_ins.append((day + 0.25, weight + water))
        if rnd.random() < 0.85:
            intake.append(ate * (1 - underlog))
        weight += (ate - true_burn) / goals.KCAL_PER_KG
    est = adaptive.estimate(formula, intake, weigh_ins)
    return true_burn, formula, est, change


def report(n: int, days: int, underlog: float, seed: int = 45) -> dict:
    rnd = random.Random(f"{seed}-{days}-{underlog}")
    f_err, l_err, better, learned, limited, near = [], [], 0, 0, 0, []
    f_plan, l_plan = [], []
    for _ in range(n):
        true_burn, formula, est, change = simulate(rnd, days, underlog)
        needed = true_burn + change  # real kcal a day the plan needs
        f_plan.append(abs((formula + change) / (1 - underlog) - needed))
        l_plan.append(abs((est["burn"] + change) / (1 - underlog) - needed))
        fe = abs(formula - true_burn)
        le = abs(est["burn"] - true_burn)
        f_err.append(fe)
        l_err.append(le)
        better += le < fe
        learned += est["measured"] is not None
        limited += est["limited"]
        if fe / true_burn < 0.03:  # the formula was already right
            near.append(le - fe)
    q = lambda xs, p: statistics.quantiles(xs, n=10)[p - 1]  # noqa: E731
    return {
        "days": days, "underlog": underlog, "learned": learned / n,
        "formula_median": statistics.median(f_err), "learned_median": statistics.median(l_err),
        "formula_p90": q(f_err, 9), "learned_p90": q(l_err, 9),
        "closer": better / n, "limited": limited / n,
        "formula_plan": statistics.median(f_plan), "learned_plan": statistics.median(l_plan),
        "formula_plan_p90": q(f_plan, 9), "learned_plan_p90": q(l_plan, 9),
        "worse_when_formula_right": statistics.median(near) if near else 0.0,
    }


def main() -> None:
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 2000
    print(f"{n} simulated people per row; medians unless marked, kcal a day\n")
    print("| Logs | Weeks | Learned yet | Burn error: formula | Burn error: learned | Plan error: formula | Plan error: learned | Plan error, worst 10%: formula | Plan error, worst 10%: learned | Held at the 15% limit |")
    print("|---|---|---|---|---|---|---|---|---|---|")
    for underlog in (0.0, 0.10):
        for days in (14, 21, 28):
            r = report(n, days, underlog)
            print(f"| {'honest' if underlog == 0 else 'miss 10%'} | {days // 7} | {r['learned']:.0%} | "
                  f"{r['formula_median']:.0f} | {r['learned_median']:.0f} | {r['formula_plan']:.0f} | "
                  f"{r['learned_plan']:.0f} | {r['formula_plan_p90']:.0f} | {r['learned_plan_p90']:.0f} | "
                  f"{r['limited']:.0%} |")
    r = report(n, 28, 0.0)
    print(f"\nPeople whose formula was already within 3%: the learned burn is "
          f"{r['worse_when_formula_right']:+.0f} kcal further off (median) after 4 weeks.")


if __name__ == "__main__":
    main()
