"""Offline integration test: exercises the real WebSocket handler + SQLite
with Deepgram and Claude stubbed out. No API keys or network needed.

Run: python test_flow_mock.py
"""
import os
import tempfile

# Config reads env at import time, so set everything before importing main.
os.environ.setdefault("ANTHROPIC_API_KEY", "test")
os.environ.setdefault("DEEPGRAM_API_KEY", "test")
os.environ.setdefault("PICO_AUTH_TOKEN", "secret-token")
os.environ["SQLITE_PATH"] = os.path.join(tempfile.mkdtemp(), "test.db")

from fastapi.testclient import TestClient  # noqa: E402
import main  # noqa: E402


class FakeStreamer:
    """Stand-in for DeepgramStreamer: swallows audio, returns canned text."""
    sent_bytes = 0

    async def open(self):
        pass

    async def send(self, pcm: bytes):
        FakeStreamer.sent_bytes += len(pcm)

    async def finish(self, timeout: float = 5.0):
        return "what is the capital of france"


async def fake_generate_reply(history, transcript):
    # Prove history threads through: reply references how many prior turns.
    return f"[{len(history)} prior] Paris. You said: {transcript}"


def run():
    main.DeepgramStreamer = FakeStreamer
    main.generate_reply = fake_generate_reply

    # Context-manager form triggers the app startup event (db.init_db).
    client = TestClient(main.app)
    client.__enter__()
    with client.websocket_connect("/ws/voice") as ws:
        # Auth
        ws.send_json({"type": "auth", "token": "secret-token", "device_id": "pico-test"})
        assert ws.receive_json() == {"type": "ready"}, "auth handshake failed"

        # --- Turn 1 ---
        ws.send_json({"type": "start"})
        for _ in range(4):
            ws.send_bytes(b"\x00\x01" * 256)  # 512-byte PCM frames
        ws.send_json({"type": "stop"})
        r1 = ws.receive_json()
        assert r1["type"] == "response", r1
        assert "0 prior" in r1["text"], r1  # no history yet
        print("Turn 1 reply:", r1["text"])

        # --- Turn 2: history from turn 1 must be present ---
        ws.send_json({"type": "start"})
        ws.send_bytes(b"\x00\x01" * 256)
        ws.send_json({"type": "stop"})
        r2 = ws.receive_json()
        assert r2["type"] == "response", r2
        assert "2 prior" in r2["text"], f"expected 2 stored turns, got: {r2}"
        print("Turn 2 reply:", r2["text"])

    assert FakeStreamer.sent_bytes == 512 * 5, FakeStreamer.sent_bytes
    print(f"Forwarded {FakeStreamer.sent_bytes} PCM bytes to (fake) STT")

    # Bad auth is rejected.
    with client.websocket_connect("/ws/voice") as ws:
        ws.send_json({"type": "auth", "token": "WRONG"})
        msg = ws.receive_json()
        assert msg["type"] == "error", msg
        print("Bad auth rejected:", msg)

    client.__exit__(None, None, None)
    print("\nALL CHECKS PASSED")


if __name__ == "__main__":
    run()
