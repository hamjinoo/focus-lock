"""SQLite state. Schedules + Frozen sessions + blocklist + audit log."""
from __future__ import annotations

import json
import sqlite3
import time
import uuid
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator, Optional

from .config import DB_PATH

SCHEMA = """
CREATE TABLE IF NOT EXISTS blocklist (
    domain TEXT PRIMARY KEY,
    added_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS schedules (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    days TEXT NOT NULL,            -- json [0..6], Mon=0
    start_minute INTEGER NOT NULL, -- minutes from midnight
    end_minute INTEGER NOT NULL,
    enabled INTEGER NOT NULL DEFAULT 1,
    created_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS sessions (
    id TEXT PRIMARY KEY,
    label TEXT NOT NULL,
    started_at REAL NOT NULL,
    ends_at REAL NOT NULL,
    frozen INTEGER NOT NULL,       -- 1 = cannot be cancelled
    cancelled_at REAL
);
CREATE TABLE IF NOT EXISTS audit (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    at REAL NOT NULL,
    event TEXT NOT NULL,
    detail TEXT
);
"""


def _connect(path: Path = DB_PATH) -> sqlite3.Connection:
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA foreign_keys=ON;")
    return conn


def init_db(path: Path = DB_PATH) -> None:
    with _connect(path) as conn:
        conn.executescript(SCHEMA)


@contextmanager
def tx(path: Path = DB_PATH) -> Iterator[sqlite3.Connection]:
    conn = _connect(path)
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


# ---------- blocklist ----------

def list_blocked() -> list[str]:
    with tx() as conn:
        rows = conn.execute("SELECT domain FROM blocklist ORDER BY domain").fetchall()
        return [r["domain"] for r in rows]


def add_blocked(domains: list[str]) -> list[str]:
    norm = [d.strip().lower().lstrip(".") for d in domains if d.strip()]
    now = time.time()
    with tx() as conn:
        for d in norm:
            conn.execute(
                "INSERT OR IGNORE INTO blocklist (domain, added_at) VALUES (?, ?)",
                (d, now),
            )
        rows = conn.execute("SELECT domain FROM blocklist ORDER BY domain").fetchall()
    log("blocklist.add", {"added": norm})
    return [r["domain"] for r in rows]


def remove_blocked(domain: str) -> list[str]:
    d = domain.strip().lower().lstrip(".")
    with tx() as conn:
        conn.execute("DELETE FROM blocklist WHERE domain = ?", (d,))
        rows = conn.execute("SELECT domain FROM blocklist ORDER BY domain").fetchall()
    log("blocklist.remove", {"domain": d})
    return [r["domain"] for r in rows]


# ---------- schedules ----------

def list_schedules() -> list[dict]:
    with tx() as conn:
        rows = conn.execute("SELECT * FROM schedules ORDER BY name").fetchall()
        return [_schedule_row(r) for r in rows]


def _schedule_row(r: sqlite3.Row) -> dict:
    return {
        "id": r["id"],
        "name": r["name"],
        "days": json.loads(r["days"]),
        "start_minute": r["start_minute"],
        "end_minute": r["end_minute"],
        "enabled": bool(r["enabled"]),
        "created_at": r["created_at"],
    }


def create_schedule(name: str, days: list[int], start_minute: int, end_minute: int) -> dict:
    sid = uuid.uuid4().hex[:12]
    now = time.time()
    with tx() as conn:
        conn.execute(
            "INSERT INTO schedules (id, name, days, start_minute, end_minute, enabled, created_at) "
            "VALUES (?, ?, ?, ?, ?, 1, ?)",
            (sid, name, json.dumps(sorted(set(days))), start_minute, end_minute, now),
        )
        row = conn.execute("SELECT * FROM schedules WHERE id = ?", (sid,)).fetchone()
    log("schedule.create", {"id": sid, "name": name})
    return _schedule_row(row)


def delete_schedule(sid: str) -> None:
    with tx() as conn:
        conn.execute("DELETE FROM schedules WHERE id = ?", (sid,))
    log("schedule.delete", {"id": sid})


def set_schedule_enabled(sid: str, enabled: bool) -> None:
    with tx() as conn:
        conn.execute("UPDATE schedules SET enabled = ? WHERE id = ?", (1 if enabled else 0, sid))
    log("schedule.enabled", {"id": sid, "enabled": enabled})


# ---------- sessions ----------

def list_active_sessions(now: Optional[float] = None) -> list[dict]:
    now = now if now is not None else time.time()
    with tx() as conn:
        rows = conn.execute(
            "SELECT * FROM sessions WHERE cancelled_at IS NULL AND ends_at > ? ORDER BY ends_at",
            (now,),
        ).fetchall()
        return [_session_row(r) for r in rows]


def _session_row(r: sqlite3.Row) -> dict:
    return {
        "id": r["id"],
        "label": r["label"],
        "started_at": r["started_at"],
        "ends_at": r["ends_at"],
        "frozen": bool(r["frozen"]),
        "cancelled_at": r["cancelled_at"],
    }


def create_session(label: str, duration_seconds: int, frozen: bool) -> dict:
    sid = uuid.uuid4().hex[:12]
    now = time.time()
    ends_at = now + max(60, int(duration_seconds))
    with tx() as conn:
        conn.execute(
            "INSERT INTO sessions (id, label, started_at, ends_at, frozen) VALUES (?, ?, ?, ?, ?)",
            (sid, label, now, ends_at, 1 if frozen else 0),
        )
        row = conn.execute("SELECT * FROM sessions WHERE id = ?", (sid,)).fetchone()
    log("session.create", {"id": sid, "label": label, "frozen": frozen, "ends_at": ends_at})
    return _session_row(row)


def cancel_session(sid: str) -> dict:
    """Cancel a non-frozen session. Raises if frozen and still active."""
    now = time.time()
    with tx() as conn:
        row = conn.execute("SELECT * FROM sessions WHERE id = ?", (sid,)).fetchone()
        if row is None:
            raise KeyError(sid)
        if row["cancelled_at"] is not None:
            return _session_row(row)
        if row["frozen"] and row["ends_at"] > now:
            log("session.cancel_denied", {"id": sid})
            raise PermissionError("session is frozen until expiry")
        conn.execute("UPDATE sessions SET cancelled_at = ? WHERE id = ?", (now, sid))
        row = conn.execute("SELECT * FROM sessions WHERE id = ?", (sid,)).fetchone()
    log("session.cancel", {"id": sid})
    return _session_row(row)


# ---------- audit ----------

def log(event: str, detail: dict | None = None) -> None:
    try:
        with tx() as conn:
            conn.execute(
                "INSERT INTO audit (at, event, detail) VALUES (?, ?, ?)",
                (time.time(), event, json.dumps(detail) if detail else None),
            )
    except sqlite3.Error:
        pass


def recent_audit(limit: int = 50) -> list[dict]:
    with tx() as conn:
        rows = conn.execute(
            "SELECT at, event, detail FROM audit ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()
        return [
            {"at": r["at"], "event": r["event"], "detail": json.loads(r["detail"]) if r["detail"] else None}
            for r in rows
        ]
