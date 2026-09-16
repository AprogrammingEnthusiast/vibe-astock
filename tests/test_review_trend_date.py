"""复盘当天的原料首次落盘、日线日历滞后，都不能把趋势停在昨天。"""
import pytest

from duanxian import breadth, data, emotion_metrics, market_facts, stats_context as sc, theme_tree


@pytest.mark.unit
@pytest.mark.parametrize("calendar_lag", [False, True])
def test_market_facts_includes_target_on_first_run(monkeypatch, calendar_lag):
    today, yesterday = "2026-09-08", "2026-09-07"
    cached = {yesterday}
    summary = {"limit_up": 50, "highest_consec": 5, "broken_rate": 0.2}
    monkeypatch.setattr(sc, "_SERIES_CACHE", {})
    monkeypatch.setattr(sc.trade_calendar, "is_settled", lambda d: True)
    monkeypatch.setattr(sc.trade_calendar, "trade_dates_ending_at",
                        lambda end, n: [yesterday] if calendar_lag else [yesterday, today])
    monkeypatch.setattr(sc, "_cached_days_per_dir", lambda: (frozenset(cached),) * 2)
    monkeypatch.setattr(sc, "_file_fingerprint", lambda *args: (1, 1))

    def day_summary(date):
        cached.add(date)
        return summary

    monkeypatch.setattr(emotion_metrics, "day_summary", day_summary)
    monkeypatch.setattr(data, "fetch_prev_pool", lambda date: [])
    monkeypatch.setattr(breadth, "market_breadth", lambda date: {})
    monkeypatch.setattr(theme_tree, "build", lambda date: {})
    for name in ("seal_quality", "loss_effect", "feedback_matrix", "theme_structure",
                 "event_ledger", "by_board"):
        monkeypatch.setattr(market_facts, name, lambda date: {})
    monkeypatch.setattr(data, "render_market_facts", lambda facts: "")

    _, facts = data.get_market_facts(today)
    assert facts["trend"]["days"][-1] == today
    assert facts["trend"]["metrics"][0]["values"][-1] == 50
    assert facts["stats_context"]["date"] == today
    assert facts["day_diff"]["date"] == today


@pytest.mark.unit
def test_missing_target_is_unavailable_not_yesterdays_trend(monkeypatch):
    monkeypatch.setattr(sc, "series", lambda *args, **kwargs: [{"date": "2026-09-07"}])
    result = sc.trend(end="2026-09-08")
    assert result["available"] is False
    assert "2026-09-08" in result["reason"]
