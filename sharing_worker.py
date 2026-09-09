"""Sharing integration inside one user's private worker container."""
from __future__ import annotations

import json
import logging
import os
from pathlib import Path
import threading
import uuid

import requests
from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse

log = logging.getLogger(__name__)
ENABLED = bool(os.environ.get("VIBE_WORKER_KEY"))
GATEWAY = os.environ.get("VIBE_GATEWAY", "http://gateway:8910")
PROFILE = Path.home() / ".vibe-research" / "llm.json"
OUTBOX = Path.home() / ".duanxian-agents" / "publication-outbox"
_publish_lock = threading.Lock()


def _headers():
    return {"X-Vibe-Worker": os.environ["VIBE_WORKER_KEY"]}


def selected_llm() -> dict | None:
    if not PROFILE.exists():
        return None
    return json.loads(PROFILE.read_text(encoding="utf-8"))


def write_profile(value):
    PROFILE.parent.mkdir(parents=True, exist_ok=True)
    temp = PROFILE.with_name(uuid.uuid4().hex + ".tmp")
    try:
        with temp.open("x", encoding="utf-8") as f:
            os.chmod(temp, 0o600)
            json.dump(value, f, ensure_ascii=False)
        temp.replace(PROFILE)
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
    OUTBOX.mkdir(parents=True, exist_ok=True)
    import hashlib
    encoded = json.dumps(content, ensure_ascii=False, sort_keys=True)
    target = OUTBOX / (hashlib.sha256(encoded.encode()).hexdigest() + ".json")
    if target.exists():
        return
    temp = OUTBOX / (uuid.uuid4().hex + ".tmp")
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
    for path in OUTBOX.glob("*.json"):
        try:
            response = requests.post(GATEWAY + "/internal/reviews", data=path.read_bytes(),
                                     headers={**_headers(), "Content-Type": "application/json"}, timeout=15)
            response.raise_for_status()
            path.unlink(missing_ok=True)
        except (requests.RequestException, OSError):
            log.warning("公共复盘发布暂未成功，已保存在待发布队列，稍后重试")
            break


def shared_review(date: str | None = None, kind: str = "review", version: str | None = None) -> dict:
    try:
        response = requests.get(GATEWAY + "/internal/reviews/latest", params={"date": date, "kind": kind, "version": version},
                                headers=_headers(), timeout=10)
        response.raise_for_status()
        return response.json()
    except (requests.RequestException, ValueError) as exc:
        raise RuntimeError("公共复盘暂时读取失败，请稍后重试") from exc


def start_publication_sync(stop: threading.Event):
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
    threading.Thread(target=run, daemon=True).start()


def install(app):
    if not ENABLED:
        return
    import hmac

    @app.middleware("http")
    async def worker_only(request: Request, call_next):
        if request.url.path != "/api/health" and not hmac.compare_digest(
            request.headers.get("x-vibe-worker", ""), os.environ["VIBE_WORKER_KEY"]
        ):
            return JSONResponse({"detail": "请通过网站登录入口访问"}, status_code=401)
        if request.method == "POST" and request.url.path in {
            "/api/deepdive/run", "/api/review/chat", "/api/deepdive/chat"
        } and not selected_llm():
            return JSONResponse({"detail": "请先在「接入 AI」保存你自己的配置", "error": "请先连接你自己的 AI"}, status_code=400)
        return await call_next(request)

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
