# focus-lock

A self-hosted website blocker for Windows with **Frozen sessions** (once started,
cannot be cancelled until the timer expires) and **scheduled blocks**.
Lives entirely on your machine — no account, no cloud, no telemetry.

> v0.1 — written as a personal dopamine-detox tool and a study in honest
> anti-bypass design. Tested on Windows 11 + WSL2 Ubuntu 24.04.

---

## Why one more blocker

Existing tools (Cold Turkey, Freedom, BlockSite) work, but I wanted to build
the smallest credible version myself and own the failure modes. The design
goal is **explicit**:

> Make bypass cost at least 5 minutes of deliberate effort, so the impulse
> cools off. Not "make bypass impossible" — the user is admin on their own
> machine; absolute prevention is a fantasy.

Everything in the codebase is shaped by that scope. No driver-signing, no
kernel-level filtering, no shipping a rootkit to enforce a habit.

## How blocking works

```
   ┌─────────────────────────────────────────────────────────────┐
   │  Windows Service (NSSM-wrapped, runs as LocalSystem)         │
   │                                                              │
   │   FastAPI ──┬── /api/sessions, /api/schedules, /api/blocklist│
   │             ├── hosts reconciler (every 5s)                  │
   │             └── SQLite state (~/AppData/focus-lock/state.db) │
   └────┬──────────────────────┬─────────────────────────────────┘
        │                      │
        │ owns                  │ serves
        ▼                      ▼
  C:\Windows\System32\     http://127.0.0.1:8765
  drivers\etc\hosts        (web UI, no auth)
        ▲
        │ watches every minute
   ┌────┴──────────────────────┐
   │ Task Scheduler watchdog   │  (covers manual Stop-Service)
   └───────────────────────────┘
```

- The service owns a marker-delimited block inside the system hosts file
  (`# >>> focus-lock managed block >>>` … `# <<< focus-lock managed block <<<`).
  Content **outside** the markers is preserved.
- For each blocked domain we write both `domain` and `www.domain`, IPv4 and
  IPv6, all pointed at `127.0.0.1` / `::1`.
- A background loop reconciles every 5 seconds — if you edit the hosts file
  by hand during an active block, the block is restored within 5s.

## Anti-bypass layers (and what each one actually buys you)

| Layer | What it stops | What it doesn't |
|---|---|---|
| Hosts file + reconciler | Casual bypass via DNS, browser cache, restarting the app | DNS-over-HTTPS in the browser. The browser extension closes this. |
| Browser extension (MV3, Chrome/Edge) | DoH-via-Chrome bypass, incognito mode (with `Allow in incognito` enabled) | A determined user disabling the extension. Adds friction. |
| Frozen session (DB-level) | Trying to cancel an in-progress session through the UI / API | Stopping the service. See next row. |
| NSSM auto-restart-on-exit | Crashes, OOM, programmatic kills | Manual `Stop-Service`. See next row. |
| Task Scheduler watchdog | Manual `Stop-Service` — restarts within 1 minute | Booting into Safe Mode and editing hosts by hand. By design. |
| Uninstall guard | `uninstall-service.ps1` refuses while any frozen session is active. Reads SQLite directly so 'Stop-Service then uninstall' does not bypass it. | `nssm remove` ran directly. Adds friction, not impossibility. |

The combination is roughly **"5+ minutes of deliberate keyboard work to
bypass during a frozen session"** — enough to outlast an impulse.

## Quick start (Windows)

```powershell
# 1. Clone wherever you like
git clone https://github.com/hamjinoo/focus-lock C:\Users\you\focus-lock
cd C:\Users\you\focus-lock

# 2. Install as a Windows service (Administrator)
powershell -ExecutionPolicy Bypass -File scripts\install-service.ps1
powershell -ExecutionPolicy Bypass -File scripts\setup-watchdog.ps1

# 3. Open the UI
start http://127.0.0.1:8765
```

The installer:
- Creates a Python venv and installs deps
- Downloads NSSM (~300 KB from nssm.cc) into `.\tools\`
- Registers the service with auto-start, log rotation, and crash recovery
- Registers a Task Scheduler watchdog

Quick command reference is in [`scripts/COMMANDS.txt`](scripts/COMMANDS.txt).

## Install the browser extension (optional but recommended)

Without the extension, **Chrome's DNS-over-HTTPS bypasses the hosts file**, so
toggling "Use secure DNS" off in `chrome://settings/security` is the
alternative. The extension is the durable answer.

1. Open `chrome://extensions/` and turn on **Developer mode** (top-right).
2. Click **Load unpacked** and select the [`extension/`](extension/) folder
   in this repo.
3. (For incognito coverage) click **Details** on the loaded extension and
   turn on **Allow in Incognito**.

The extension polls `http://127.0.0.1:8765` every 5 seconds and installs
`declarativeNetRequest` rules for every actively-blocked domain. If the
service is unreachable the extension **keeps the last known rules in place**
(unblocking on transient failure would defeat the point).

## Development (WSL / Linux, no admin needed)

```bash
bash scripts/dev.sh
```

The dev runner points hosts/db at `/tmp/focus-lock-*` so it can't damage your
real system. You'll need `python3-venv` (`sudo apt install python3-venv python3-pip`).

Run the end-to-end engine smoke test (stdlib-only, no install required):

```bash
PYTHONPATH=. python3 tests/test_smoke.py
```

It covers idle state, schedule + session activation, hosts-file integrity,
and the frozen-session cancel refusal.

## Project structure

```
focus_lock/
  config.py        # env-overridable paths (HOSTS, DB)
  hosts.py         # marker-delimited block, atomic write, IPv4+IPv6, www variants
  store.py         # SQLite: blocklist, schedules, sessions, audit
  lock.py          # sessions ∪ schedules → effective block state
  reconciler.py    # 5-second loop that forces hosts back to desired state
  main.py          # FastAPI app + sync first-pass reconcile at startup
  models.py        # pydantic schemas

web/               # vanilla HTML+CSS+JS dashboard, no build step
extension/         # Chrome/Edge MV3 — talks to the local service
scripts/           # PowerShell installers + bash dev runner
tests/             # stdlib-only smoke test
```

State (DB and logs) lives at:

- Windows: `C:\ProgramData\focus-lock\` (shared between service + admin scripts)
- Linux:   `~/.local/share/focus-lock/`

No frontend framework, no ORM, no async DB layer. Two third-party Python
packages total (`fastapi`, `uvicorn[standard]`; `pydantic` comes with FastAPI).
The whole thing is < 800 lines of Python.

## Roadmap

- **Phase 1 — local-only MVP** ✅
  - Hosts blocker, schedules, frozen sessions, web UI, reconciler
- **Phase 2 — tamper-resistance** ✅
  - NSSM Windows service, crash auto-restart, Task Scheduler watchdog,
    frozen-aware uninstall guard (SQLite-direct check, not API-dependent)
- **Phase 3 — DoH / incognito coverage** ✅
  - Chrome / Edge MV3 extension that talks to the local service and installs
    declarativeNetRequest rules. Works under DoH. Covers incognito when the
    user enables "Allow in incognito".
- **Phase 4 — process-level blocking** (maybe)
  - Kill listed `.exe` names while a block is active. Currently out of scope.

## Honest limitations

- An administrator can stop both the service and the watchdog, edit hosts,
  disable the extension, and be done in three minutes. That's intended —
  see the design goal above.
- The browser extension is loaded "unpacked" (developer mode) until/unless
  this ships to the Chrome Web Store. A determined user can disable it in
  `chrome://extensions/`.
- Other browsers (Firefox, Safari, Brave with strict DoH) are partially
  covered by hosts but the extension is Chromium-only for now.
- No mobile / no cross-device sync. By design — this is a single-machine
  tool, not a SaaS.
- No code signing. The Windows installer scripts work fine but the project
  is not distributed as a signed binary.

## License

MIT — see [LICENSE](LICENSE).
