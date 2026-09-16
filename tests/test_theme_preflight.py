import json

import pytest

from duanxian import data, fetchers, preflight, theme_tree, trade_calendar


@pytest.mark.parametrize("source", ["cache", "network", "failure", "empty"])
def test_theme_preflight_reuses_data_or_explains_failure(monkeypatch, tmp_path, source):
    date = "2026-09-07"
    reasons = {"600000": "机器人+业绩增长"}
    monkeypatch.setattr(theme_tree, "_CACHE_DIR", str(tmp_path))
    monkeypatch.setattr(trade_calendar, "is_settled", lambda d: True)
    for label, name, _ in preflight._CHECKS:
        if label != "题材串":
            monkeypatch.setattr(data, name, lambda d: "正常数据")
    if source == "cache":
        (tmp_path / f"{date}.json").write_text(json.dumps({
            "schema": theme_tree._SCHEMA, "date": date, "reasons": reasons,
        }), encoding="utf-8")
    calls = []

    def fetch(ymd):
        calls.append(ymd)
        if source == "cache":
            raise AssertionError("已有同日缓存，不应再次请求")
        if source == "failure":
            return {}, "未配置 IWENCAI_API_KEY"
        if source == "empty":
            return {}, None
        return reasons, None

    monkeypatch.setattr(fetchers, "fetch_zt_reasons", fetch)
    result = preflight.check(date)
    assert result["ok"]
    if source in ("cache", "network"):
        assert result["warnings"] == []
        assert "机器人×1" in data.get_theme_reasons(date)
        assert calls == ([] if source == "cache" else ["20260907"])
    else:
        assert result["missing_optional"] == ["题材串"]
        assert ("IWENCAI_API_KEY" if source == "failure" else "未返回题材串") in result["warnings"][0]
