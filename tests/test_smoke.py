"""End-to-end smoke test against a temp hosts file. No admin needed."""
from __future__ import annotations

import os
import tempfile
import time
from pathlib import Path

# Point at temp paths BEFORE importing the package so config.py picks them up.
_tmp_dir = tempfile.mkdtemp(prefix="focus-lock-test-")
_hosts = Path(_tmp_dir) / "hosts"
_hosts.write_text("127.0.0.1\tlocalhost\n", encoding="utf-8")
_db = Path(_tmp_dir) / "state.db"
os.environ["FOCUS_LOCK_HOSTS"] = str(_hosts)
os.environ["FOCUS_LOCK_DB"] = str(_db)

from focus_lock import hosts as hosts_mod  # noqa: E402
from focus_lock import lock, store         # noqa: E402


def _show(label: str) -> None:
    print(f"\n--- {label} ---")
    print(_hosts.read_text(encoding="utf-8"))


def main() -> None:
    store.init_db()
    print("hosts at:", _hosts)
    print("db at:", _db)

    # 1. empty state: idle, no managed block
    status = lock.evaluate()
    assert not status.active, status
    hosts_mod.reconcile(lock.desired_domains(status))
    assert hosts_mod.read_state().domains == []
    print("[ok] idle state — no managed block")

    # 2. add blocklist while idle: still idle, no block written
    store.add_blocked(["youtube.com", "x.com"])
    status = lock.evaluate()
    assert not status.active
    hosts_mod.reconcile(lock.desired_domains(status))
    assert hosts_mod.read_state().domains == []
    print("[ok] blocklist while idle does not modify hosts")

    # 3. start a non-frozen 1-min session → block engages
    sess = store.create_session("test", duration_seconds=60, frozen=False)
    status = lock.evaluate()
    assert status.active and status.reason == "session"
    assert not status.frozen
    changed = hosts_mod.reconcile(lock.desired_domains(status))
    assert changed
    domains = sorted(hosts_mod.read_state().domains)
    assert "youtube.com" in domains and "x.com" in domains, domains
    _show("active block")

    # 4. cancel non-frozen session → block releases
    store.cancel_session(sess["id"])
    status = lock.evaluate()
    assert not status.active
    hosts_mod.reconcile(lock.desired_domains(status))
    assert hosts_mod.read_state().domains == []
    print("[ok] non-frozen cancel releases the block")

    # 5. start FROZEN session → cannot cancel
    fsess = store.create_session("frozen test", duration_seconds=120, frozen=True)
    status = lock.evaluate()
    assert status.active and status.frozen
    hosts_mod.reconcile(lock.desired_domains(status))
    assert len(hosts_mod.read_state().domains) >= 2
    try:
        store.cancel_session(fsess["id"])
    except PermissionError:
        print("[ok] frozen session refused cancellation")
    else:
        raise AssertionError("frozen session was cancelled (should not be)")

    # 6. schedule: weekday 00:00-23:59 → active right now
    from datetime import datetime
    today = datetime.now().weekday()
    sched = store.create_schedule("always", [today], 0, 23 * 60 + 59)
    status = lock.evaluate()
    assert status.active
    assert any(s["type"] == "schedule" for s in status.sources)
    print("[ok] schedule contributes to lock state")

    # cleanup so re-runs are idempotent
    store.delete_schedule(sched["id"])

    # 7. hosts file integrity: preserves non-managed lines
    raw = _hosts.read_text(encoding="utf-8")
    assert "127.0.0.1\tlocalhost" in raw, "lost the original hosts entry"
    print("[ok] original hosts content preserved outside markers")

    _show("final hosts")
    print("\nALL CHECKS PASSED")


if __name__ == "__main__":
    main()
