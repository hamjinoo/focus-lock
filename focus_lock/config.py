"""Runtime configuration. Lets tests point hosts/db to safe paths."""
from __future__ import annotations

import os
import sys
from pathlib import Path


def default_hosts_path() -> Path:
    if override := os.environ.get("FOCUS_LOCK_HOSTS"):
        return Path(override)
    if sys.platform.startswith("win"):
        return Path(r"C:\Windows\System32\drivers\etc\hosts")
    return Path("/etc/hosts")


def default_db_path() -> Path:
    if override := os.environ.get("FOCUS_LOCK_DB"):
        return Path(override)
    if sys.platform.startswith("win"):
        # ProgramData is readable by all authenticated users; needed so the
        # service (LocalSystem) and admin-launched scripts share one DB.
        base = Path(os.environ.get("PROGRAMDATA", r"C:\ProgramData")) / "focus-lock"
    else:
        base = Path.home() / ".local" / "share" / "focus-lock"
    base.mkdir(parents=True, exist_ok=True)
    return base / "state.db"


HOSTS_PATH = default_hosts_path()
DB_PATH = default_db_path()

REDIRECT_IP = "127.0.0.1"
MARKER_BEGIN = "# >>> focus-lock managed block >>>"
MARKER_END = "# <<< focus-lock managed block <<<"
