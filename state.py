"""Atomic, repository-persisted notification state."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path


def read_state(path: Path) -> dict:
    if not path.exists():
        return {"notification_sent": False}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        # A damaged state must never suppress a genuine notification.
        return {"notification_sent": False}


def save_notification(path: Path, theatres: list[str], showtimes: dict[str, list[str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    state = {
        "notification_sent": True,
        "notified_at": datetime.now(timezone.utc).isoformat(),
        "theatres": theatres,
        "showtimes": showtimes,
    }
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(state, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(path)
