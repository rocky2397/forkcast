#!/usr/bin/env python
"""The Forkcast server for ops/screenshots.sh, with a settable "today".

    FORKCAST_SHOT_CLOCK=<file> python backend/scripts/serve_for_screenshots.py <port>

Runs the app exactly as uvicorn would, except that while <file> holds a date
(YYYY-MM-DD) the app's "today" (progress.local_today) is that date. The
README's "the plan redraws itself" strip uses it to show one sample person at
weeks 1, 3 and 6 of the same history, each on its own date, so the three
cards share one calendar. An empty or missing file means the real today.
Screenshots only: the app itself has no way to change its clock.
"""
import os
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import uvicorn  # noqa: E402

from app import progress, weight  # noqa: E402

CLOCK = Path(os.environ["FORKCAST_SHOT_CLOCK"])
_real = progress.local_today


def local_today(tz_minutes: int = 0) -> date:
    text = CLOCK.read_text().strip() if CLOCK.exists() else ""
    return date.fromisoformat(text) if text else _real(tz_minutes)


progress.local_today = local_today
weight.local_today = local_today  # imported by name there

if __name__ == "__main__":
    from app.main import app

    uvicorn.run(app, port=int(sys.argv[1]), log_level="warning")
