from __future__ import annotations

import sys
from types import SimpleNamespace

import pytest

import server


def test_selected_subscription_model_reaches_codex_cli(monkeypatch):
    vr_app = sys.modules["app"]
    captured = {}

    def fake_run(kind, system, user, model=""):
        captured.update(kind=kind, model=model)
        yield "ok"

    monkeypatch.setattr(vr_app.chat_layer.cli_runtime, "run_cli_stream", fake_run)
    events = list(vr_app.chat_layer.run_chat_cli_stream(
        {"provider": "cli-codex", "model": "gpt-test"},
        [{"role": "user", "content": "hello"}],
    ))

    assert captured == {"kind": "codex", "model": "gpt-test"}
    assert events[-1]["type"] == "done"
    assert vr_app.cli_runtime._model_args("codex", "gpt-test") == ["-m", "gpt-test"]
    assert vr_app.cli_runtime._model_args("codex", "codex") == []
    with pytest.raises(RuntimeError, match="模型名称格式无效"):
        vr_app.cli_runtime._model_args("codex", "bad\nmodel")


def test_model_catalogs_are_filtered(monkeypatch):
    catalog = {"models": [
        {"slug": "hidden", "visibility": "hide", "priority": 0},
        {"slug": "gpt-b", "visibility": "list", "priority": 2},
        {"slug": "gpt-a", "visibility": "list", "priority": 1},
        {"slug": "bad model", "visibility": "list", "priority": 0},
        {"slug": "gpt-a", "visibility": "list", "priority": 3},
    ]}
    monkeypatch.setattr(server.subprocess, "run", lambda *args, **kwargs:
                        SimpleNamespace(returncode=0, stdout=server.json.dumps(catalog)))
    assert server._codex_models(["codex"]) == ["gpt-a", "gpt-b"]

    response = SimpleNamespace(
        status_code=200,
        json=lambda: {"data": [{"id": "model-a"}, {"id": "model-a"},
                                {"id": "bad\nmodel"}, "model-b"]},
    )
    monkeypatch.setattr(sys.modules["app"].chat_layer.requests, "get", lambda *args, **kwargs: response)
    assert sys.modules["app"].chat_layer.list_models(
        {"baseURL": "https://api.example.com/v1", "apiKey": "fake"},
    ) == ["model-a", "model-b"]

def test_api_model_catalog_is_not_truncated(monkeypatch):
    expected = [f"model-{i}" for i in range(650)]
    response = SimpleNamespace(status_code=200, json=lambda: {"data": [{"id": m} for m in expected]})
    layer = sys.modules["app"].chat_layer
    monkeypatch.setattr(layer.requests, "get", lambda *args, **kwargs: response)
    assert layer.list_models({"baseURL": "https://api.example.com/v1", "apiKey": "fake"}) == expected
