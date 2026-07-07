#!/usr/bin/env bash
# One-command local start: creates the venv on first run, installs
# dependencies, and launches the backend on http://localhost:8080.
set -euo pipefail
cd "$(dirname "$0")"

if [ ! -d .venv ]; then
  echo "Creating virtual environment..."
  python3 -m venv .venv
fi

source .venv/bin/activate
pip install --quiet -r requirements.txt

export SQLITE_PATH="${SQLITE_PATH:-./app.db}"
export ADMIN_PASSWORD="${ADMIN_PASSWORD:-admin}"

echo "Dashboard: http://localhost:8080 (first-run password: $ADMIN_PASSWORD)"
exec uvicorn app.main:app --host 0.0.0.0 --port 8080
