"""Fresh-process integration check of the actual shared application entrypoint."""
import os
from pathlib import Path
import socket
import sys
import threading
import base64
from concurrent.futures import ThreadPoolExecutor

root = Path(sys.argv[1])
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.update(VIBE_SHARED_APP="1", VIBE_ACCOUNTS_DB=str(root / "accounts.sqlite3"),
                  VIBE_COOKIE_SECURE="0", HOME=str(root / "service"), VIBE_ALLOW_UNSAFE_CLI="codex")
for key in ("ASTOCK_AGENT_HOME", "CODEX_HOME", "VR_DATA_DIR", "VR_REPORTS_DIR", "VIBE_WORKER_KEY"):
    os.environ.pop(key, None)


def no_network(*args, **kwargs):
    raise AssertionError("Integration checks must not contact external services")


socket.socket.connect = no_network
from fastapi.testclient import TestClient
import sharing
import sharing_admin
import account_context
import server
import sharing_worker
import watchtower

server._start_intraday = lambda: None
watchtower.ensure_started = lambda: None


def signed_in(name):
    invite = sharing_admin.provision(name, owner=name == "alice")
    client = TestClient(sharing.app, headers={"X-Vibe-Request": "1"})
    assert client.post("/api/account/activate", json={"username": name, "password": "test-account-password", "invite": invite}).status_code == 200
    client.headers["X-Vibe-Account"] = client.get("/api/account/me").json()["user"]["id"]
    return client


with TestClient(sharing.app):
    alice, bob = signed_in("alice"), signed_in("bobby")
    for client, mark in ((alice, "ALICE"), (bob, "BOB")):
        saved = client.post("/api/journal/add", json={"date": "2026-09-08", "code": "600519", "name": mark, "note": mark})
        assert saved.status_code == 200, saved.text
        profile = {"provider": "api-compatible", "model": "test-model", "baseURL": "https://8.8.8.8/v1", "apiKey": mark}
        response = client.put("/api/personal/agent-connection", json={"llm": profile})
        assert response.status_code == 200, response.text
        assert client.get("/api/review-agent/conversations").status_code == 200
    assert "ALICE" in alice.get("/api/journal/list").text and "BOB" not in alice.get("/api/journal/list").text
    assert "BOB" in bob.get("/api/journal/list").text and "ALICE" not in bob.get("/api/journal/list").text
    assert alice.get("/api/personal/agent-connection").json()["llm"]["apiKey"] == "ALICE"
    assert bob.get("/api/personal/agent-connection").json()["llm"]["apiKey"] == "BOB"
    upload = alice.post("/api/myreports", json={"name": "private.txt", "content_b64": base64.b64encode(b"ALICE research").decode()})
    assert upload.status_code == 200, upload.text
    report_id = upload.json()["data"]["id"]
    assert alice.get("/api/myreports/file/" + report_id).content == b"ALICE research"
    assert bob.get("/api/myreports/file/" + report_id).status_code == 404
    assert bob.delete("/api/myreports/" + report_id).json()["data"]["ok"] is False
    assert alice.get("/api/myreports/file/" + report_id).status_code == 200
    assert bob.get("/api/journal/list", headers={"X-Vibe-Account": alice.headers["X-Vibe-Account"]}).status_code == 401
    assert TestClient(server.app).get("/api/journal/list").status_code == 401
    assert alice.post("/api/review/run", json={}).status_code == 409
    bad = {"provider": "api-compatible", "model": "test-model", "baseURL": "https://127.0.0.1/v1", "apiKey": "fake"}
    assert alice.put("/api/personal/agent-connection", json={"llm": bad}).status_code == 400

    with sharing.connect() as db:
        users = [dict(row) for row in db.execute("SELECT * FROM users ORDER BY username")]
    gate = threading.Event()
    threads = []
    homes = []
    turns = []
    managers = []
    for user, marker in zip(users, ("ALICE", "BOB")):
        with account_context.bind(user, root / "homes"):
            homes.append(account_context.home())
            server._state()._job["job_id"] = marker
            watchtower.set_client_watch("a" * 32, ["600519"] if marker == "ALICE" else ["000001"])
            assert watchtower._state()._extra_watch == (["600519"] if marker == "ALICE" else ["000001"])
            manager = server._get_review_agent()
            assert manager.store.root.is_relative_to(account_context.home())
            turn, fresh = manager.store.start("2026-09-08", marker, "c" * 32, {"provider": "codex-private", "model": "fake"},
                                               lambda: {"revision": "r", "dates": ["2026-09-08"]})
            assert fresh
            turns.append(turn)
            (manager.runtime.home / "auth.json").write_text(marker)
            legacy = account_context.home() / ".codex" / "auth.json"
            legacy.parent.mkdir(parents=True, exist_ok=True)
            legacy.write_text(marker)
            def write_after_request(mark=marker):
                assert gate.wait(5)
                sharing_worker.write_profile({"marker": mark})
            worker = account_context.thread(target=write_after_request)
            manager.active = (turn["id"], threading.Event(), worker)
            managers.append(manager)
            worker.start()
            threads.append(worker)
    gate.set()
    for worker in threads:
        worker.join(5)
        assert not worker.is_alive()
    with ThreadPoolExecutor(max_workers=2) as pool:
        jobs = list(pool.map(lambda client: client.get("/api/review/status").json()["job_id"], (alice, bob)))
    assert jobs == ["ALICE", "BOB"], jobs
    assert bob.get("/api/review-agent/conversations/" + turns[0]["conversation_id"]).status_code == 400
    assert bob.post("/api/review-agent/turns/" + turns[0]["id"] + "/cancel", json={}).status_code == 400
    cancelled = alice.post("/api/review-agent/turns/" + turns[0]["id"] + "/cancel", json={})
    assert cancelled.status_code == 200, cancelled.text
    assert managers[0].active[1].is_set() and not managers[1].active[1].is_set()
    assert bob.get("/api/review-agent/turns/" + turns[1]["id"]).json()["status"] == "running"
    assert bob.post("/api/review-agent/turns/" + turns[1]["id"] + "/cancel", json={}).status_code == 200
    for manager in managers:
        manager.active = None
    for home, marker in zip(homes, ("ALICE", "BOB")):
        assert marker in (home / ".vibe-research/llm.json").read_text()
    from duanxian import review_store
    with account_context.bind(users[0], root / "homes"):
        review_store.save({"target_date": "2026-09-08", "focus_md": "公开市场资料" * 100, "complete": True}, "2026-09-08")
    published = bob.get("/api/review/latest").json()
    assert published["publication"]["author"] == "alice", published
    assert not (homes[1] / ".duanxian-agents/reviews/2026-09-08.json").exists()
    assert alice.post("/api/review-agent/access/logout", json={}).status_code == 200
    assert not (homes[0] / ".codex/auth.json").exists()
    assert (homes[1] / ".codex/auth.json").read_text() == "BOB"
    assert (homes[1] / ".vibe-astock-agent/codex-home/auth.json").read_text() == "BOB"
    assert bob.get("/api/personal/agent-connection").json()["llm"]["apiKey"] == "BOB"
    assert alice.get("/api/personal/agent-connection").json()["llm"] is None
    with account_context.bind(users[0], root / "homes"):
        try:
            from duanxian.config import make_llm
            make_llm()
            raise AssertionError("Missing personal credentials must fail")
        except RuntimeError:
            pass
    alice.close()
    bob.close()
print("Single-process account boundaries passed")
