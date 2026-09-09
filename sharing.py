"""Authenticated website gateway. Private APIs go only to the account's worker.

Workers never share a home directory. Only completed market reviews are published
to this gateway; neither browsing nor publication invokes an LLM.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
from pathlib import Path
import re
import secrets
import sqlite3
import time
from urllib.parse import urlparse

import requests
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from starlette.concurrency import run_in_threadpool

DB = Path(os.environ.get("VIBE_ACCOUNTS_DB", "/home/app/sharing/accounts.sqlite3"))
DIST = Path(__file__).parent / "frontend" / "dist"
COOKIE = "vibe_session"
SESSION_SECONDS = 30 * 86400
MAX_BODY = 2 * 1024 * 1024
app = FastAPI(title="Vibe-Astock · shared research")


def digest(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def password_hash(password: str, salt: str) -> str:
    return hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 600_000).hex()


def connect():
    DB.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(DB, timeout=15)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA foreign_keys=ON")
    return db


def initialize():
    with connect() as db:
        db.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            id TEXT PRIMARY KEY, username TEXT UNIQUE NOT NULL,
            salt TEXT NOT NULL, password TEXT, invite TEXT,
            worker TEXT NOT NULL, worker_key TEXT NOT NULL UNIQUE,
            admin INTEGER NOT NULL DEFAULT 0, enabled INTEGER NOT NULL DEFAULT 1,
            watchlist TEXT
        );
        CREATE TABLE IF NOT EXISTS sessions (
            token TEXT PRIMARY KEY, user_id TEXT NOT NULL REFERENCES users(id), expires REAL NOT NULL
        );
        CREATE TABLE IF NOT EXISTS attempts (key TEXT NOT NULL, ts REAL NOT NULL);
        CREATE INDEX IF NOT EXISTS attempts_key ON attempts(key, ts);
        CREATE TABLE IF NOT EXISTS reviews (
            id TEXT PRIMARY KEY, user_id TEXT NOT NULL REFERENCES users(id),
            trade_date TEXT NOT NULL, created REAL NOT NULL, payload TEXT NOT NULL,
            kind TEXT NOT NULL, code TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS review_date ON reviews(trade_date, created);
        CREATE TABLE IF NOT EXISTS invitation_slots (
            user_id TEXT PRIMARY KEY REFERENCES users(id)
        );
        """)


def user_for(request: Request, *, worker: bool = False):
    with connect() as db:
        if worker:
            key = request.headers.get("x-vibe-worker", "")
            row = db.execute("SELECT * FROM users WHERE worker_key=? AND enabled=1", (key,)).fetchone()
        else:
            row = db.execute("""SELECT u.* FROM users u JOIN sessions s ON u.id=s.user_id
                WHERE s.token=? AND s.expires>? AND u.enabled=1""",
                (digest(request.cookies.get(COOKIE, "")), time.time())).fetchone()
    if row is None:
        raise HTTPException(401, "请先登录网站" if not worker else "工作实例未授权")
    if not worker and request.url.path != "/api/account/me" and request.headers.get("x-vibe-account") != row["id"]:
        raise HTTPException(401, "账号已切换，请刷新页面")
    return dict(row)


@app.middleware("http")
async def boundary(request: Request, call_next):
    # SameSite + a non-simple header prevent cross-site form requests, including login CSRF.
    if request.method not in {"GET", "HEAD", "OPTIONS"} and not request.url.path.startswith("/internal/"):
        origin = request.headers.get("origin")
        if request.headers.get("x-vibe-request") != "1" or (
            origin and urlparse(origin).netloc != request.headers.get("host")
        ):
            return JSONResponse({"detail": "请求来源校验失败"}, status_code=403)
    response = await call_next(request)
    if request.url.path.startswith(("/api/", "/internal/")):
        response.headers["Cache-Control"] = "no-store"
        response.headers["Vary"] = "Cookie"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "same-origin"
    return response


async def body_bytes(request: Request) -> bytes:
    parts, size = [], 0
    async for part in request.stream():
        size += len(part)
        if size > MAX_BODY:
            raise HTTPException(413, "请求内容过大")
        parts.append(part)
    return b"".join(parts)


async def json_body(request: Request):
    try:
        value = json.loads(await body_bytes(request))
        if not isinstance(value, dict):
            raise ValueError()
        return value
    except (ValueError, UnicodeError):
        raise HTTPException(400, "需要 JSON 对象")


def throttle(request: Request, username: str):
    # Both account and source are limited; rotating account names cannot evade the source limit.
    keys = ["user:" + username, "ip:" + (request.client.host if request.client else "unknown")]
    with connect() as db:
        db.execute("BEGIN IMMEDIATE")
        db.execute("DELETE FROM attempts WHERE ts<?", (time.time() - 900,))
        for key in keys:
            count = db.execute("SELECT count(*) FROM attempts WHERE key=?", (key,)).fetchone()[0]
            if count >= (10 if key.startswith("user:") else 60):
                raise HTTPException(429, "尝试次数过多，请 15 分钟后重试")
        db.executemany("INSERT INTO attempts VALUES (?, ?)", [(key, time.time()) for key in keys])


def signed_in(user: dict, previous: str = ""):
    token = secrets.token_urlsafe(32)
    with connect() as db:
        db.execute("DELETE FROM sessions WHERE expires<? OR token=?", (time.time(), digest(previous)))
        db.execute("INSERT INTO sessions VALUES (?, ?, ?)", (digest(token), user["id"], time.time() + SESSION_SECONDS))
    response = JSONResponse({"ok": True})
    response.set_cookie(COOKIE, token, max_age=SESSION_SECONDS, httponly=True, samesite="strict",
                        secure=os.environ.get("VIBE_COOKIE_SECURE", "1") != "0")
    return response


@app.get("/api/account/me")
def account(request: Request):
    try:
        u = user_for(request)
    except HTTPException:
        return {"shared": True, "user": None}
    return {"shared": True, "user": {"id": u["id"], "username": u["username"], "admin": bool(u["admin"])},
            "watchlist": json.loads(u["watchlist"]) if u["watchlist"] is not None else None}


@app.post("/api/account/{action}")
async def account_action(action: str, request: Request):
    if action == "logout":
        with connect() as db:
            db.execute("DELETE FROM sessions WHERE token=?", (digest(request.cookies.get(COOKIE, "")),))
        response = JSONResponse({"ok": True})
        response.delete_cookie(COOKIE)
        return response
    if action not in {"login", "activate"}:
        raise HTTPException(404)
    body = await json_body(request)
    username, password = body.get("username"), body.get("password")
    if not isinstance(username, str) or not re.fullmatch(r"[a-z][a-z0-9_-]{2,31}", username) or not isinstance(password, str) or not 1 <= len(password) <= 256:
        raise HTTPException(400, "请输入账号和密码")
    await run_in_threadpool(throttle, request, username)
    with connect() as db:
        row = db.execute("SELECT * FROM users WHERE username=? AND enabled=1", (username,)).fetchone()
    u = dict(row) if row else None
    computed = await run_in_threadpool(password_hash, password, u["salt"] if u else "unknown")
    if action == "activate":
        invite = body.get("invite", "")
        if len(password) < 12:
            raise HTTPException(400, "密码至少 12 个字符")
        if not u or not isinstance(invite, str) or not hmac.compare_digest(u["invite"] or "", digest(invite)):
            raise HTTPException(401, "账号或邀请码错误")
        with connect() as db:
            changed = db.execute("UPDATE users SET password=?, invite=NULL WHERE id=? AND invite=?",
                                 (computed, u["id"], digest(invite))).rowcount
            if not changed:
                raise HTTPException(409, "邀请已使用，请登录")
            db.execute("DELETE FROM sessions WHERE user_id=?", (u["id"],))
    elif not u or not hmac.compare_digest(u["password"] or "", computed):
        raise HTTPException(401, "账号或密码错误")
    return signed_in(u, request.cookies.get(COOKIE, ""))


@app.put("/api/account/watchlist")
async def watchlist(request: Request):
    u = user_for(request)
    codes = (await json_body(request)).get("codes")
    if not isinstance(codes, list) or len(codes) > 1000 or any(
        not isinstance(c, str) or not re.fullmatch(r"[0-9]{6}", c) for c in codes
    ):
        raise HTTPException(400, "自选股必须为六位代码，最多 1000 只")
    with connect() as db:
        db.execute("UPDATE users SET watchlist=? WHERE id=?", (json.dumps(list(dict.fromkeys(codes))), u["id"]))
    return {"ok": True}


@app.post("/internal/reviews")
async def publish(request: Request):
    u = user_for(request, worker=True)
    body = await json_body(request)
    deepdive = body.get("run_type") == "stock_deepdive"
    kind = "deepdive" if deepdive else "review"
    date = body.get("trade_date" if deepdive else "target_date", "")
    try:
        from datetime import date as day
        if not isinstance(date, str) or day.fromisoformat(date).isoformat() != date:
            raise ValueError()
    except ValueError:
        raise HTTPException(400, "复盘日期无效")
    if deepdive and not re.fullmatch(r"[0-9]{6}", str(body.get("code", ""))):
        raise HTTPException(400, "个股代码无效")
    if not body.get("verdict" if deepdive else "focus") and len(str(body.get("verdict_md" if deepdive else "focus_md", "")).strip()) < 200:
        raise HTTPException(400, "未完成的复盘不能发布")
    from sharing_schema import public_payload
    payload = json.dumps(public_payload(body), ensure_ascii=False, sort_keys=True)
    version = digest(u["id"] + payload)
    with connect() as db:
        db.execute("INSERT OR IGNORE INTO reviews VALUES (?, ?, ?, ?, ?, ?, ?)",
                   (version, u["id"], date, time.time(), payload, kind, body.get("code", "") if deepdive else ""))
    return {"id": version}


def admin_for(request: Request):
    u = user_for(request)
    if not u["admin"]:
        raise HTTPException(403, "只有管理员可以邀请成员")
    return u


@app.get("/api/admin/invitations")
def invitation_list(request: Request):
    admin_for(request)
    with connect() as db:
        return {"available": db.execute("SELECT count(*) FROM invitation_slots").fetchone()[0],
                "members": [{"username": r["username"], "admin": bool(r["admin"]),
                             "status": "active" if r["password"] else "invited"} for r in db.execute(
                    "SELECT username, admin, password FROM users WHERE enabled=1 AND id NOT IN (SELECT user_id FROM invitation_slots) ORDER BY admin DESC, username")]}


@app.post("/api/admin/invitations")
async def invite_member(request: Request):
    admin_for(request)
    username = (await json_body(request)).get("username")
    if not isinstance(username, str) or not re.fullmatch(r"[a-z][a-z0-9_-]{2,31}", username):
        raise HTTPException(400, "账号须为 3–32 位小写字母、数字、下划线或短横线，且以字母开头")
    return await run_in_threadpool(issue_invite, username)


def issue_invite(username: str):
    # ponytail: prestarted private workers cover a small friend group; refill slots with the operator CLI.
    # The public gateway never receives Docker control privileges.
    with connect() as db:
        if db.execute("SELECT 1 FROM users WHERE username=?", (username,)).fetchone():
            raise HTTPException(409, "账号已存在，请使用其他名称")
        slots = [dict(r) for r in db.execute("SELECT u.* FROM users u JOIN invitation_slots s ON u.id=s.user_id WHERE u.enabled=1")]
    if not slots:
        raise HTTPException(409, "可邀请名额已用完，请先补充账号名额")
    for slot in slots:
        try:
            response = requests.get(slot["worker"] + "/api/health", headers={"Host": "localhost"}, timeout=2, allow_redirects=False)
            if response.status_code == 200:
                break
        except requests.RequestException:
            pass
    else:
        raise HTTPException(503, "正在准备成员空间，请稍后重试；尚未生成邀请码")
    invite = secrets.token_urlsafe(32)
    try:
        with connect() as db:
            db.execute("BEGIN IMMEDIATE")
            if not db.execute("DELETE FROM invitation_slots WHERE user_id=?", (slot["id"],)).rowcount:
                raise HTTPException(409, "名额刚被使用，请重新生成")
            db.execute("UPDATE users SET username=?, invite=? WHERE id=? AND password IS NULL",
                       (username, digest(invite), slot["id"]))
    except sqlite3.IntegrityError:
        raise HTTPException(409, "账号已存在，请使用其他名称")
    return {"username": username, "invite": invite}


def public_review(date: str | None = None, version: str | None = None, kind: str = "review"):
    with connect() as db:
        row = db.execute("""SELECT r.*, u.username FROM reviews r JOIN users u ON r.user_id=u.id
            WHERE (? IS NULL OR r.trade_date=?) AND (? IS NULL OR r.id=?) AND r.kind=?
            ORDER BY r.trade_date DESC,
                CASE WHEN r.kind='review' AND json_extract(r.payload, '$.complete')=1 THEN 1 ELSE 0 END DESC,
                r.created DESC, r.id DESC LIMIT 1""", (date, date, version, version, kind)).fetchone()
    if not row:
        return {"requested_date": date} if date else {}
    return {**json.loads(row["payload"]), "publication": {"id": row["id"], "author": row["username"],
            "published_at": row["created"], "shared": True}}


@app.get("/internal/reviews/dates")
def worker_review_dates(request: Request):
    user_for(request, worker=True)
    with connect() as db:
        return {"dates": [r[0] for r in db.execute("SELECT DISTINCT trade_date FROM reviews WHERE kind='review' ORDER BY trade_date DESC")]}


@app.get("/internal/reviews/latest")
def worker_review(request: Request, date: str | None = None, kind: str = "review", version: str | None = None):
    user_for(request, worker=True)
    return public_review(date, version, kind=kind)


@app.get("/api/deepdive/latest")
def shared_deepdive(request: Request):
    user_for(request)
    return public_review(kind="deepdive")


@app.get("/api/review/latest")
def latest(request: Request, date: str | None = None, version: str | None = None):
    user_for(request)
    return public_review(date, version)


@app.get("/api/review/dates")
def review_dates(request: Request):
    user_for(request)
    with connect() as db:
        return {"dates": [r[0] for r in db.execute("SELECT DISTINCT trade_date FROM reviews WHERE kind='review' ORDER BY trade_date DESC")]}


@app.get("/api/review/versions")
def versions(request: Request, date: str):
    user_for(request)
    with connect() as db:
        return {"versions": [dict(r) for r in db.execute("""SELECT r.id, u.username AS author, r.created AS published_at
            FROM reviews r JOIN users u ON r.user_id=u.id WHERE r.trade_date=? AND r.kind='review' ORDER BY r.created DESC""", (date,))]}


@app.get("/api/health")
def health():
    return {"ok": True, "service": "vibe-sharing"}


def forward(u: dict, method: str, path: str, query: str, content: bytes, content_type: str):
    # The worker address comes exclusively from operator-provisioned records.
    try:
        upstream = requests.request(method, u["worker"] + "/api/" + path,
            params=query, data=content,
            headers={"X-Vibe-Worker": u["worker_key"], "Authorization": "Bearer " + u["worker_key"],
                     "Content-Type": content_type, "Host": "localhost"}, timeout=(5, 330), stream=True, allow_redirects=False)
    except requests.RequestException:
        raise HTTPException(503, "你的工作实例暂时不可用，请稍后重试")

    def chunks():
        try:
            yield from upstream.iter_content(chunk_size=1024)
        finally:
            upstream.close()
    return StreamingResponse(chunks(), status_code=upstream.status_code,
                             media_type=upstream.headers.get("Content-Type", "application/json"))


@app.api_route("/api/{path:path}", methods=["GET", "POST", "PUT", "DELETE"])
async def private_api(path: str, request: Request):
    u = user_for(request)
    if any(p in {".", ".."} for p in path.split("/")) or "\\" in path:
        raise HTTPException(400, "路径无效")
    return await run_in_threadpool(forward, u, request.method, path, request.url.query,
                                   await body_bytes(request), request.headers.get("content-type", "application/json"))


@app.get("/{path:path}")
def frontend(path: str):
    candidate = (DIST / path).resolve()
    if candidate.is_relative_to(DIST.resolve()) and candidate.is_file():
        return FileResponse(candidate)
    if (DIST / "index.html").is_file():
        return FileResponse(DIST / "index.html")
    raise HTTPException(503, "请先构建前端")


initialize()
