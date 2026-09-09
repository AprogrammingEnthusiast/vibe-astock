"""Operator commands for the shared application and explicit legacy home import."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import secrets
import shutil
import stat
import tempfile
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
                 "", secrets.token_urlsafe(32), int(owner)))
    return invite


def manifest(port: int, secure: bool) -> dict:
    common = {"image": "vibe-astock-shared:local", "restart": "unless-stopped", "read_only": True,
              "security_opt": ["no-new-privileges:true"], "cap_drop": ["ALL"], "pids_limit": 256,
              "tmpfs": ["/tmp:uid=1000,gid=1000,mode=1777,size=268435456"],
              "healthcheck": {"test": ["CMD", "python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8910/api/health', timeout=5)"],
                              "interval": "30s", "timeout": "10s", "start_period": "60s", "retries": 3}}
    service = {**common, "command": ["python", "-m", "uvicorn", "sharing:app", "--host", "0.0.0.0", "--port", "8910"],
               "ports": [f"127.0.0.1:{port}:8910"], "volumes": ["accounts:/home/app/sharing"],
               "tmpfs": [*common["tmpfs"], "/app/vr/.cache:uid=1000,gid=1000,mode=0700,size=268435456"],
               "environment": {"VIBE_COOKIE_SECURE": "1" if secure else "0", "VIBE_SHARED_APP": "1",
                               "VIBE_ALLOW_UNSAFE_CLI": "codex", "HOME": "/home/app/sharing/service"}, "mem_limit": "3g", "cpus": 2}
    return {"name": "vibe-astock-shared", "services": {"gateway": service},
            "volumes": {"accounts": {"external": True, "name": "vibe-astock-accounts"}}}


def _plain_path(path: Path):
    for entry in (path, *path.parents):
        if entry.is_symlink() or (hasattr(entry, "is_junction") and entry.is_junction()):
            raise ValueError("迁移路径不能包含符号链接或目录联接")


def _plain_tree(path: Path):
    _plain_path(path)
    if not path.is_dir():
        raise ValueError("旧 home 必须是已存在的目录")
    for parent, directories, files in os.walk(path, followlinks=False):
        for name in directories + files:
            entry = Path(parent) / name
            _plain_path(entry)
            mode = entry.lstat().st_mode
            if not (stat.S_ISDIR(mode) or stat.S_ISREG(mode)):
                raise ValueError("旧 home 只能包含普通文件和目录")


def import_home(username: str, source: Path) -> Path:
    """Copy an offline, read-only legacy home; never merge or alter its source."""
    with sharing.connect() as db:
        row = db.execute("SELECT id FROM users WHERE username=?", (username,)).fetchone()
    if not row or not re.fullmatch(r"[0-9a-f]{32}", row["id"]):
        raise ValueError("账号不存在或账号编号无效")
    source = Path(source).absolute()
    _plain_tree(source)
    root = sharing.DB.absolute().parent / "homes"
    _plain_path(root)
    target = root / row["id"]
    if target.exists() or target.is_symlink():
        raise ValueError("本人账号空间已存在，拒绝覆盖或合并")
    if root.is_relative_to(source) or source.is_relative_to(target):
        raise ValueError("源目录与目标账号空间不能嵌套")
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    with tempfile.TemporaryDirectory(prefix=".import-", dir=root) as temporary:
        staged = Path(temporary) / "home"
        shutil.copytree(source, staged, symlinks=True)
        _plain_tree(staged)
        staged.chmod(0o700)
        if target.exists() or target.is_symlink():
            raise ValueError("本人账号空间已存在，拒绝覆盖或合并")
        staged.rename(target)
    return target


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["add-user", "reset-invite", "disable", "render", "import-home"])
    parser.add_argument("username", nargs="?")
    parser.add_argument("--source", type=Path, help="import-home 的只读旧 home 目录")
    parser.add_argument("--owner", action="store_true")
    parser.add_argument("--port", type=int, default=8910)
    parser.add_argument("--local-http", action="store_true", help="仅本机 HTTP 测试；公网 HTTPS 不要设置")
    parser.add_argument("--output", default="/app/.sharing")
    args = parser.parse_args()
    if not 1 <= args.port <= 65535:
        parser.error("端口无效")
    if args.action == "import-home":
        if not args.username or not args.source:
            parser.error("import-home 需要账号和 --source；先停止新旧应用的写入")
        try:
            import_home(args.username, args.source)
        except (ValueError, OSError):
            parser.error("导入失败：检查账号、目录权限、链接及目标是否已存在；原件保持不变")
        print("本人账号数据已复制；旧数据保持不变。")
        return
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)
    invite = None
    if args.action == "add-user":
        invite = provision(args.username or "", owner=args.owner)
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
