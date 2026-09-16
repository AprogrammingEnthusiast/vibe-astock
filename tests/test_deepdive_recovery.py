import datetime
from types import SimpleNamespace

import pytest

from duanxian.deepdive import evidence as e
from vr import astock


def test_history_success_then_failure_uses_dated_account_cache(tmp_path, monkeypatch):
    monkeypatch.setattr(e.Path, 'home', lambda: tmp_path)
    monkeypatch.setattr(e, 'china_now', lambda: datetime.datetime(2026, 9, 10, 18))
    monkeypatch.setattr(e, 'is_a_share_closed', lambda: True)
    rows = [{'date': '2026-09-09', 'main_net': 0}, {'date': '2026-09-10', 'main_net': -12},
            {'date': '2026-09-11', 'main_net': 999}]
    monkeypatch.setattr(astock, 'stock_fund_flow_120d', lambda *a, **kw: rows)
    value = e._historical_capital('300750')
    assert '-12' in value and '999' not in value and '"main_net": 0' in value
    assert '最近5条记录主力净额合计": null' in value
    def failed(*a, **kw): raise ConnectionError('disconnected')
    monkeypatch.setattr(astock, 'stock_fund_flow_120d', failed)
    value = e._historical_capital('300750')
    assert 'ConnectionError' in value and '使用缓存，截至2026-09-10' in value
    assert '无有效缓存' in e._historical_capital('000001')
    monkeypatch.setattr(e, 'china_now', lambda: datetime.datetime(2026, 10, 10, 18))
    assert '无有效缓存' in e._historical_capital('300750')


def test_history_strict_failure_and_unknown_not_zero(monkeypatch):
    def fail(*a, **kw): raise ConnectionError()
    monkeypatch.setattr(astock, 'em_get', fail)
    assert astock.stock_fund_flow_120d('300750') == []
    with pytest.raises(ConnectionError): astock.stock_fund_flow_120d('300750', strict=True)
    monkeypatch.setattr(astock, 'em_get', lambda *a, **kw: SimpleNamespace(json=lambda:
        {'data': {'klines': ['2026-09-10,-,0,-2,nan,3']}}))
    row = astock.stock_fund_flow_120d('300750', strict=True)[0]
    assert row['main_net'] is None and row['small_net'] == 0 and row['large_net'] is None


def test_announcement_pages_and_identity(monkeypatch):
    import requests
    pages = []
    def fetch(*a, **kw):
        page = kw['params']['page_index']; pages.append(page)
        return SimpleNamespace(raise_for_status=lambda: None, json=lambda: {'data': {
            'art_code': 'AN123', 'security': [{'stock':'300750'}], 'page_size':2,
            'notice_content':f'正文{page}', 'notice_title':'归属公告'}})
    monkeypatch.setattr(requests, 'get', fetch)
    value = astock.announcement_content('300750', 'https://data.eastmoney.com/notices/detail/300750/AN123.html')
    assert pages == [1, 2] and value['完整读取'] and value['正文'] == '正文1\n正文2'
    with pytest.raises(ValueError): astock.announcement_content('000001', 'https://data.eastmoney.com/notices/detail/300750/AN123.html')


def test_first_debate_prompt_does_not_claim_opponent_missing():
    from duanxian.deepdive.agents import create_join_debator
    from duanxian.deepdive.state import new_stock_debate_state
    prompts = []
    llm = SimpleNamespace(invoke=lambda p: prompts.append(p) or SimpleNamespace(content='证据有限'))
    create_join_debator(llm)({'code':'300750','name':'测试','debate_state':new_stock_debate_state()})
    assert '本轮由你首先陈述证据' in prompts[0]
    assert '未来持续性不能确认，不等于已有历史行情缺失' in prompts[0]


def test_risk_body_failure_keeps_other_evidence(monkeypatch):
    monkeypatch.setattr(e, 'china_now', lambda: datetime.datetime(2026,9,10,18))
    monkeypatch.setattr(astock, 'lockup_expiry', lambda *a, **kw: {'history':[], 'upcoming':[]})
    monkeypatch.setattr(astock, 'announcements', lambda *a, **kw: [{'date':'2026-09-09','title':'归属公告','url':'notice'}])
    monkeypatch.setattr(astock, 'financials', lambda *a: {'period':'2026-06-30'})
    def fail(*a): raise TimeoutError()
    monkeypatch.setattr(astock, 'announcement_content', fail)
    value = e.get_risk_context('300750')
    assert 'TimeoutError' in value and '2026-06-30' in value and '"完整读取": false' in value
