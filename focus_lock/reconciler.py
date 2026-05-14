"""Background reconciliation loop. Periodically forces the hosts file to match
the desired state — defends against external edits while a block is active."""
from __future__ import annotations

import asyncio
import logging

from . import hosts, lock, store

log = logging.getLogger("focus_lock.reconciler")

INTERVAL_SECONDS = 5.0


async def run(stop_event: asyncio.Event) -> None:
    while not stop_event.is_set():
        try:
            status = lock.evaluate()
            desired = lock.desired_domains(status)
            changed = hosts.reconcile(desired)
            if changed:
                store.log(
                    "hosts.reconcile",
                    {"active": status.active, "count": len(desired)},
                )
        except PermissionError as exc:
            log.warning("permission denied writing hosts: %s", exc)
            store.log("hosts.permission_error", {"err": str(exc)})
        except Exception as exc:
            log.exception("reconcile failed: %s", exc)
            store.log("hosts.error", {"err": str(exc)})
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=INTERVAL_SECONDS)
        except asyncio.TimeoutError:
            pass
