"""Hosts file management.

Owns a marker-delimited block inside the system hosts file. Read/replace is
idempotent and atomic — write to a temp file in the same dir, then rename.
Anything outside the markers is preserved untouched.
"""
from __future__ import annotations

import os
import re
import tempfile
from dataclasses import dataclass
from pathlib import Path

from .config import HOSTS_PATH, MARKER_BEGIN, MARKER_END, REDIRECT_IP

_BLOCK_RE = re.compile(
    rf"\n?{re.escape(MARKER_BEGIN)}.*?{re.escape(MARKER_END)}\n?",
    re.DOTALL,
)


@dataclass
class HostsState:
    domains: list[str]
    """Domains currently being redirected. Empty list = no managed block."""


def _expand(domain: str) -> list[str]:
    d = domain.strip().lower().lstrip(".")
    if not d:
        return []
    if d.startswith("www."):
        return [d, d[4:]]
    return [d, f"www.{d}"]


def _render_block(domains: list[str]) -> str:
    seen: set[str] = set()
    lines: list[str] = [MARKER_BEGIN]
    for d in domains:
        for variant in _expand(d):
            if variant in seen:
                continue
            seen.add(variant)
            lines.append(f"{REDIRECT_IP}\t{variant}")
            lines.append(f"::1\t{variant}")
    lines.append(MARKER_END)
    return "\n".join(lines)


def _atomic_write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".focus-lock-", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(content)
        os.replace(tmp, path)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def read_state(path: Path = HOSTS_PATH) -> HostsState:
    if not path.exists():
        return HostsState(domains=[])
    text = path.read_text(encoding="utf-8", errors="replace")
    match = _BLOCK_RE.search(text)
    if not match:
        return HostsState(domains=[])
    found: list[str] = []
    seen: set[str] = set()
    for line in match.group(0).splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split()
        if len(parts) >= 2:
            host = parts[1].lower()
            base = host[4:] if host.startswith("www.") else host
            if base not in seen:
                seen.add(base)
                found.append(base)
    return HostsState(domains=found)


def write_block(domains: list[str], path: Path = HOSTS_PATH) -> None:
    """Replace the managed block. Empty list removes the block entirely."""
    if not path.exists():
        raise FileNotFoundError(f"hosts file not found: {path}")
    text = path.read_text(encoding="utf-8", errors="replace")
    stripped = _BLOCK_RE.sub("\n", text)
    if not domains:
        _atomic_write(path, stripped)
        return
    new = stripped.rstrip("\n") + "\n\n" + _render_block(domains) + "\n"
    _atomic_write(path, new)


def reconcile(desired: list[str], path: Path = HOSTS_PATH) -> bool:
    """Write desired list only if it differs from current. Returns True if changed."""
    current = read_state(path).domains
    if sorted(set(current)) == sorted(set(d.strip().lower().lstrip(".") for d in desired if d.strip())):
        return False
    write_block(desired, path)
    return True
