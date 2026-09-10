from __future__ import annotations

import sys
import time

from fastapi.testclient import TestClient

import server


def test_backend_exposes_codex_device_authorization(tmp_path, monkeypatch):
    """The browser can start, inspect, and complete Docker Codex login."""
    finish = tmp_path / "finish"
    codex_home = tmp_path / "codex-home"
    fake = tmp_path / "fake_codex.py"
    fake.write_text(
        """
import os
import sys
import time
from pathlib import Path

home = Path(os.environ["CODEX_HOME"])
args = sys.argv[1:]
if args == ["login", "status"]:
    raise SystemExit(0 if (home / "auth.ok").exists() else 1)
if args != ["login", "--device-auth"]:
    raise SystemExit(2)
home.mkdir(parents=True, exist_ok=True)
print("https://auth.openai.com/codex/device", flush=True)
print("Enter this one-time code (expires in 15 minutes)", flush=True)
print("  TEST-", end="", flush=True)
time.sleep(0.02)
print("1234", flush=True)
print("private diagnostic", file=sys.stderr, flush=True)
while not Path(os.environ["TEST_CODEX_LOGIN_FINISH"]).exists():
    time.sleep(0.02)
(home / "auth.ok").write_text("ok", encoding="utf-8")
""",
        encoding="utf-8",
    )
    monkeypatch.setenv("CODEX_HOME", str(codex_home))
    monkeypatch.setenv("TEST_CODEX_LOGIN_FINISH", str(finish))
    monkeypatch.setattr(server, "_ALLOWED_CLI_KINDS", frozenset({"claude", "codex"}))
    monkeypatch.setattr(server, "_codex_command", lambda: [sys.executable, str(fake)], raising=False)
    client = TestClient(server.app, base_url="http://localhost")

    assert client.post(
        "/api/cli/codex/login", headers={"Origin": "https://evil.example"}
    ).status_code == 403
    assert client.post("/api/cli/codex/login").json() == {"state": "started"}
    assert client.post("/api/cli/codex/login").json() == {"state": "pending"}

    deadline = time.time() + 3
    codex = None
    while time.time() < deadline:
        payload = client.get("/api/cli/available").json()
        codex = next(item for item in payload["clis"] if item["kind"] == "codex")
        if codex.get("deviceAuth"):
            break
        time.sleep(0.02)
    assert codex is not None
    assert codex["status"] == "login_pending"
    assert codex["deviceAuth"] == {
        "verificationUrl": "https://auth.openai.com/codex/device",
        "userCode": "TEST-1234",
    }
    assert "private diagnostic" not in str(payload)

    finish.write_text("ok", encoding="utf-8")
    deadline = time.time() + 3
    while time.time() < deadline:
        payload = client.get("/api/cli/available").json()
        codex = next(item for item in payload["clis"] if item["kind"] == "codex")
        if codex.get("authenticated"):
            break
        time.sleep(0.02)
    assert codex["status"] == "ready"
    assert codex["authenticated"] is True
    assert "deviceAuth" not in codex
