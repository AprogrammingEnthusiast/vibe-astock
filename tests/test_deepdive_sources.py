"""Deep-dive evidence survives missing optional tools and model paraphrasing."""
import datetime
from types import SimpleNamespace

import pytest

from duanxian.deepdive import agents, data
from duanxian.util import is_degraded_report
from vr import astock


@pytest.fixture
def sources(monkeypatch):
    monkeypatch.setattr(data, "china_now", lambda: datetime.datetime(2026, 9, 10, 17))
    monkeypatch.setattr(astock, "concept_blocks", lambda code: {"concept_tags": ["电池", "储能"]})
    news = [{"新闻标题": "项目进展", "新闻内容": "公司披露项目进展", "发布时间": "2026-09-09 12:00:00",
             "文章来源": "测试来源", "新闻链接": "https://example.com/news"}]
    monkeypatch.setattr(astock, "stock_news", lambda code, limit: news)
    return news


def test_theme_uses_existing_public_sources_with_dates(sources):
    text = data.get_theme("300750", "宁德时代")
    assert "电池" in text and "储能" in text and "项目进展" in text
    assert "2026-09-09 12:00:00" in text and "测试来源" in text
    assert "https://example.com/news" in text and "东方财富" in text
    assert "mcporter" not in text and not is_degraded_report(text)


@pytest.mark.parametrize("missing", ["concept_blocks", "stock_news"])
def test_partial_failure_remains_visible_after_model_paraphrase(sources, monkeypatch, missing):
    def fail(*args, **kwargs):
        raise TimeoutError("private transport details must not leak")
    monkeypatch.setattr(astock, missing, fail)
    material = data.get_theme("300750", "宁德时代")
    assert not is_degraded_report(material)
    node = agents.create_theme_analyst(SimpleNamespace(invoke=lambda p: SimpleNamespace(content="模型省略了缺口。")),
                                      SimpleNamespace(get_theme=lambda *a: material))
    report = node({"code": "300750", "name": "宁德时代"})["theme_report"]
    assert "[⚠️" in report and "TimeoutError" in report
    assert "private transport" not in report


def test_total_failure_skips_model_and_keeps_degraded_envelope(sources, monkeypatch):
    monkeypatch.setattr(astock, "concept_blocks", lambda code: {"concept_tags": []})
    monkeypatch.setattr(astock, "stock_news", lambda *a, **kw: [])
    material = data.get_theme("300750", "宁德时代")
    assert is_degraded_report(material)
    def forbidden(prompt):
        pytest.fail("Do not ask the model to paraphrase a complete evidence failure")
    node = agents.create_theme_analyst(SimpleNamespace(invoke=forbidden), SimpleNamespace(get_theme=lambda *a: material))
    assert is_degraded_report(node({"code": "300750", "name": "宁德时代"})["theme_report"])


def test_news_filters_future_old_undated_and_sorts_before_limit(sources):
    template = sources[0]
    sources[:] = [dict(template, 新闻标题=label, 发布时间=date) for label, date in [
        ("过期", "2026-07-01 12:00:00"), ("未来", "2026-09-11 12:00:00"),
        ("无日期", ""), ("无效日期", "bad"),
        ("旧样本", "2026-09-01 12:00:00"), ("最新样本", "2026-09-10 12:00:00")]]
    text = data.get_theme("300750", "宁德时代")
    assert "最新样本" in text and "旧样本" in text
    assert text.index("最新样本") < text.index("旧样本")
    assert all(label not in text for label in ("过期", "未来", "无日期", "无效日期"))
