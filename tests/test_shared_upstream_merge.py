import json
from pathlib import Path
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

import sharing_worker
from sharing_schema import public_payload


def test_new_connection_is_worker_private_and_validated(tmp_path, monkeypatch):
    monkeypatch.setattr(sharing_worker, "ENABLED", True)
    monkeypatch.setattr(sharing_worker, "PROFILE", tmp_path / "llm.json")
    monkeypatch.setenv("VIBE_WORKER_KEY", "worker-a")
    app = FastAPI()
    sharing_worker.install(app)
    client = TestClient(app)
    path = "/api/personal/agent-connection"
    cfg = {"provider": "codex-private", "model": "gpt-5.5", "baseURL": "", "apiKey": ""}
    assert client.put(path, json={"llm": cfg}).status_code == 401
    assert client.get(path, headers={"X-Vibe-Worker": "worker-b"}).status_code == 401
    client.headers["X-Vibe-Worker"] = "worker-a"
    assert client.put(path, json={"llm": cfg}).status_code == 200
    assert client.get(path).json()["llm"] == cfg
    assert client.put(path, json={"llm": {**cfg, "provider": "api-compatible", "baseURL": "http://localhost"}}).status_code == 400
    assert client.get(path).json()["llm"] == cfg
    for invalid in ("bad", [], {**cfg, "provider": "unknown"}, {**cfg, "extra": "secret"}):
        assert client.put(path, json={"llm": invalid}).status_code == 400
    assert client.get(path).json()["llm"] == cfg
    assert not sharing_worker.PROFILE.exists()


def test_private_login_copy_preserves_original_and_existing_new_login(tmp_path, monkeypatch):
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    old = tmp_path / ".codex" / "auth.json"
    old.parent.mkdir()
    old.write_text('{"test":"old"}')
    runtime = SimpleNamespace(home=tmp_path / "new")
    runtime.home.mkdir()
    sharing_worker.prepare_agent(runtime)
    assert (runtime.home / "auth.json").read_bytes() == old.read_bytes()
    (runtime.home / "auth.json").write_text('{"test":"new"}')
    sharing_worker.prepare_agent(runtime)
    assert json.loads((runtime.home / "auth.json").read_text())["test"] == "new"
    assert json.loads(old.read_text())["test"] == "old"


def test_shared_evidence_keeps_history_cutoff_and_source_privacy(monkeypatch, tmp_path):
    monkeypatch.setattr(sharing_worker, "ENABLED", True)
    monkeypatch.setenv("VIBE_WORKER_KEY", "test-worker")
    monkeypatch.setattr(sharing_worker.requests, "get", lambda *a, **kw: SimpleNamespace(
        raise_for_status=lambda: None, json=lambda: {"dates": ["2026-09-08", "2026-09-07"]}))
    fetched = []
    def report(day, version=None):
        fetched.append((day, version))
        return {"target_date": day, "focus_md": "public market", "emotion_metrics": {}, "market_facts": {}}
    monkeypatch.setattr(sharing_worker, "shared_review", report)
    from review_agent.evidence import build_bundle
    bundle = build_bundle(tmp_path, "2026-09-07", version="a" * 64)
    assert bundle["dates"] == ["2026-09-07"]
    assert fetched == [("2026-09-07", "a" * 64)]
    assert not list(tmp_path.iterdir())
    payload = public_payload({"focus_md": "public", "apiKey": "secret", "conversation": "private",
        "ai_source": {"provider": "api-compatible", "model": "model", "baseURL": "private-url", "apiKey": "secret"}})
    assert payload == {"focus_md": "public", "ai_source": {"provider": "api-compatible", "model": "model"}}
