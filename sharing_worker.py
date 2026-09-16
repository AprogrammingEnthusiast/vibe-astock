"""Sharing integration inside one user's private worker container."""
from __future__ import annotations
import account_context

import json
import logging
import os
from pathlib import Path
import threading
import sqlite3
import uuid

import requests
from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse

log = logging.getLogger(__name__)
ENABLED = account_context.ENABLED or bool(os.environ.get("VIBE_WORKER_KEY"))
GATEWAY = os.environ.get("VIBE_GATEWAY", "http://gateway:8910")
PROFILE = Path.home() / ".vibe-research" / "llm.json"
OUTBOX = Path.home() / ".duanxian-agents" / "publication-outbox"
_publish_lock = threading.Lock()


def _headers():
    if account_context.ENABLED:
        return {"X-Vibe-Worker": account_context.current()["worker_key"]}
    return {"X-Vibe-Worker": os.environ["VIBE_WORKER_KEY"]}


def selected_llm() -> dict | None:
    if not account_context.path(PROFILE).exists():
        return None
    return json.loads(account_context.path(PROFILE).read_text(encoding="utf-8"))


def write_profile(value, path=None):
    profile = account_context.path(path) if path is not None else account_context.path(PROFILE)
    profile.parent.mkdir(parents=True, exist_ok=True)
    temp = profile.with_name(uuid.uuid4().hex + ".tmp")
    try:
        with temp.open("x", encoding="utf-8") as f:
            os.chmod(temp, 0o600)
            json.dump(value, f, ensure_ascii=False)
        temp.replace(profile)
    finally:
        temp.unlink(missing_ok=True)


def make_llm(temperature: float):
    cfg = selected_llm()
    if not cfg:
        raise RuntimeError("请先在「接入 AI」保存你自己的配置；浏览公共复盘不需要 AI")
    if cfg["provider"] == "cli-codex":
        from duanxian.cli_llm import CliLlm
        return CliLlm("codex", model=cfg.get("model", ""))
    if cfg["provider"].startswith("cli-"):
        raise RuntimeError("共享站点目前只支持 Codex 订阅或个人 API Key")
    from chat import _check_base_url
    from langchain_openai import ChatOpenAI
    _check_base_url(cfg["baseURL"])
    return ChatOpenAI(model=cfg["model"], base_url=cfg["baseURL"], api_key=cfg["apiKey"],
                      temperature=temperature, timeout=180, max_retries=2)


def queue_publication(payload: dict):
    if not ENABLED:
        return
    # The review graph has public market inputs only. Never call this for chat or journal output.
    from sharing_schema import public_payload
    content = public_payload(payload)
    account_context.path(OUTBOX).mkdir(parents=True, exist_ok=True)
    import hashlib
    encoded = json.dumps(content, ensure_ascii=False, sort_keys=True)
    target = account_context.path(OUTBOX) / (hashlib.sha256(encoded.encode()).hexdigest() + ".json")
    if target.exists():
        return
    temp = account_context.path(OUTBOX) / (uuid.uuid4().hex + ".tmp")
    temp.write_text(encoded, encoding="utf-8")
    temp.replace(target)
    flush_publications()


def flush_publications():
    if not _publish_lock.acquire(blocking=False):
        return
    try:
        _flush_publications()
    finally:
        _publish_lock.release()


def _flush_publications():
    for path in account_context.path(OUTBOX).glob("*.json"):
        try:
            if account_context.ENABLED:
                from sharing import publish_for
                publish_for(account_context.current(), json.loads(path.read_bytes()))
            else:
                response = requests.post(GATEWAY + "/internal/reviews", data=path.read_bytes(),
                                         headers={**_headers(), "Content-Type": "application/json"}, timeout=15)
                response.raise_for_status()
            path.unlink(missing_ok=True)
        except (requests.RequestException, OSError, ValueError, HTTPException, sqlite3.Error):
            log.warning("公共复盘发布暂未成功，已保存在待发布队列，稍后重试")
            break


def shared_review(date: str | None = None, kind: str = "review", version: str | None = None) -> dict:
    if account_context.ENABLED:
        from sharing import public_review
        return public_review(date, version, kind)
    try:
        response = requests.get(GATEWAY + "/internal/reviews/latest", params={"date": date, "kind": kind, "version": version},
                                headers=_headers(), timeout=10)
        response.raise_for_status()
        return response.json()
    except (requests.RequestException, ValueError) as exc:
        raise RuntimeError("公共复盘暂时读取失败，请稍后重试") from exc


def start_publication_sync(stop: threading.Event):
    if account_context.ENABLED:
        def shared_run():
            from sharing import connect, DB
            while not stop.is_set():
                with connect() as db:
                    users = [dict(r) for r in db.execute("SELECT * FROM users WHERE enabled=1 AND id NOT IN (SELECT user_id FROM invitation_slots)")]
                for user in users:
                    with account_context.bind(user, DB.parent / "homes"):
                        flush_publications()
                stop.wait(15)
        account_context.thread(target=shared_run, daemon=True).start()
        return
    def run():
        if os.environ.get("VIBE_IMPORT_REVIEWS") == "1":
            from duanxian import review_store
            for path in Path(review_store.DIR).glob("????-??-??.json"):
                try:
                    payload = json.loads(path.read_text(encoding="utf-8"))
                    if review_store.usable(payload):
                        queue_publication(payload)
                except (ValueError, OSError):
                    log.warning("旧复盘未能导入：%s", path.name)
        while not stop.is_set():
            flush_publications()
            stop.wait(15)
    account_context.thread(target=run, daemon=True).start()


def install(app):
    if not ENABLED:
        return
    import hmac

    @app.middleware("http")
    async def worker_only(request: Request, call_next):
        authorized = account_context.current() is not None if account_context.ENABLED else hmac.compare_digest(
            request.headers.get("x-vibe-worker", ""), os.environ["VIBE_WORKER_KEY"])
        if request.url.path != "/api/health" and not authorized:
            return JSONResponse({"detail": "请通过网站登录入口访问"}, status_code=401)
        if request.method == "POST" and request.url.path in {
            "/api/deepdive/run", "/api/review/chat", "/api/deepdive/chat"
        } and not selected_llm():
            return JSONResponse({"detail": "请先在「接入 AI」保存你自己的配置", "error": "请先连接你自己的 AI"}, status_code=400)
        return await call_next(request)

    connection_file = PROFILE.with_name("agent-connection.json")

    @app.get("/api/personal/agent-connection")
    def get_agent_profile():
        return {"llm": json.loads(account_context.path(connection_file).read_text(encoding="utf-8")) if account_context.path(connection_file).exists() else None}

    @app.put("/api/personal/agent-connection")
    async def save_agent_profile(request: Request):
        from review_agent.api import ModelInput
        from review_agent.runtime import connection
        from review_agent.evidence import EvidenceError
        try:
            value = (await request.json())["llm"]
            verified_at = value.get("verifiedAt") if isinstance(value, dict) else None
            if value is not None:
                if not isinstance(value, dict) or value.get("provider") not in {"codex-private", "openai", "mimo", "api-compatible"}:
                    raise ValueError()
                # Verification timestamps are display metadata, not model input.
                cfg = ModelInput(**{k: v for k, v in value.items() if k != "verifiedAt"})
                value = cfg.model_dump(exclude={"apiKey"})
                value["apiKey"] = cfg.apiKey.get_secret_value()
                connection(value)
                if value["provider"] in {"claude", "codebuddy"}:
                    raise ValueError()
            if value is not None and isinstance(verified_at, (int, float)) and not isinstance(verified_at, bool):
                import time
                if 0 < verified_at <= time.time() * 1000:
                    value["verifiedAt"] = verified_at
            write_profile(value, account_context.path(connection_file))
        except (ValueError, TypeError, KeyError, EvidenceError):
            raise HTTPException(400, "个人 AI 配置无效，请检查来源、地址及模型") from None
        return {"ok": True}

    @app.get("/api/personal/llm")
    def get_profile():
        return {"llm": selected_llm()}

    @app.put("/api/personal/llm")
    async def save_profile(request: Request):
        try:
            body = await request.json()
            cfg = body["llm"]
            if cfg is not None:
                from app import LLMConfig
                cfg = LLMConfig(**cfg).model_dump()
                if not cfg["model"] or len(cfg["model"]) > 256:
                    raise ValueError("请填写模型")
                if cfg["provider"].startswith("cli-"):
                    if cfg["provider"] != "cli-codex":
                        raise ValueError("共享站点目前仅支持 Codex 订阅")
                else:
                    from chat import _check_base_url
                    if not cfg["apiKey"] or not cfg["baseURL"]:
                        raise ValueError("请填写 API Key 和接口地址")
                    _check_base_url(cfg["baseURL"])
            write_profile(cfg)
        except (ValueError, TypeError, KeyError, RuntimeError) as exc:
            raise HTTPException(400, str(exc))
        return {"ok": True}


def prepare_agent(runtime):
    """Migrate only this worker's own login; original data remains as a backup."""
    import shutil
    old = account_context.home() / ".codex" / "auth.json"
    target = runtime.home / "auth.json"
    if not target.exists() and old.is_file() and not old.is_symlink():
        with target.open("xb") as output, old.open("rb") as source:
            os.chmod(target, 0o600)
            shutil.copyfileobj(source, output)


def shared_bundle(anchor, version=""):
    import re
    if version and not re.fullmatch(r"[0-9a-f]{64}", version):
        from review_agent.evidence import EvidenceError
        raise EvidenceError("共享复盘版本无效")
    import tempfile
    from review_agent.evidence import build_bundle, valid_date, EvidenceError
    valid_date(anchor)
    try:
        if account_context.ENABLED:
            from sharing import connect
            with connect() as db:
                available = [r[0] for r in db.execute("SELECT DISTINCT trade_date FROM reviews WHERE kind='review'")]
        else:
            response = requests.get(GATEWAY + "/internal/reviews/dates", headers=_headers(), timeout=10)
            response.raise_for_status()
            available = response.json()["dates"]
        dates = sorted((d for d in available if isinstance(d, str) and d <= anchor), reverse=True)[:20]
        with tempfile.TemporaryDirectory(prefix="public-evidence-") as tmp:
            for day in dates:
                valid_date(day)
                payload = shared_review(day, version=version) if day == anchor and version else shared_review(day)
                (Path(tmp) / (day + ".json")).write_text(json.dumps(payload), encoding="utf-8")
            return build_bundle(Path(tmp), anchor, shared=False)
    except (requests.RequestException, RuntimeError, ValueError, KeyError) as exc:
        raise EvidenceError("公共复盘证据暂时不可用，请稍后重试") from exc
