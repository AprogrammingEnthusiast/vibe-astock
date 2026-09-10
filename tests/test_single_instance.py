"""Shared accounts use one application, without provisioned worker slots."""
from fastapi.testclient import TestClient

import sharing
import sharing_admin
import subprocess
import sys
from pathlib import Path
import json


def test_invite_without_workers(tmp_path, monkeypatch):
    monkeypatch.setattr(sharing, "DB", tmp_path / "accounts.sqlite3")
    monkeypatch.setenv("VIBE_COOKIE_SECURE", "0")
    sharing.initialize()
    invite = sharing_admin.provision("owner", owner=True)
    with TestClient(sharing.app) as client:
        client.headers["X-Vibe-Request"] = "1"
        assert client.post("/api/account/activate", json={"username": "owner", "password": "a-good-password", "invite": invite}).status_code == 200
        client.headers["X-Vibe-Account"] = client.get("/api/account/me").json()["user"]["id"]
        result = client.post("/api/admin/invitations", json={"username": "friend"})
        assert result.status_code == 200, result.text
        assert client.post("/api/admin/invitations", json={"username": "friend"}).status_code == 409
    assert len(sharing_admin.manifest(8910, True)["services"]) == 1


def test_single_process_account_boundaries(tmp_path):
    result = subprocess.run([sys.executable, str(Path(__file__).with_name("single_instance_check.py")), str(tmp_path)],
                            capture_output=True, text=True, timeout=90)
    assert result.returncode == 0, result.stdout + result.stderr


def test_post_review_subprocess_has_only_the_callers_home(tmp_path, monkeypatch):
    import account_context
    from review_agent.post_review import capture_bounded
    monkeypatch.setattr(account_context, "ENABLED", True)
    monkeypatch.setenv("VIBE_SHARED_APP", "1")
    monkeypatch.setenv("OPENAI_API_KEY", "host-secret")
    captured = []

    class Process:
        returncode = 0

        def __init__(self, command, **kwargs):
            captured.append(kwargs["env"])
            Path(command[-1]).write_text(json.dumps({"archive": {"ok": True}}))

        def poll(self):
            return 0

    monkeypatch.setattr(subprocess, "Popen", Process)
    for uid in ("a" * 32, "b" * 32):
        with account_context.bind({"id": uid}, tmp_path / "homes"):
            assert capture_bounded("2026-09-08")["archive"]["ok"]
            assert captured[-1]["HOME"] == str(tmp_path / "homes" / uid)
            assert "OPENAI_API_KEY" not in captured[-1] and "VIBE_SHARED_APP" not in captured[-1]
    assert captured[0]["VR_DATA_DIR"] != captured[1]["VR_DATA_DIR"]
