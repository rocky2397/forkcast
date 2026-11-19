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
- With FORKCAST_KITCHENS_DIR set (D34), kitchens are also saved there, so they
  survive restarts and updates: on Hugging Face that is the mounted private
  storage bucket. The live copy stays on local disk, where SQLite is fast and
  safe; a changed kitchen is copied to the saved folder within SAVE_SECONDS,
  and on shutdown. A visitor whose live copy is gone (restart, idle sweep)
  gets the saved one back. A saved kitchen is deleted KEEP_SECONDS after the
  last visit, at most MAX_SAVED are kept, and the visitor can delete theirs at
  any time (delete()).
- Photo and label scanning are off unless the host sets ANTHROPIC_API_KEY
  (D38): they call a paid model. With a key, each visitor gets SCANS_PER_VISITOR
  scans a UTC day and the whole demo SCANS_PER_DAY, counted in memory (a restart
  resets them; the key's own spending limit in the Anthropic Console is the
  hard stop).

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
from contextvars import ContextVar
from pathlib import Path

from . import db

HEADER = "X-Forkcast-Kitchen"
IDLE_SECONDS = 24 * 3600
MAX_KITCHENS = 300
KEEP_SECONDS = 30 * 24 * 3600
MAX_SAVED = 5000
SAVE_SECONDS = 30
SWEEP_SAVED_SECONDS = 3600
SCANS_PER_VISITOR = 10
SCANS_PER_DAY = 200
SCAN_LIMIT_VISITOR = "That's 10 scans for today in this demo. Add ingredients by name, or come back tomorrow."
SCAN_LIMIT_DAY = "The demo has used all its scans for today. Add ingredients by name, or come back tomorrow."
SCAN_OFF = (
    "Photo scanning is switched off in this demo, because it calls a paid AI model. "
    "The walkthrough in the README shows it."
)

_SEED = Path(__file__).with_name("demo_kitchen.json")
_ID = re.compile(r"^[A-Za-z0-9_-]{22}$")  # secrets.token_urlsafe(16)
_lock = threading.Lock()
_scans: dict[str, int] = {}  # kitchen id -> scans today (D38)
_scans_total = 0
_scans_day = ""
_save_lock = threading.Lock()  # one save pass at a time
_dirty: set[str] = set()  # kitchens with changes not yet saved
_saved_on: dict[str, str] = {}  # kitchen id -> UTC day its saved copy was last written
_swept_saved_at = 0.0

# The kitchen of the request being handled, set by the middleware in main.py.
current_id: ContextVar[str | None] = ContextVar("demo_kitchen_id", default=None)


def enabled() -> bool:
    return os.environ.get("FORKCAST_DEMO") == "1"


def _root() -> Path:
    return db.DATA_DIR / "demo"


def scanning() -> bool:
    """Photo and label scanning on in the demo (D38): only with an API key."""
    return enabled() and bool(os.environ.get("ANTHROPIC_API_KEY"))


def take_scan(kitchen_id: str | None) -> str | None:
    """Count one scan; the reason it is refused, or None if it may go ahead."""
    global _scans_total, _scans_day
    with _lock:
        today = _today()
        if _scans_day != today:
            _scans.clear()
            _scans_total = 0
            _scans_day = today
        if _scans_total >= SCANS_PER_DAY:
            return SCAN_LIMIT_DAY
        key = kitchen_id or ""
        if _scans.get(key, 0) >= SCANS_PER_VISITOR:
            return SCAN_LIMIT_VISITOR
        _scans[key] = _scans.get(key, 0) + 1
        _scans_total += 1
        return None


def saved_dir() -> Path | None:
    """Where kitchens are saved to survive restarts (D34), or None: not saved."""
    d = os.environ.get("FORKCAST_KITCHENS_DIR")
    return Path(d) if enabled() and d else None


def _today() -> str:
    return time.strftime("%Y-%m-%d", time.gmtime())


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
    # D57: no profile, so each visitor sets their own, and nothing logged
    # today or rated: an empty day that is theirs.
    unknown = []
    for raw in data["kitchen"]:
        canonical = match(raw)
        if canonical is None:
            unknown.append(raw)
        else:
            con.execute("INSERT OR IGNORE INTO inventory (canonical) VALUES (?)", (canonical,))
    for cook in data["cooked_earlier"]:
        # Earlier in the week, unrated: the recipe feed has dishes to compare
        # with ("Like your Cherry Tomato Pasta"), and the intro says so.
        # Skipped, not failed, on a corpus without these ids (the test corpus).
        if con.execute("SELECT 1 FROM recipes WHERE id = ?", (cook["recipe_id"],)).fetchone():
            con.execute(
                "INSERT INTO meal_log (recipe_id, logged_at) VALUES (?, datetime('now', ?))",
                (cook["recipe_id"], f"-{cook['days_ago']} days"),
            )
    con.commit()
    con.close()
    os.replace(tmp, path)
    return unknown


def _sweep(now: float) -> None:
    """Delete idle kitchens, then the least recently used beyond the cap."""
    files = []
    for f in kitchens_dir().glob("*.db"):
        if f.stem in _dirty:
            continue  # unsaved changes: the next save pass needs this file
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
                if saved_dir() and _saved_on.get(requested) != _today():
                    _dirty.add(requested)  # a visit restarts the saved copy's 30 days
                return requested, path, False
            saved = saved_dir() / f"{requested}.db" if saved_dir() else None
            if saved is not None and saved.is_file():
                kitchens_dir().mkdir(parents=True, exist_ok=True)
                shutil.copyfile(saved, path)
                _dirty.add(requested)
                return requested, path, False
        now = time.time()
        kitchens_dir().mkdir(parents=True, exist_ok=True)
        _sweep(now)
        new = secrets.token_urlsafe(16)
        path = kitchens_dir() / f"{new}.db"
        shutil.copyfile(template_path(), path)
        # D57: the seeded cooks are the same number of days back for every new
        # visitor, however old the template is; never today.
        con = sqlite3.connect(path)
        for cook in seed()["cooked_earlier"]:
            con.execute(
                "UPDATE meal_log SET logged_at = datetime('now', ?) WHERE recipe_id = ?",
                (f"-{cook['days_ago']} days", cook["recipe_id"]),
            )
        con.commit()
        con.close()
        return new, path, True


def changed(kitchen_id: str) -> None:
    """Mark a kitchen for the next save pass (called after a successful change)."""
    if saved_dir():
        with _lock:
            _dirty.add(kitchen_id)


def _write_saved(src: Path, dest: Path) -> None:
    """Copy a live kitchen to the saved folder as one consistent file."""
    snapshot = src.with_suffix(".snapshot")
    live = sqlite3.connect(src)
    copy = sqlite3.connect(snapshot)
    try:
        live.backup(copy)  # consistent even while a request is writing
    finally:
        copy.close()
        live.close()
    tmp = dest.with_suffix(".saving")
    try:
        shutil.copyfile(snapshot, tmp)
        try:
            os.replace(tmp, dest)
        except OSError:  # some bucket mounts can't rename; write in place
            shutil.copyfile(snapshot, dest)
            tmp.unlink(missing_ok=True)
    finally:
        snapshot.unlink(missing_ok=True)


def save_pending() -> int:
    """Save every changed kitchen; returns how many were saved."""
    target = saved_dir()
    if target is None:
        return 0
    with _save_lock:
        with _lock:
            pending = sorted(_dirty)
            _dirty.clear()
        target.mkdir(parents=True, exist_ok=True)
        saved = 0
        for kid in pending:
            src = kitchens_dir() / f"{kid}.db"
            if not src.is_file():
                continue  # deleted by its visitor in the meantime
            try:
                _write_saved(src, target / f"{kid}.db")
            except (OSError, sqlite3.Error) as e:
                print(f"[demo] couldn't save a kitchen, will retry: {type(e).__name__}: {e}", flush=True)
                with _lock:
                    _dirty.add(kid)  # try again next pass
                continue
            _saved_on[kid] = _today()
            saved += 1
        _sweep_saved(time.time())
        if saved:
            print(f"[demo] saved {saved} changed kitchen(s)", flush=True)
        return saved


def _sweep_saved(now: float) -> None:
    """Delete saved kitchens past KEEP_SECONDS, then the oldest beyond MAX_SAVED."""
    global _swept_saved_at
    target = saved_dir()
    if target is None or now - _swept_saved_at < SWEEP_SAVED_SECONDS:
        return
    _swept_saved_at = now
    files = []
    for f in target.glob("*.db"):
        try:
            written = f.stat().st_mtime
        except FileNotFoundError:
            continue
        if now - written > KEEP_SECONDS:
            f.unlink(missing_ok=True)
        else:
            files.append((written, f))
    files.sort()
    for _, f in files[: max(0, len(files) - MAX_SAVED)]:
        f.unlink(missing_ok=True)


def delete(kitchen_id: str) -> None:
    """Delete a visitor's kitchen everywhere: the live copy and the saved one."""
    if not _ID.match(kitchen_id):
        return
    with _save_lock, _lock:  # never while a save pass could write it back
        _dirty.discard(kitchen_id)
        _saved_on.pop(kitchen_id, None)
        (kitchens_dir() / f"{kitchen_id}.db").unlink(missing_ok=True)
        if saved_dir():
            (saved_dir() / f"{kitchen_id}.db").unlink(missing_ok=True)
