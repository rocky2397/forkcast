"""Public demo mode (D32): a private demo kitchen for every visitor.

Forkcast is a single-user app: one inventory, one meal log, one profile. A
public link to it would let every visitor edit the same kitchen. With
FORKCAST_DEMO=1 each visitor instead gets their own copy of the demo kitchen
(the one the README screenshots use), as a small SQLite file next to the shared
read-only recipe corpus:

- The server hands out a random kitchen id in the X-Forkcast-Kitchen response
  header; the frontend keeps it in localStorage and sends it back. A header
  rather than a cookie, because hosts like Hugging Face Spaces show the app in
  a cross-site iframe, where browsers block cookies.
- A kitchen nobody has used for IDLE_SECONDS is deleted, and at most
  MAX_KITCHENS exist at once (the least recently used go first), so scripts
  creating kitchens can't fill the disk.
- Photo and label scanning are off: they call a paid model, and the demo ships
  without any API key.

Nothing here runs unless FORKCAST_DEMO is set.
"""

import json
import os
import re
import secrets
import shutil
import sqlite3
import threading
import time
from collections.abc import Callable
from pathlib import Path

from . import db

HEADER = "X-Forkcast-Kitchen"
IDLE_SECONDS = 24 * 3600
MAX_KITCHENS = 300
SCAN_OFF = (
    "Photo scanning is switched off in this demo, because it calls a paid AI model. "
    "The walkthrough in the README shows it."
)

_SEED = Path(__file__).with_name("demo_kitchen.json")
_ID = re.compile(r"^[A-Za-z0-9_-]{22}$")  # secrets.token_urlsafe(16)
_lock = threading.Lock()


def enabled() -> bool:
    return os.environ.get("FORKCAST_DEMO") == "1"


def _root() -> Path:
    return db.DATA_DIR / "demo"


def template_path() -> Path:
    return _root() / "template.db"


def kitchens_dir() -> Path:
    return _root() / "kitchens"


def seed() -> dict:
    return json.loads(_SEED.read_text())


def build_template(match: Callable[[str], str | None]) -> list[str]:
    """Write the demo kitchen every visitor starts from; returns unmatched items."""
    data = seed()
    path = template_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".building")
    tmp.unlink(missing_ok=True)
    con = db.connect(tmp)
    p = data["profile"]
    con.execute(
        "INSERT INTO profile (id, sex, age, height_cm, weight_kg, activity, goal)"
        " VALUES (1, ?, ?, ?, ?, ?, ?)",
        (p["sex"], p["age"], p["height_cm"], p["weight_kg"], p["activity"], p["goal"]),
    )
    unknown = []
    for raw in data["kitchen"]:
        canonical = match(raw)
        if canonical is None:
            unknown.append(raw)
        else:
            con.execute("INSERT OR IGNORE INTO inventory (canonical) VALUES (?)", (canonical,))
    for rid in data["cooked_and_liked"]:
        # Skipped, not failed, on a corpus without these ids (the test corpus).
        if con.execute("SELECT 1 FROM recipes WHERE id = ?", (rid,)).fetchone():
            con.execute("INSERT INTO meal_log (recipe_id, liked) VALUES (?, 1)", (rid,))
    m = data["typed_meal"]
    con.execute(
        "INSERT INTO meal_log (name, calories, protein_g, carbs_g, fat_g) VALUES (?, ?, ?, ?, ?)",
        (m["name"], m["calories"], m["protein_g"], m["carbs_g"], m["fat_g"]),
    )
    con.commit()
    con.close()
    os.replace(tmp, path)
    return unknown


def _sweep(now: float) -> None:
    """Delete idle kitchens, then the least recently used beyond the cap."""
    files = []
    for f in kitchens_dir().glob("*.db"):
        try:
            used = f.stat().st_mtime
        except FileNotFoundError:
            continue
        if now - used > IDLE_SECONDS:
            f.unlink(missing_ok=True)
        else:
            files.append((used, f))
    files.sort()
    for _, f in files[: max(0, len(files) - MAX_KITCHENS + 1)]:
        f.unlink(missing_ok=True)


def kitchen(requested: str | None) -> tuple[str, Path, bool]:
    """(kitchen id, user DB path, newly created) for a request.

    The visitor's own kitchen, or a new one.

    Anything that isn't a live kitchen id, including a malformed header, gets a
    fresh kitchen; the id is never used in a path unless it matches _ID.
    """
    with _lock:
        if requested and _ID.match(requested):
            path = kitchens_dir() / f"{requested}.db"
            if path.is_file():
                os.utime(path)  # last use, for the idle sweep
                return requested, path, False
        now = time.time()
        kitchens_dir().mkdir(parents=True, exist_ok=True)
        _sweep(now)
        new = secrets.token_urlsafe(16)
        path = kitchens_dir() / f"{new}.db"
        shutil.copyfile(template_path(), path)
        # The seeded meals happened "today" for every new visitor.
        con = sqlite3.connect(path)
        con.execute("UPDATE meal_log SET logged_at = datetime('now')")
        con.commit()
        con.close()
        return new, path, True
