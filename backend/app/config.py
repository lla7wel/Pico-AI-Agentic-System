"""Bootstrap-only configuration.

Almost everything is now configured at RUNTIME through the dashboard and
stored in SQLite (see settings_store.py). This module holds only the few
values needed to boot the process before the settings store is available.
"""
import os

# Where the SQLite database (settings, devices, conversations, events) lives.
# On Fly.io this is the mounted volume; locally it defaults to ./app.db.
SQLITE_PATH = os.environ.get("SQLITE_PATH", "./app.db")

# First-run admin password. Used ONLY to seed the dashboard login the first
# time the DB is created; after that the password is managed in the dashboard
# and this env var is ignored. If unset, the seed password is "admin" and the
# dashboard will nag you to change it.
BOOTSTRAP_ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "admin")

# Dashboard session lifetime.
SESSION_TTL_HOURS = int(os.environ.get("SESSION_TTL_HOURS", "12"))

# Optional: legacy single-device token to seed a device row on first run, so
# an already-flashed Pico keeps working after the upgrade. Ignored once any
# device exists.
LEGACY_PICO_AUTH_TOKEN = os.environ.get("PICO_AUTH_TOKEN", "")

# In-memory log ring size (dashboard "Logs" tail).
LOG_RING_SIZE = int(os.environ.get("LOG_RING_SIZE", "1000"))
