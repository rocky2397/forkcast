"""Anonymous usage totals for the public demo (D33).

Counts what visitors do, per day, and nothing about who they are:

- **Kept:** daily totals of a fixed list of events (EVENTS), which of
  Forkcast's 1,790 ingredient names were added, which recipe ids were opened
  or cooked, and how many visitors reached each step of the funnel (FUNNEL).
- **How it runs:** per API route (its template, e.g. "GET /api/recipes/{id}",
  never the address asked for), a histogram of response times (TIME_BUCKETS),
  server errors (5xx) and not-found answers (404); and how long each start of
  the app took until it was ready.
- **Never kept:** IP addresses, browser details, times finer than the day,
  anything typed (meal names, unrecognised ingredients), profile values, or
  anything per visitor. The funnel is worked out from each visitor's random
  kitchen id held in memory; only the totals are written.

Totals live in memory and are written to FORKCAST_STATS_DIR as one small JSON
file per day (UTC), every FLUSH_SECONDS and on shutdown. On Hugging Face that
directory is a mounted storage bucket, so it survives restarts. A crash loses
at most a few minutes of counts.

Only active in demo mode (D32) with FORKCAST_STATS_DIR set. Requests from
the post-deploy check (ops/check_live.py, header X-Forkcast-Check) are not
counted: a check is not a visitor.
"""

import json
import logging
import os
import threading
from contextvars import ContextVar
from datetime import datetime, timezone
from pathlib import Path

from . import demo

log = logging.getLogger("forkcast.stats")

FLUSH_SECONDS = 300
# Stages a visitor can reach, in order; "visited" is the new kitchen itself.
FUNNEL = ("visited", "added", "opened", "cooked")
EVENTS = frozenset({
    "ingredient_added", "ingredient_removed",
    "recipe_opened", "recipe_cooked",
    "rated_liked", "rated_not_for_me", "rating_cleared",
    "profile_saved", "meal_typed",
    "photo_scan_tried", "label_scan_tried", "barcode_lookup",
})
# Events whose item is worth counting, and what kind of item it must be.
ITEMS = {"ingredient_added": str, "recipe_opened": int, "recipe_cooked": int}
_MAX_TRACKED = 5000  # kitchens remembered for the funnel before forgetting
# Response-time histogram edges in ms; the last bucket is "slower than 5 s".
TIME_BUCKETS = (10, 25, 50, 100, 250, 500, 1000, 2500, 5000)
_MAX_ROUTES = 60  # the app has about 25; anything beyond is counted as "other"
_MAX_STARTS = 100  # start durations kept per day

# Set by the demo middleware for each request: the visitor's random kitchen id.
current_kitchen: ContextVar[str | None] = ContextVar("current_kitchen", default=None)
# False for the post-deploy check (ops/check_live.py), which sends CHECK_HEADER:
# a check is not a visitor, so it must not show up in the public totals.
CHECK_HEADER = "X-Forkcast-Check"
counting: ContextVar[bool] = ContextVar("counting", default=True)

_lock = threading.Lock()
_days: dict[str, dict] = {}
_dirty: set[str] = set()
_reached: dict[str, set[str]] = {}  # kitchen id -> stages reached today
_reached_day: str | None = None
_vocab: frozenset[str] = frozenset()


def directory() -> Path | None:
    d = os.environ.get("FORKCAST_STATS_DIR")
    return Path(d) if d else None


def enabled() -> bool:
    return demo.enabled() and directory() is not None


def today() -> str:
    return datetime.now(timezone.utc).date().isoformat()


def _empty(day: str) -> dict:
    return {
        "day": day,
        "events": {},
        "funnel": {s: 0 for s in FUNNEL},
        "items": {name: {} for name in ITEMS},
        "timing": {},  # route -> {"buckets": [...], "count": n, "total_ms": x}
        "errors": {"server": {}, "not_found": {}},  # route -> count
        "starts": [],  # seconds from the app starting to being ready
    }


def _day(day: str) -> dict:
    """The in-memory totals for a day, continuing from its file if one exists."""
    if day not in _days:
        data = _empty(day)
        path = directory() / f"{day}.json"
        try:
            saved = json.loads(path.read_text())
            _merge(data, saved)
        except FileNotFoundError:
            pass
        except (OSError, ValueError) as e:
            log.warning("stats: could not read %s: %s", path, e)
        _days[day] = data
    return _days[day]


def _merge(into: dict, other: dict) -> None:
    for k, v in other.get("events", {}).items():
        if k in EVENTS:
            into["events"][k] = into["events"].get(k, 0) + int(v)
    for k, v in other.get("funnel", {}).items():
        if k in FUNNEL:
            into["funnel"][k] += int(v)
    for name, counts in other.get("items", {}).items():
        if name in ITEMS:
            bucket = into["items"][name]
            for item, v in counts.items():
                bucket[item] = bucket.get(item, 0) + int(v)
    for route, t in other.get("timing", {}).items():
        mine = into["timing"].setdefault(route, _new_timing())
        for i, v in enumerate(t.get("buckets", [])[: len(TIME_BUCKETS) + 1]):
            mine["buckets"][i] += int(v)
        mine["count"] += int(t.get("count", 0))
        mine["total_ms"] += float(t.get("total_ms", 0))
    for kind in ("server", "not_found"):
        for route, v in other.get("errors", {}).get(kind, {}).items():
            into["errors"][kind][route] = into["errors"][kind].get(route, 0) + int(v)
    into["starts"] = (into["starts"] + [float(x) for x in other.get("starts", [])])[:_MAX_STARTS]


def _new_timing() -> dict:
    return {"buckets": [0] * (len(TIME_BUCKETS) + 1), "count": 0, "total_ms": 0.0}


def start(vocabulary) -> None:
    """Called at startup: the ingredient names an item may be."""
    global _vocab
    _vocab = frozenset(vocabulary)
    directory().mkdir(parents=True, exist_ok=True)


def _reach(kitchen: str | None, stage: str, day: str) -> None:
    global _reached_day
    if kitchen is None:
        return
    if _reached_day != day or len(_reached) > _MAX_TRACKED:
        _reached.clear()
        _reached_day = day
    stages = _reached.setdefault(kitchen, set())
    if stage not in stages:
        stages.add(stage)
        _day(day)["funnel"][stage] += 1


def visit() -> None:
    """A new demo kitchen, i.e. a new visitor."""
    if not enabled() or not counting.get():
        return
    with _lock:
        day = today()
        _day(day)
        _reach(current_kitchen.get(), "visited", day)
        _dirty.add(day)


def event(name: str, item: str | int | None = None, stage: str | None = None) -> None:
    """Count one event. Unknown names, items and stages are dropped, never stored."""
    if not enabled() or not counting.get() or name not in EVENTS:
        return
    with _lock:
        day = today()
        data = _day(day)
        data["events"][name] = data["events"].get(name, 0) + 1
        kind = ITEMS.get(name)
        if kind is str and isinstance(item, str) and item in _vocab:
            key = item
        elif kind is int and isinstance(item, int) and not isinstance(item, bool) and item > 0:
            key = str(item)
        else:
            key = None
        if key is not None:
            bucket = data["items"][name]
            bucket[key] = bucket.get(key, 0) + 1
        if stage in FUNNEL:
            _reach(current_kitchen.get(), stage, day)
        _dirty.add(day)


def request_done(route: str | None, status: int, ms: float) -> None:
    """Time and outcome of one API request, by route template."""
    if not enabled() or not counting.get():
        return
    with _lock:
        day = today()
        data = _day(day)
        label = route if route and (route in data["timing"] or len(data["timing"]) < _MAX_ROUTES) else "other"
        t = data["timing"].setdefault(label, _new_timing())
        t["buckets"][next((i for i, edge in enumerate(TIME_BUCKETS) if ms <= edge), len(TIME_BUCKETS))] += 1
        t["count"] += 1
        t["total_ms"] += round(ms, 1)
        kind = "server" if status >= 500 else "not_found" if status == 404 else None
        if kind:
            data["errors"][kind][label] = data["errors"][kind].get(label, 0) + 1
        _dirty.add(day)


def started(seconds: float) -> None:
    """One start of the app: seconds until it was ready to answer."""
    if not enabled():
        return
    with _lock:
        day = today()
        data = _day(day)
        if len(data["starts"]) < _MAX_STARTS:
            data["starts"].append(round(seconds, 1))
        _dirty.add(day)


def seconds_since_process_start(fallback_start: float) -> float:
    """Wall time since this process began, including Python's own startup.

    Read from /proc on Linux (where the demo runs); elsewhere, time since
    fallback_start (a time.monotonic() taken early in the app).
    """
    try:
        ticks = int(Path("/proc/self/stat").read_text().rsplit(")", 1)[1].split()[19])
        uptime = float(Path("/proc/uptime").read_text().split()[0])
        return max(0.0, uptime - ticks / os.sysconf("SC_CLK_TCK"))
    except (OSError, ValueError, IndexError):
        import time

        return time.monotonic() - fallback_start


def _percentile_ms(buckets: list[int], share: float) -> int | None:
    """Upper edge of the bucket holding the given share of requests (None: >5 s)."""
    total = sum(buckets)
    if not total:
        return None
    seen = 0
    for i, n in enumerate(buckets):
        seen += n
        if seen >= share * total:
            return TIME_BUCKETS[i] if i < len(TIME_BUCKETS) else None
    return None


def flush() -> None:
    """Write every changed day to its file. Failures are logged and retried later."""
    if not enabled():
        return
    with _lock:
        pending = {day: json.dumps(_days[day], sort_keys=True) for day in _dirty}
        _dirty.clear()
    for day, text in pending.items():
        path = directory() / f"{day}.json"
        try:
            tmp = path.with_name(path.name + ".tmp")
            tmp.write_text(text)
            try:
                os.replace(tmp, path)
            except OSError:  # some bucket mounts can't rename; write in place
                path.write_text(text)
                tmp.unlink(missing_ok=True)
        except OSError as e:
            log.warning("stats: could not write %s: %s", path, e)
            with _lock:
                _dirty.add(day)
        # Old days are final once written; keep only today in memory.
        with _lock:
            if day != today() and day not in _dirty:
                _days.pop(day, None)


def all_days() -> list[dict]:
    """Every day's totals: the files, with today's unsaved counts on top."""
    found: dict[str, dict] = {}
    d = directory()
    if d is not None and d.is_dir():
        for path in sorted(d.glob("????-??-??.json")):
            try:
                data = _empty(path.stem)
                _merge(data, json.loads(path.read_text()))
                found[path.stem] = data
            except (OSError, ValueError):
                continue
    with _lock:
        for day, data in _days.items():
            found[day] = json.loads(json.dumps(data))
    return [found[k] for k in sorted(found)]


def summary(recipe_names) -> dict:
    """Totals across all days, for the public /stats page."""
    days = all_days()
    visitors = sum(d["funnel"]["visited"] for d in days)
    events: dict[str, int] = {}
    funnel = {s: 0 for s in FUNNEL}
    items: dict[str, dict[str, int]] = {name: {} for name in ITEMS}
    for d in days:
        for k, v in d["events"].items():
            events[k] = events.get(k, 0) + v
        for s in FUNNEL:
            funnel[s] += d["funnel"][s]
        for name in ITEMS:
            for k, v in d["items"][name].items():
                items[name][k] = items[name].get(k, 0) + v

    def top(name: str, n: int = 10) -> list[tuple[str, int]]:
        return sorted(items[name].items(), key=lambda kv: (-kv[1], kv[0]))[:n]

    timing: dict[str, dict] = {}
    errors = {"server": {}, "not_found": {}}
    starts: list[dict] = []
    for d in days:
        for route, t in d["timing"].items():
            mine = timing.setdefault(route, _new_timing())
            mine["buckets"] = [a + b for a, b in zip(mine["buckets"], t["buckets"])]
            mine["count"] += t["count"]
            mine["total_ms"] += t["total_ms"]
        for kind in errors:
            for route, v in d["errors"][kind].items():
                errors[kind][route] = errors[kind].get(route, 0) + v
        starts += [{"day": d["day"], "seconds": s} for s in d["starts"]]
    speed = sorted(
        (
            {
                "route": route,
                "requests": t["count"],
                "average_ms": round(t["total_ms"] / t["count"]) if t["count"] else None,
                "typical_under_ms": _percentile_ms(t["buckets"], 0.5),
                "p95_under_ms": _percentile_ms(t["buckets"], 0.95),
                "server_errors": errors["server"].get(route, 0),
                "not_found": errors["not_found"].get(route, 0),
            }
            for route, t in timing.items()
        ),
        key=lambda r: -r["requests"],
    )
    per_day_errors = [
        {"day": d["day"], "server": sum(d["errors"]["server"].values()), "not_found": sum(d["errors"]["not_found"].values()),
         "requests": sum(t["count"] for t in d["timing"].values())}
        for d in days[-14:]
    ]

    opened = top("recipe_opened")
    names = recipe_names([int(k) for k, _ in opened])
    return {
        "since": days[0]["day"] if days else None,
        "visitors": visitors,
        "per_day": [{"day": d["day"], "visitors": d["funnel"]["visited"]} for d in days[-14:]],
        "funnel": {s: {"visitors": funnel[s], "share": round(funnel[s] / visitors, 3) if visitors else None} for s in FUNNEL},
        "events": dict(sorted(events.items())),
        "top_ingredients_added": [{"ingredient": k, "times": v} for k, v in top("ingredient_added")],
        "top_recipes_opened": [{"id": int(k), "name": names.get(int(k)), "times": v} for k, v in opened],
        "speed": speed,
        "errors_per_day": per_day_errors,
        "starts": starts[-20:],
    }


def _reset_for_tests() -> None:
    global _reached_day, _vocab
    with _lock:
        _days.clear()
        _dirty.clear()
        _reached.clear()
        _reached_day = None
        _vocab = frozenset()
