#!/usr/bin/env python3
"""After a deploy: is the public demo running what the repo says, and does it work?

    python3 ops/check_live.py            # check the demo now
    python3 ops/check_live.py --wait 900 # first wait (up to 15 min) for a new build

Checks, in order:

  1. The Space: the latest upload is the build that's running (not still
     building or failed), and its Dockerfile pins the same Forkcast commit and
     recipe corpus as deploy/huggingface/Dockerfile here.
  2. /health: up, the ingredient vocabulary loaded, and the commit and corpus
     it reports are the pinned ones.
  3. /api/session: demo mode with saved kitchens, scanning and usage totals on.
  4. The frontend: the page and every script and stylesheet it loads.
  5. A visit in a throwaway kitchen, through the API: the seeded demo kitchen,
     the recipe feed and a recipe, worth buying, a profile with a goal weight,
     a typed meal, a weigh-in, Done for today, progress. Then the kitchen is
     deleted, and the check confirms it is gone.
  6. /stats loads.

Photo and label scanning are left out on purpose: each scan costs money and
counts against the demo's daily cap.

Every request sends X-Forkcast-Check, so the check never shows up in the
demo's public usage totals. Standard library only; exits 1 if anything fails.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import date
from pathlib import Path

DEMO = "https://rockyyyy2397-forkcast.hf.space"
SPACE = "rockyyyy2397/forkcast"
DOCKERFILE = Path(__file__).resolve().parents[1] / "deploy" / "huggingface" / "Dockerfile"
KITCHEN_HEADER = "X-Forkcast-Kitchen"
CHECK = {"X-Forkcast-Check": "1", "User-Agent": "forkcast-live-check"}
SLOW_SECONDS = 5.0

failures: list[str] = []
timings: list[tuple[float, str]] = []


def ok(what: str) -> None:
    print(f"  ok    {what}")


def fail(what: str) -> None:
    print(f"  FAIL  {what}")
    failures.append(what)


def note(what: str) -> None:
    print(f"  note  {what}")


def check(condition: bool, what: str) -> bool:
    (ok if condition else fail)(what)
    return condition


def request(url: str, method: str = "GET", body=None, headers=None, timeout: float = 60):
    """(status, headers, body bytes); never raises for an HTTP error status."""
    data = json.dumps(body).encode() if body is not None else None
    h = dict(CHECK) | (headers or {}) | ({"content-type": "application/json"} if data else {})
    req = urllib.request.Request(url, data=data, method=method, headers=h)
    began = time.perf_counter()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            status, rh, raw = r.status, r.headers, r.read()
    except urllib.error.HTTPError as e:
        status, rh, raw = e.code, e.headers, e.read()
    timings.append((time.perf_counter() - began, f"{method} {url.split('?')[0]}"))
    return status, rh, raw


def get_json(url: str, **kw):
    status, headers, raw = request(url, **kw)
    try:
        return status, headers, json.loads(raw or b"null")
    except json.JSONDecodeError:
        return status, headers, None


def pins(dockerfile_text: str) -> dict:
    out = {}
    for name in ("FORKCAST_COMMIT", "CORPUS_URL"):
        m = re.search(rf"^ARG {name}=(\S+)", dockerfile_text, re.M)
        out[name] = m.group(1) if m else None
    return out


def corpus_tag(url: str | None) -> str | None:
    return url.rstrip("/").split("/")[-2] if url else None


# ---- 1. The Space ------------------------------------------------------------

def space_info(space: str) -> dict:
    status, _, info = get_json(f"https://huggingface.co/api/spaces/{space}")
    if status != 200 or not info:
        raise RuntimeError(f"Hugging Face API answered {status}")
    return info


def check_space(space: str, url: str, wait: float) -> dict:
    print(f"\nThe Space ({space})")
    deadline = time.time() + wait
    woke = False
    while True:
        info = space_info(space)
        rt = info.get("runtime") or {}
        stage = rt.get("stage")
        current = rt.get("sha") == info.get("sha")
        if stage == "RUNNING" and current:
            break
        if stage in ("SLEEPING", "PAUSED") and not woke:
            note(f"the Space is {stage.lower()}; a visit wakes it")
            request(url + "/", timeout=120)
            woke = True
        if "ERROR" in (stage or "") or time.time() >= deadline:
            fail(f"the latest upload isn't running: stage {stage}, "
                 f"{'running the latest upload' if current else 'running an older upload'}")
            return {}
        time.sleep(10)
    ok(f"running the latest upload ({info['sha'][:7]})")
    status, _, raw = request(f"https://huggingface.co/spaces/{space}/raw/main/Dockerfile")
    if not check(status == 200, "its Dockerfile can be read"):
        return {}
    there, here = pins(raw.decode()), pins(DOCKERFILE.read_text())
    check(there["FORKCAST_COMMIT"] == here["FORKCAST_COMMIT"],
          f"it pins Forkcast {str(there['FORKCAST_COMMIT'])[:7]}, as the repo does ({str(here['FORKCAST_COMMIT'])[:7]})")
    check(there["CORPUS_URL"] == here["CORPUS_URL"],
          f"it pins corpus {corpus_tag(there['CORPUS_URL'])}, as the repo does ({corpus_tag(here['CORPUS_URL'])})")
    return here


# ---- 2-4. Health, session, frontend --------------------------------------------

def check_health(url: str, expected: dict) -> None:
    print("\nHealth")
    status, _, h = get_json(url + "/health", timeout=120)
    if not check(status == 200 and h and h.get("status") == "ok", f"/health answers ok ({status})"):
        return
    check(h.get("vocab_size", 0) >= 1000, f"ingredient vocabulary loaded ({h.get('vocab_size')} names)")
    want_commit, want_corpus = expected.get("FORKCAST_COMMIT"), corpus_tag(expected.get("CORPUS_URL"))
    if "commit" not in h:
        note("the running build doesn't report its commit (built before /health did)")
    elif want_commit:
        check(h["commit"] == want_commit, f"running commit {h['commit'][:7]} is the pinned one")
    if "corpus" in h and want_corpus:
        check(h["corpus"] == want_corpus, f"running corpus {h['corpus']} is the pinned one")


def check_session(url: str) -> None:
    print("\nDemo settings")
    status, _, s = get_json(url + "/api/session")
    if not check(status == 200 and s is not None, f"/api/session answers ({status})"):
        return
    for key, what in (("demo", "demo mode"), ("saved", "saved kitchens"),
                      ("scans", "photo scanning (a key is set)"), ("stats", "usage totals")):
        check(s.get(key) is True, f"{what} on")


def check_frontend(url: str) -> None:
    print("\nThe app's page")
    status, _, raw = request(url + "/")
    page = raw.decode(errors="replace")
    if not check(status == 200 and "<div id=\"root\"" in page, f"the page loads ({status})"):
        return
    assets = sorted(set(re.findall(r'(?:src|href)="(/assets/[^"]+)"', page)))
    check(bool(assets), f"it loads {len(assets)} scripts and stylesheets")
    for a in assets:
        st, _, _ = request(url + a)
        check(st == 200, f"{a} ({st})")


# ---- 5. A visit ----------------------------------------------------------------

def check_visit(url: str) -> None:
    print("\nA visit in a throwaway kitchen")
    status, headers, day = get_json(url + "/api/day?tz=0")
    kitchen = headers.get(KITCHEN_HEADER) if headers else None
    if not check(status == 200 and bool(kitchen), f"a new kitchen ({status})"):
        return
    k = {KITCHEN_HEADER: kitchen}
    try:
        # D57: a visitor sets up their own profile and starts with an empty day.
        check(day is not None and day["meals"] == [] and day.get("targets") is None,
              f"it starts empty, without a profile ({len((day or {}).get('meals', []))} meals)")
        _, _, inv = get_json(url + "/api/inventory", headers=k)
        check(len((inv or {}).get("items", [])) >= 5, f"and the demo kitchen ({len((inv or {}).get('items', []))} ingredients)")

        _, _, feed = get_json(url + "/api/recipes/cookable?max_missing=1&limit=5", headers=k)
        recipes = (feed or {}).get("recipes", [])
        if check(bool(recipes), f"the recipe feed lists recipes ({len(recipes)})"):
            first = recipes[0]
            st, _, r = get_json(f"{url}/api/recipes/{first['id']}", headers=k)
            check(st == 200 and (r or {}).get("name") == first["name"], f"a recipe opens: {first['name']}")
        st, _, _ = request(url + "/api/shopping", headers=k)
        check(st == 200, f"worth buying answers ({st})")

        # D61: one typed line, several foods with their amounts.
        _, _, line = get_json(url + "/api/foods/line?q=" + urllib.parse.quote("2 Eier, Cappuccino"), headers=k)
        parts = [(p["food"]["canonical"], p.get("count")) for p in (line or {}).get("parts", [])]
        check(parts[:1] == [("egg", 2)] and (line or {}).get("dishes") in (["cappuccino"], ["Cappuccino"]),  # D67 lower-cased it
              f"a typed line reads amounts and dishes ({len(parts)} parts)")

        profile = {"sex": "f", "age": 31, "height_cm": 170, "weight_kg": 72, "activity": "moderate",
                   "goal": "maintain", "goal_weight_kg": 66, "pace": "steady"}
        st, _, p = get_json(url + "/api/profile?tz=0", method="PUT", body=profile, headers=k)
        plan = (p or {}).get("plan") or {}
        check(st == 200 and plan.get("direction") == "lose" and plan.get("calories", 0) > 1000,
              f"a goal weight gives a plan ({plan.get('calories')} kcal a day, {plan.get('weeks')} weeks)")
        check(((p or {}).get("burn") or {}).get("formula", 0) > 1000, "and says what you burn")

        before = (day or {}).get("totals", {}).get("calories", 0)
        st, _, _ = request(url + "/api/meals", method="POST", headers=k,
                           body={"name": "Live check", "calories": 420, "protein_g": 18, "carbs_g": 40, "fat_g": 12})
        _, _, after = get_json(url + "/api/day?tz=0", headers=k)
        added = round((after or {}).get("totals", {}).get("calories", 0) - before)
        check(st == 200 and added == 420, f"a typed meal counts ({added} kcal added)")

        st, _, w = get_json(url + "/api/weight?tz=0", method="POST", body={"weight_kg": 71.8}, headers=k)
        check(st == 200 and (w or {}).get("trend_kg") == 71.8, f"a weigh-in ({(w or {}).get('trend_kg')} kg)")
        today = (after or {}).get("date") or date.today().isoformat()
        st, _, _ = request(f"{url}/api/days/{today}/check", method="PUT", body={"complete": True}, headers=k)
        check(st == 200, f"Done for today ({st})")
        st, _, pr = get_json(url + "/api/progress?tz=0", headers=k)
        check(st == 200 and isinstance(((pr or {}).get("progress") or {}).get("streak"), int), f"progress ({st})")
    finally:
        st, _, _ = request(url + "/api/demo/kitchen", method="DELETE", headers=k)
        check(st == 200, f"the kitchen is deleted ({st})")
        _, again, _ = request(url + "/api/inventory", headers=k)
        check(again.get(KITCHEN_HEADER) != kitchen, "and gone: its id now gets a fresh kitchen")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--url", default=DEMO)
    ap.add_argument("--space", default=SPACE, help="Hugging Face Space id; '' to skip the Space checks")
    ap.add_argument("--wait", type=float, default=0, help="seconds to wait for a new build to be running")
    args = ap.parse_args()
    url = args.url.rstrip("/")
    print(f"Checking {url}")
    try:
        expected = check_space(args.space, url, args.wait) if args.space else pins(DOCKERFILE.read_text())
        check_health(url, expected)
        check_session(url)
        check_frontend(url)
        check_visit(url)
        print("\nUsage totals")
        st, _, _ = request(url + "/stats")
        check(st == 200, f"/stats loads ({st})")
    except Exception as e:  # a network error or an answer the check can't read
        fail(f"stopped: {e!r}")
    slowest = max(timings, default=(0.0, ""))
    print(f"\nSlowest request: {slowest[0]:.1f} s ({slowest[1]})")
    if slowest[0] > SLOW_SECONDS:
        note(f"slower than {SLOW_SECONDS:.0f} s: a cold start, or worth a look")
    if failures:
        print(f"\n{len(failures)} check(s) failed.")
        return 1
    print("\nAll checks passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
