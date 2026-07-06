"""Offline integration test for the agent platform. Deepgram + OpenAI are
stubbed, so no API keys or network are needed.

Covers: startup, admin login, settings update, device creation, the voice WS
turn (auth -> stream -> stop -> response), persistence, presence, integrations
toggle, and logs/events. Run: python test_flow_mock.py
"""
import os
import tempfile

os.environ["SQLITE_PATH"] = os.path.join(tempfile.mkdtemp(), "test.db")
os.environ["ADMIN_PASSWORD"] = "admin"

from fastapi.testclient import TestClient  # noqa: E402
from app import main  # noqa: E402
from app.routers import voice  # noqa: E402


class FakeStreamer:
    async def open(self): pass
    async def send(self, pcm): pass
    async def finish(self, timeout: float = 5.0): return "what time is it"


async def fake_generate_reply(device_id, history, transcript):
    return f"[{len(history)} prior] you said: {transcript}"


def h(token):
    return {"Authorization": "Bearer " + token}


def run():
    voice.DeepgramStreamer = FakeStreamer
    voice.generate_reply = fake_generate_reply

    client = TestClient(main.app)
    client.__enter__()  # trigger startup (db, settings, tools, admin seed)

    # --- admin login (default password) ---
    r = client.post("/api/login", json={"password": "admin"})
    assert r.status_code == 200, r.text
    tok = r.json()["token"]
    assert r.json()["must_change"] is True
    print("login ok; must_change flagged")

    # --- wrong password rejected ---
    assert client.post("/api/login", json={"password": "nope"}).status_code == 401

    # --- unauthenticated admin call rejected ---
    assert client.get("/api/settings").status_code == 401

    # --- settings: set keys + model; secrets come back masked ---
    client.put("/api/settings", headers=h(tok), json={
        "openai_api_key": "sk-test-1234",
        "deepgram_api_key": "dg-test-5678",
        "openai_model": "gpt-4o-mini",
        "system_prompt": "be terse",
    })
    s = client.get("/api/settings", headers=h(tok)).json()
    assert s["openai_api_key"]["set"] is True and s["openai_api_key"]["hint"].endswith("1234")
    assert "sk-test" not in str(s["openai_api_key"]), "raw secret leaked!"
    assert s["openai_model"] == "gpt-4o-mini"
    print("settings saved; secrets masked:", s["openai_api_key"])

    # blank secret must NOT wipe stored key
    client.put("/api/settings", headers=h(tok), json={"openai_api_key": ""})
    s2 = client.get("/api/settings", headers=h(tok)).json()
    assert s2["openai_api_key"]["set"] is True, "blank field wiped the key!"
    print("blank secret preserved existing key")

    # --- create a device; token returned once ---
    dev = client.post("/api/devices", headers=h(tok),
                      json={"name": "Test Pico", "device_id": "pico-test"}).json()
    device_token = dev["token"]
    assert dev["device_id"] == "pico-test" and device_token
    print("device created; token issued")

    # list never returns the full token
    devs = client.get("/api/devices", headers=h(tok)).json()
    assert device_token not in str(devs), "device token leaked in list!"

    # --- voice WS turn ---
    with client.websocket_connect("/ws/voice") as ws:
        ws.send_json({"type": "auth", "token": device_token, "device_id": "pico-test"})
        assert ws.receive_json() == {"type": "ready"}
        ws.send_json({"type": "start"})
        for _ in range(3):
            ws.send_bytes(b"\x00\x01" * 256)
        ws.send_json({"type": "stop"})
        resp = ws.receive_json()
        assert resp["type"] == "response" and "you said: what time is it" in resp["text"], resp
        print("voice turn ok:", resp["text"])

        # presence shows online during the session
        st = client.get("/api/status", headers=h(tok)).json()
        assert st["online_devices"] == 1, st

    # --- bad device token rejected ---
    with client.websocket_connect("/ws/voice") as ws:
        ws.send_json({"type": "auth", "token": "WRONG"})
        assert ws.receive_json()["type"] == "error"
    print("bad device token rejected")

    # --- conversation persisted ---
    conv = client.get("/api/conversations", headers=h(tok)).json()
    roles = {c["role"] for c in conv}
    assert roles == {"user", "assistant"}, conv
    print(f"conversation persisted ({len(conv)} rows)")

    # clear history
    client.delete("/api/conversations", headers=h(tok))
    assert client.get("/api/conversations", headers=h(tok)).json() == []
    print("history cleared")

    # --- integrations: safe builtin active, integration gated ---
    ints = {t["name"]: t for t in client.get("/api/integrations", headers=h(tok)).json()}
    assert ints["get_current_time"]["active"] is True
    assert ints["email_read"]["active"] is False and ints["email_read"]["requires_auth"]
    # enabling but not authorizing keeps it inactive
    client.patch("/api/integrations/email_read", headers=h(tok), json={"enabled": True})
    e = client.get("/api/integrations", headers=h(tok)).json()
    e = {t["name"]: t for t in e}["email_read"]
    assert e["enabled"] is True and e["active"] is False, "gated tool active without auth!"
    client.patch("/api/integrations/email_read", headers=h(tok), json={"authorized": True})
    e = {t["name"]: t for t in client.get("/api/integrations", headers=h(tok)).json()}["email_read"]
    assert e["active"] is True
    print("integration gating verified (enable+authorize required)")

    # --- events + logs populated ---
    events = client.get("/api/events", headers=h(tok)).json()
    assert any("connected" in ev["message"] for ev in events), events
    logs = client.get("/api/logs", headers=h(tok)).json()
    assert len(logs) > 0
    print(f"events={len(events)} logs={len(logs)}")

    # --- export/import config ---
    exp = client.get("/api/config/export?include_secrets=false", headers=h(tok)).json()
    assert "openai_api_key" not in exp["settings"], "secret exported without opt-in!"
    exp_s = client.get("/api/config/export?include_secrets=true", headers=h(tok)).json()
    assert exp_s["settings"]["openai_api_key"] == "sk-test-1234"
    print("export honors include_secrets")

    # --- change admin password ---
    assert client.post("/api/password", headers=h(tok), json={"new_password": "hunter2"}).status_code == 200
    assert client.post("/api/login", json={"password": "admin"}).status_code == 401
    assert client.post("/api/login", json={"password": "hunter2"}).status_code == 200
    print("admin password change works")

    client.__exit__(None, None, None)
    print("\nALL CHECKS PASSED")


if __name__ == "__main__":
    run()
