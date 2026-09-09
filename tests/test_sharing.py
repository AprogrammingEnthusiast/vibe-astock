from __future__ import annotations

import json
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

import sharing
import sharing_admin


@pytest.fixture
def site(tmp_path, monkeypatch):
    monkeypatch.setattr(sharing, "DB", tmp_path / "accounts.sqlite3")
    monkeypatch.setenv("VIBE_COOKIE_SECURE", "0")
    sharing.initialize()
    clients = []
    for name in ("alice", "bobby"):
        invite = sharing_admin.provision(name, owner=name == "alice")
        client = TestClient(sharing.app, headers={"X-Vibe-Request": "1"})
        result = client.post("/api/account/activate", json={"username": name, "password": "a-good-test-password", "invite": invite})
        assert result.status_code == 200, result.text
        assert "httponly" in result.headers["set-cookie"].lower()
        user = client.get("/api/account/me").json()["user"]
        client.headers["X-Vibe-Account"] = user["id"]
        clients.append(client)
    yield clients
    for client in clients:
        client.close()


def test_account_identity_watchlist_and_logout(site):
    alice, bob = site
    assert alice.put("/api/account/watchlist", json={"codes": ["600519"]}).status_code == 200
    assert alice.get("/api/account/me").json()["watchlist"] == ["600519"]
    assert bob.get("/api/account/me").json()["watchlist"] is None
    assert bob.put("/api/account/watchlist", json={"codes": ["../alice"]}).status_code == 400
    # Forged account identifiers cannot select another user's state.
    assert bob.put("/api/account/watchlist", headers={"X-Vibe-Account": alice.headers["X-Vibe-Account"]}, json={"codes": []}).status_code == 401
    cookie = alice.cookies.get(sharing.COOKIE)
    assert alice.post("/api/account/logout").status_code == 200
    assert alice.get("/api/account/me", headers={"Cookie": f"{sharing.COOKIE}={cookie}"}).json()["user"] is None
    assert bob.get("/api/account/me").json()["user"]["username"] == "bobby"


def test_csrf_invite_reuse_and_failed_logins(site):
    alice, _ = site
    assert alice.post("/api/account/logout", headers={"Origin": "https://evil.example"}).status_code == 403
    assert alice.put("/api/account/watchlist", headers={"X-Vibe-Request": ""}, json={"codes": []}).status_code == 403
    fresh = TestClient(sharing.app, headers={"X-Vibe-Request": "1"})
    assert fresh.post("/api/account/activate", json={"username": "alice", "password": "a-good-test-password", "invite": "wrong"}).status_code == 401
    for _ in range(10):
        last = fresh.post("/api/account/login", json={"username": "alice", "password": "wrong"})
    assert last.status_code == 429
    assert fresh.get("/api/journal").status_code == 401


def test_public_review_versions_never_call_ai(site, monkeypatch):
    alice, bob = site
    monkeypatch.setattr(sharing, "forward", lambda *a: pytest.fail("Reading public review invoked a worker"))
    with sharing.connect() as db:
        owners = [dict(r) for r in db.execute("SELECT * FROM users ORDER BY username")]
    payload = {"target_date": "2026-09-07", "focus_md": "public market facts " * 30,
               "journal": "PRIVATE", "apiKey": "SECRET", "complete": True}
    ids = []
    for u in owners:
        result = alice.post("/internal/reviews", headers={"X-Vibe-Worker": u["worker_key"]}, json=payload)
        assert result.status_code == 200, result.text
        ids.append(result.json()["id"])
    assert alice.post("/internal/reviews", json=payload).status_code == 401
    latest = bob.get("/api/review/latest").json()
    assert latest["publication"]["author"] == "bobby"
    assert "PRIVATE" not in json.dumps(latest) and "SECRET" not in json.dumps(latest)
    assert len(bob.get("/api/review/versions?date=2026-09-07").json()["versions"]) == 2
    assert bob.get("/api/review/latest", params={"version": ids[0]}).json()["publication"]["author"] == "alice"
    assert bob.get("/api/review/dates").json()["dates"] == ["2026-09-07"]
    # Retrying an outbox item is idempotent.
    alice.post("/internal/reviews", headers={"X-Vibe-Worker": owners[0]["worker_key"]}, json=payload)
    assert len(alice.get("/api/review/versions?date=2026-09-07").json()["versions"]) == 2
    deepdive = {"run_type": "stock_deepdive", "trade_date": "2026-09-07", "code": "600519",
                "verdict_md": "public company research " * 30, "journal": "PRIVATE"}
    assert alice.post("/internal/reviews", headers={"X-Vibe-Worker": owners[0]["worker_key"]}, json=deepdive).status_code == 200
    assert bob.get("/api/deepdive/latest").json()["code"] == "600519"
    assert bob.get("/api/review/latest").json()["publication"]["author"] == "bobby"


def test_private_proxy_is_bound_to_session_and_preserves_streams(site, monkeypatch):
    alice, bob = site
    calls, closed = [], []
    def fake_request(method, url, **kwargs):
        assert kwargs["headers"]["Host"] == "localhost"
        calls.append((url, kwargs))
        return SimpleNamespace(status_code=200, headers={"Content-Type": "application/x-ndjson"},
            iter_content=lambda **kw: iter([b'{"type":"delta","text":"ok"}\n', b'{"type":"done"}\n']),
            close=lambda: closed.append(True))
    monkeypatch.setattr(sharing.requests, "request", fake_request)
    for client in (alice, bob):
        response = client.post("/api/chat", json={"user_id": "alice", "worker": "http://evil", "messages": []}, headers={"Authorization": "Bearer forged", "X-Vibe-Worker": "forged"})
        assert response.status_code == 200 and '"done"' in response.text
        assert response.headers["cache-control"] == "no-store"
    assert len(closed) == 2
    assert calls[0][0] != calls[1][0]
    assert calls[0][1]["headers"]["X-Vibe-Worker"] != calls[1][1]["headers"]["X-Vibe-Worker"]
    assert all("forged" not in str(options["headers"]) for _, options in calls)


def test_deployment_has_distinct_volumes_networks_and_no_owner_fallback(site):
    config = sharing_admin.manifest(8910, True)
    workers = [s for key, s in config["services"].items() if key.startswith("worker-")]
    assert len(workers) == 2
    assert workers[0]["volumes"] != workers[1]["volumes"]
    assert workers[0]["networks"] != workers[1]["networks"]
    for worker in workers:
        assert "ports" not in worker and "env_file" not in worker
        assert "MIMO_API_KEY" not in worker["environment"]
        assert worker["read_only"] and "no-new-privileges:true" in worker["security_opt"]
    assert config["services"]["gateway"]["environment"]["VIBE_COOKIE_SECURE"] == "1"


def test_admin_invites_use_ready_private_slots_and_activate_once(site, monkeypatch):
    alice, bob = site
    assert bob.get("/api/admin/invitations").status_code == 403
    assert bob.post("/api/admin/invitations", json={"username": "friend"}).status_code == 403
    assert alice.post("/api/admin/invitations", headers={"Origin": "https://evil.example"}, json={"username": "friend"}).status_code == 403
    assert alice.post("/api/admin/invitations", json={"username": "../owner"}).status_code == 400
    assert alice.post("/api/admin/invitations", json={"username": "friend"}).status_code == 409
    sharing_admin.add_slots(1)
    before = sharing_admin.manifest(8910, True)
    listing = alice.get("/api/admin/invitations").json()
    assert listing["available"] == 1 and len(listing["members"]) == 2
    assert "worker_key" not in json.dumps(listing) and "password" not in json.dumps(listing)
    monkeypatch.setattr(sharing.requests, "get", lambda *a, **kw: SimpleNamespace(status_code=503))
    assert alice.post("/api/admin/invitations", json={"username": "friend"}).status_code == 503
    assert alice.get("/api/admin/invitations").json()["available"] == 1
    import server
    worker = TestClient(server.app, base_url="http://worker-private:8910")
    assert worker.get("/api/health").status_code == 403
    def worker_health(url, **kwargs):
        return worker.get("/api/health", headers=kwargs.get("headers", {}))
    monkeypatch.setattr(sharing.requests, "get", worker_health)
    assert alice.post("/api/admin/invitations", json={"username": "bobby"}).status_code == 409
    response = alice.post("/api/admin/invitations", json={"username": "friend"})
    assert response.status_code == 200
    invitation = response.json()
    assert alice.get("/api/admin/invitations").json()["available"] == 0
    assert sharing_admin.manifest(8910, True) == before  # No shared homes or container mutation.
    with sharing.connect() as db:
        friend = dict(db.execute("SELECT * FROM users WHERE username='friend'").fetchone())
    assert friend["invite"] == sharing.digest(invitation["invite"]) and not friend["admin"]
    with TestClient(sharing.app, headers={"X-Vibe-Request": "1"}) as client:
        payload = {**invitation, "password": "friends-own-password"}
        assert client.post("/api/account/activate", json=payload).status_code == 200
        me = client.get("/api/account/me").json()
        assert me["watchlist"] is None and me["user"]["username"] == "friend"
        assert client.post("/api/account/activate", json=payload).status_code == 401
    assert alice.get("/api/admin/invitations").json()["members"][-1]["status"] == "active"


def test_worker_llm_fails_closed_and_pins_personal_model(tmp_path, monkeypatch):
    import server
    import sharing_worker as worker
    monkeypatch.setenv("VIBE_WORKER_KEY", "personal-worker-key")
    monkeypatch.setenv("CODEX_HOME", str(tmp_path / "personal-codex"))
    monkeypatch.setenv("OPENAI_API_KEY", "owner-key-must-not-leak")
    monkeypatch.setattr(worker, "PROFILE", tmp_path / "llm.json")
    from duanxian.config import make_llm
    with pytest.raises(RuntimeError, match="自己的配置"):
        make_llm()
    worker.write_profile({"provider": "cli-codex", "model": "personal-model"})
    llm = make_llm()
    assert llm.model == "personal-model"
    runtime = sys.modules["app"].cli_runtime
    env = runtime.codex_env()
    assert env["CODEX_HOME"] == str(tmp_path / "personal-codex")
    assert "OPENAI_API_KEY" not in env and "VIBE_WORKER_KEY" not in env
    args = runtime._execution_args("codex", ["exec", "--skip-git-repo-check", "-"])
    assert "--ignore-user-config" in args and "read-only" in args and "shell_tool" in args
    monkeypatch.setattr(worker, "ENABLED", True)
    from fastapi import HTTPException
    with runtime.credential_lock:
        with pytest.raises(HTTPException) as busy:
            server._codex_account_change(lambda: "changed")()
        assert busy.value.status_code == 409


def test_failed_publication_keeps_local_outbox(tmp_path, monkeypatch):
    import sharing_worker as worker
    monkeypatch.setattr(worker, "ENABLED", True)
    monkeypatch.setattr(worker, "OUTBOX", tmp_path)
    monkeypatch.setenv("VIBE_WORKER_KEY", "test-key")
    payload = {"target_date": "2026-09-07", "focus_md": "public " * 40, "private": "secret"}
    def fail(*a, **kw):
        raise worker.requests.ConnectionError()
    monkeypatch.setattr(worker.requests, "post", fail)
    worker.queue_publication(payload)
    worker.flush_publications()
    files = list(tmp_path.glob("*.json"))
    assert len(files) == 1 and "secret" not in files[0].read_text()
    monkeypatch.setattr(worker.requests, "post", lambda *a, **kw: SimpleNamespace(raise_for_status=lambda: None))
    worker.flush_publications()
    assert not list(tmp_path.glob("*.json"))


@pytest.mark.parametrize("source", ["shared", "local", "missing", "unavailable"])
def test_shared_review_reuses_completed_result_before_credentials(monkeypatch, source):
    import server
    monkeypatch.setattr(server.sharing_worker, "ENABLED", True)
    monkeypatch.setattr(server, "_origin_ok", lambda r: True)
    monkeypatch.setattr(server.trade_calendar, "is_settled", lambda d: True)
    from duanxian.roles import ROLES
    complete = {"focus": {"ok": True}, "emotion_metrics": {"ok": True},
                "market_facts": {"ok": True}, "analysts": [{"key": r.key, "html": "report"} for r in ROLES]}
    monkeypatch.setattr(server.review_store, "load", lambda d: complete if source == "local" else None)
    def shared(date):
        assert date == "2026-09-07"
        if source == "unavailable":
            raise RuntimeError("公共复盘暂时读取失败")
        return complete if source == "shared" else {}
    monkeypatch.setattr(server.sharing_worker, "shared_review", shared)
    monkeypatch.setattr(server.sharing_worker, "selected_llm", lambda: None)
    monkeypatch.setattr(server, "_job", {"running": False})
    starts = []
    monkeypatch.setattr(server.threading, "Thread", lambda **kw: SimpleNamespace(start=lambda: starts.append(kw)))
    result = TestClient(server.app, base_url="http://localhost").post("/api/review/run?date=2026-09-07&regenerate=true")
    assert not starts
    if source in {"shared", "local"}:
        assert result.status_code == 200 and result.json()["already_done"]
    else:
        assert result.status_code == (503 if source == "unavailable" else 400)


def test_shared_completed_version_survives_later_partial_review(site):
    alice, bob = site
    with sharing.connect() as db:
        owners = [dict(r) for r in db.execute("SELECT * FROM users ORDER BY username")]
    ids = []
    for owner, complete in zip(owners, [True, False]):
        result = alice.post("/internal/reviews", headers={"X-Vibe-Worker": owner["worker_key"]},
                            json={"target_date": "2026-09-07", "focus_md": "public " * 40, "complete": complete})
        assert result.status_code == 200
        ids.append(result.json()["id"])
    for client in (alice, bob):
        assert client.get("/api/review/latest?date=2026-09-07").json()["publication"]["id"] == ids[0]
        assert client.get("/api/review/latest", params={"version": ids[1]}).json()["complete"] is False
