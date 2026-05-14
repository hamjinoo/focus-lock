"""Compute effective block state from active sessions + enabled schedules."""
from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from . import store


@dataclass
class LockStatus:
    active: bool
    reason: str                       # "idle" | "session" | "schedule"
    expires_at: Optional[float]       # epoch seconds when current block ends
    frozen: bool                      # any active reason is frozen?
    sources: list[dict]               # contributing sessions/schedules


def _schedule_active_at(sched: dict, now_dt: datetime) -> bool:
    if not sched["enabled"]:
        return False
    weekday = now_dt.weekday()
    if weekday not in sched["days"]:
        return False
    minute = now_dt.hour * 60 + now_dt.minute
    start, end = sched["start_minute"], sched["end_minute"]
    if start == end:
        return False
    if start < end:
        return start <= minute < end
    # overnight wrap (e.g., 22:00 → 06:00)
    return minute >= start or minute < end


def _schedule_ends_at(sched: dict, now: float) -> float:
    """Epoch when this schedule's current active window ends. Assumes already active."""
    now_dt = datetime.fromtimestamp(now)
    minute = now_dt.hour * 60 + now_dt.minute
    start, end = sched["start_minute"], sched["end_minute"]
    midnight = now - (minute * 60 + now_dt.second + now_dt.microsecond / 1e6)
    if start < end:
        return midnight + end * 60
    # overnight wrap: if we're in the post-start half, end is tomorrow's `end`
    if minute >= start:
        return midnight + (24 * 60 + end) * 60
    return midnight + end * 60


def evaluate(now: Optional[float] = None) -> LockStatus:
    now = now if now is not None else time.time()
    now_dt = datetime.fromtimestamp(now)
    sessions = store.list_active_sessions(now)
    schedules = store.list_schedules()

    sources: list[dict] = []
    expires_at: Optional[float] = None
    frozen = False
    reason = "idle"

    for s in sessions:
        sources.append({"type": "session", **s})
        if s["frozen"]:
            frozen = True
        if expires_at is None or s["ends_at"] > expires_at:
            expires_at = s["ends_at"]
        reason = "session"

    for sch in schedules:
        if _schedule_active_at(sch, now_dt):
            ends = _schedule_ends_at(sch, now)
            sources.append({"type": "schedule", "ends_at": ends, **sch})
            if expires_at is None or ends > expires_at:
                expires_at = ends
            if reason == "idle":
                reason = "schedule"

    return LockStatus(
        active=bool(sources),
        reason=reason,
        expires_at=expires_at,
        frozen=frozen,
        sources=sources,
    )


def desired_domains(status: LockStatus) -> list[str]:
    if not status.active:
        return []
    return store.list_blocked()
