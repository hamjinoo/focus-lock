"""FastAPI service entry point. Run with: uvicorn focus_lock.main:app"""
from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles

from . import hosts as hosts_mod
from . import lock, reconciler, store
from .config import HOSTS_PATH
from .models import (
    BlocklistAdd,
    ScheduleCreate,
    SessionCreate,
    StatusResponse,
)

WEB_DIR = Path(__file__).resolve().parent.parent / "web"


@asynccontextmanager
async def lifespan(app: FastAPI):
    store.init_db()
    store.log("service.start", None)
    # First-pass reconcile is synchronous so the unblocked window after
    # boot/restart is as short as possible. Any error is logged and ignored;
    # the background loop will retry.
    try:
        status = lock.evaluate()
        hosts_mod.reconcile(lock.desired_domains(status))
        store.log("hosts.initial_apply", {"active": status.active})
    except Exception as exc:
        store.log("hosts.initial_apply_error", {"err": str(exc)})
    stop_event = asyncio.Event()
    task = asyncio.create_task(reconciler.run(stop_event))
    try:
        yield
    finally:
        stop_event.set()
        try:
            await asyncio.wait_for(task, timeout=2)
        except asyncio.TimeoutError:
            task.cancel()
        store.log("service.stop", None)


app = FastAPI(title="focus-lock", version="0.1.0", lifespan=lifespan)

# Allow the browser extension to query block state. The service binds to
# 127.0.0.1 only so this isn't reachable from the network.
app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=r"^(chrome-extension://.*|moz-extension://.*|http://(localhost|127\.0\.0\.1)(:\d+)?)$",
    allow_methods=["GET"],
    allow_headers=["*"],
)


@app.get("/api/status", response_model=StatusResponse)
def get_status():
    status = lock.evaluate()
    desired = lock.desired_domains(status)
    current = set(hosts_mod.read_state().domains)
    synced = set(d.strip().lower().lstrip(".") for d in desired) == current or (
        not desired and not current
    )
    return StatusResponse(
        active=status.active,
        reason=status.reason,
        expires_at=status.expires_at,
        frozen=status.frozen,
        sources=status.sources,
        blocked_domains=store.list_blocked(),
        hosts_synced=synced,
    )


@app.get("/api/blocklist")
def get_blocklist():
    return {"domains": store.list_blocked()}


@app.post("/api/blocklist")
def post_blocklist(payload: BlocklistAdd):
    return {"domains": store.add_blocked(payload.domains)}


@app.delete("/api/blocklist/{domain}")
def delete_blocklist(domain: str):
    return {"domains": store.remove_blocked(domain)}


@app.get("/api/schedules")
def get_schedules():
    return {"schedules": store.list_schedules()}


@app.post("/api/schedules")
def post_schedule(payload: ScheduleCreate):
    return store.create_schedule(
        payload.name, payload.days, payload.start_minute, payload.end_minute
    )


@app.delete("/api/schedules/{sid}")
def delete_schedule(sid: str):
    store.delete_schedule(sid)
    return {"ok": True}


@app.post("/api/schedules/{sid}/toggle")
def toggle_schedule(sid: str, enabled: bool = True):
    store.set_schedule_enabled(sid, enabled)
    return {"ok": True}


@app.get("/api/sessions")
def get_sessions():
    return {"sessions": store.list_active_sessions()}


@app.post("/api/sessions")
def post_session(payload: SessionCreate):
    return store.create_session(payload.label, payload.duration_minutes * 60, payload.frozen)


@app.delete("/api/sessions/{sid}")
def delete_session(sid: str):
    try:
        return store.cancel_session(sid)
    except KeyError:
        raise HTTPException(404, "session not found")
    except PermissionError as exc:
        raise HTTPException(403, str(exc))


@app.get("/api/audit")
def get_audit(limit: int = 50):
    return {"entries": store.recent_audit(limit=limit)}


@app.get("/api/health")
def health():
    return {
        "ok": True,
        "hosts_path": str(HOSTS_PATH),
        "hosts_writable": _hosts_writable(),
    }


def _hosts_writable() -> bool:
    try:
        return HOSTS_PATH.exists() and (
            HOSTS_PATH.stat().st_mode & 0o200 != 0
        ) and __import__("os").access(HOSTS_PATH, 2)  # W_OK
    except OSError:
        return False


@app.get("/favicon.ico")
def favicon():
    # tiny inline SVG → no separate file needed
    svg = (
        b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 16 16">'
        b'<rect width="16" height="16" rx="3" fill="#0f1115"/>'
        b'<circle cx="8" cy="8" r="3" fill="#6ee7b7"/></svg>'
    )
    return Response(content=svg, media_type="image/svg+xml")


if WEB_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(WEB_DIR)), name="static")

    @app.get("/")
    def root():
        index = WEB_DIR / "index.html"
        if index.exists():
            return FileResponse(index)
        return JSONResponse({"ok": True})
