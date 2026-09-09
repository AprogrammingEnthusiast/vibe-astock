"""Operator-only worker provisioning. The website issues invites from prepared slots.

Run this inside the app image with the gateway data volume mounted. The generated
Compose file starts one isolated worker per invited account, using the same image.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import secrets
import uuid

import sharing


def provision(username: str, *, owner: bool = False) -> str:
    if not re.fullmatch(r"[a-z][a-z0-9_-]{2,31}", username):
        raise ValueError("账号须为 3–32 位小写字母、数字、下划线或短横线，且以字母开头")
    invite = secrets.token_urlsafe(32)
    uid = uuid.uuid4().hex
    with sharing.connect() as db:
        if owner and db.execute("SELECT 1 FROM users WHERE admin=1").fetchone():
            raise ValueError("管理员已经存在")
        db.execute("""INSERT INTO users (id, username, salt, invite, worker, worker_key, admin)
            VALUES (?, ?, ?, ?, ?, ?, ?)""", (uid, username, secrets.token_hex(16), sharing.digest(invite),
                 "http://worker-" + uid + ":8910", secrets.token_urlsafe(32), int(owner)))
    return invite


def manifest(port: int, secure: bool) -> dict:
    with sharing.connect() as db:
        users = [dict(r) for r in db.execute("SELECT * FROM users WHERE enabled=1")]
    common = {"image": "vibe-astock-shared:local", "restart": "unless-stopped", "read_only": True,
              "security_opt": ["no-new-privileges:true"], "cap_drop": ["ALL"], "pids_limit": 256,
              "tmpfs": ["/tmp:uid=1000,gid=1000,mode=1777,size=268435456"],
              "healthcheck": {"test": ["CMD", "python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8910/api/health', timeout=5)"],
                              "interval": "30s", "timeout": "10s", "start_period": "60s", "retries": 3}}
    networks = {"account-" + u["id"]: {} for u in users}
    services = {"gateway": {**common, "command": ["python", "-m", "uvicorn", "sharing:app", "--host", "0.0.0.0", "--port", "8910"],
                           "ports": [f"127.0.0.1:{port}:8910"], "volumes": ["accounts:/home/app/sharing"],
                           "environment": {"VIBE_COOKIE_SECURE": "1" if secure else "0"},
                           "networks": list(networks), "mem_limit": "512m"}}
    volumes = {"accounts": {"external": True, "name": "vibe-astock-accounts"}}
    for u in users:
        volume = "home-" + u["id"]
        volumes[volume] = {"name": "vibe-astock-shared-" + u["id"]}
        services["worker-" + u["id"]] = {**common,
            "volumes": [volume + ":/home/app"], "networks": ["account-" + u["id"]],
            "tmpfs": [*common["tmpfs"], "/app/vr/.cache:uid=1000,gid=1000,mode=0700,size=268435456"],
            "mem_limit": "3g", "cpus": 2,
            "environment": {"VIBE_WORKER_KEY": u["worker_key"], "VR_API_KEY": u["worker_key"],
                "VIBE_GATEWAY": "http://gateway:8910", "CODEX_HOME": "/home/app/.codex",
                "VIBE_ALLOW_UNSAFE_CLI": "codex", "VIBE_IMPORT_REVIEWS": "1" if u["admin"] else "0"}}
    return {"name": "vibe-astock-shared", "services": services, "volumes": volumes, "networks": networks}


def add_slots(count: int):
    if not 1 <= count <= 20:
        raise ValueError("每次可补充 1–20 个名额")
    for _ in range(count):
        name = "slot_" + secrets.token_hex(10)
        provision(name)
        with sharing.connect() as db:
            db.execute("UPDATE users SET invite=NULL WHERE username=?", (name,))
            db.execute("INSERT INTO invitation_slots SELECT id FROM users WHERE username=?", (name,))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["add-user", "add-slots", "reset-invite", "disable", "render"])
    parser.add_argument("username", nargs="?")
    parser.add_argument("--owner", action="store_true")
    parser.add_argument("--port", type=int, default=8910)
    parser.add_argument("--local-http", action="store_true", help="仅本机 HTTP 测试；公网 HTTPS 不要设置")
    parser.add_argument("--output", default="/app/.sharing")
    args = parser.parse_args()
    if not 1 <= args.port <= 65535:
        parser.error("端口无效")
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)
    invite = None
    if args.action == "add-user":
        invite = provision(args.username or "", owner=args.owner)
    elif args.action == "add-slots":
        add_slots(int(args.username or "5"))
    elif args.action in {"reset-invite", "disable"}:
        with sharing.connect() as db:
            row = db.execute("SELECT id FROM users WHERE username=?", (args.username,)).fetchone()
            if not row:
                parser.error("账号不存在")
            db.execute("DELETE FROM sessions WHERE user_id=?", (row["id"],))
            if args.action == "disable":
                db.execute("UPDATE users SET enabled=0 WHERE id=?", (row["id"],))
            else:
                invite = secrets.token_urlsafe(32)
                db.execute("UPDATE users SET invite=?, password=NULL WHERE id=?", (sharing.digest(invite), row["id"]))
    target = output / "compose.json"
    target.write_text(json.dumps(manifest(args.port, not args.local_http), indent=2), encoding="utf-8")
    os.chmod(target, 0o600)
    if invite:
        note = output / (args.username + "-invite.txt")
        note.write_text(f"网站账号：{args.username}\n一次性邀请码：{invite}\n在网站选择「首次使用」并设置自己的密码。请勿分享管理员邀请。\n", encoding="utf-8")
        os.chmod(note, 0o600)
        print(f"已保存邀请：{note}")
    print(f"部署配置：{target}。用 docker compose -f .sharing/compose.json up -d --remove-orphans 应用。")


if __name__ == "__main__":
    main()
