"""In-memory device presence: who is connected right now.

The dashboard shows online/offline + connection status from here. Persistent
"last seen" is written to the devices table by the voice router.
"""
import time

# device_id -> {"connected": bool, "since": float, "remote": str, "last_seen": float}
_state: dict[str, dict] = {}


def mark_connected(device_id: str, remote: str) -> None:
    _state[device_id] = {
        "connected": True,
        "since": time.time(),
        "remote": remote,
        "last_seen": time.time(),
    }


def touch(device_id: str) -> None:
    if device_id in _state:
        _state[device_id]["last_seen"] = time.time()


def mark_disconnected(device_id: str) -> None:
    if device_id in _state:
        _state[device_id]["connected"] = False
        _state[device_id]["last_seen"] = time.time()


def get(device_id: str) -> dict | None:
    return _state.get(device_id)


def online_count() -> int:
    return sum(1 for s in _state.values() if s["connected"])


def snapshot() -> dict[str, dict]:
    return dict(_state)
