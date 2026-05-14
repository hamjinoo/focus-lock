#!/usr/bin/env bash
# Dev runner for WSL/Linux. Uses a temp hosts file so no admin needed.
set -euo pipefail
cd "$(dirname "$0")/.."

TMP_HOSTS="${FOCUS_LOCK_HOSTS:-/tmp/focus-lock-hosts}"
TMP_DB="${FOCUS_LOCK_DB:-/tmp/focus-lock-state.db}"

if [ ! -f "$TMP_HOSTS" ]; then
    printf "127.0.0.1\tlocalhost\n" > "$TMP_HOSTS"
fi

export FOCUS_LOCK_HOSTS="$TMP_HOSTS"
export FOCUS_LOCK_DB="$TMP_DB"

if [ ! -d .venv ]; then
    python3 -m venv .venv
fi
# shellcheck disable=SC1091
source .venv/bin/activate
pip install --quiet --upgrade pip
pip install --quiet -r requirements.txt

echo "focus-lock dev → http://127.0.0.1:8765"
echo "  hosts:  $TMP_HOSTS"
echo "  db:     $TMP_DB"
exec uvicorn focus_lock.main:app --host 127.0.0.1 --port 8765 --reload
