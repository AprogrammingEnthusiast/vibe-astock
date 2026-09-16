import datetime
from types import SimpleNamespace

import pytest

from vr import astock


def test_lockup_uses_event_shares_and_preserves_unknown(monkeypatch):
    filters = []
    def rows(*a, **kw):
        filters.append(kw['filter_str'])
        return [{'FREE_DATE': '2024-09-24', 'FREE_SHARES': 390146.5544,
                 'CURRENT_FREE_SHARES': 320.8269, 'ABLE_FREE_SHARES': 0, 'FREE_RATIO': None}]
    monkeypatch.setattr(astock, 'eastmoney_datacenter', rows)
    result = astock.lockup_expiry('300750', '2026-09-10')
    assert result['history'][0]['shares'] == pytest.approx(3208269)
    assert result['history'][0]['able_shares'] == 0
    assert result['history'][0]['ratio'] is None
    assert 'FREE_DATE<' in filters[0]


def test_announcements_can_request_second_page(monkeypatch):
    import requests
    params = []
    monkeypatch.setattr(requests, 'get', lambda *a, **kw:
        (params.append(kw['params']) or SimpleNamespace(json=lambda: {'data': {'list': []}})))
    assert astock.announcements('300750', 50, page=2) == []
    assert params[0]['page_index'] == 2


def test_industry_comparison_uses_all_pages(monkeypatch):
    from duanxian import fetchers
    monkeypatch.setattr(fetchers, '_clist', lambda *a, **kw: [
        {'f12':str(i),'f14':str(i),'f3':200-i,'f104':0,'f105':2} for i in range(201)])
    result = astock.industry_comparison(2)
    assert result['total'] == 201
    assert result['bottom'][-1]['code'] == '200'


def test_risk_context_pages_dates_units_and_failure_isolation(monkeypatch):
    from duanxian.deepdive import evidence as e
    monkeypatch.setattr(e, 'china_now', lambda: datetime.datetime(2026,9,10,17))
    pages=[]
    def announcements(code, limit, page=1):
        pages.append(page)
        if page == 1:
            return [{'date':'2026-09-09','title':'普通公告','url':str(i)} for i in range(50)]
        return [{'date':'2026-04-01','title':'减持计划','url':'risk'},
                {'date':'2026-09-11','title':'尚未公开','url':'future'},
                {'date':'2024-01-01','title':'过期公告','url':'old'}]
    monkeypatch.setattr(astock,'announcements',announcements)
    monkeypatch.setattr(astock,'lockup_expiry',lambda *a, **kw: {'history':[], 'upcoming':[]})
    monkeypatch.setattr(astock,'financials',lambda *a: (_ for _ in ()).throw(TimeoutError()))
    result=e.get_risk_context('300750')
    assert pages == [1,2]
    assert '减持计划' in result and '尚未公开' not in result and '过期公告' not in result
    assert 'TimeoutError' in result and '未查到' in result and '标题' in result


def test_long_term_filters_intraday_and_rejects_invalid_prices(monkeypatch):
    import pandas as pd
    import akshare
    from duanxian.deepdive import evidence as e
    monkeypatch.setattr(e,'china_now',lambda:datetime.datetime(2026,9,10,10))
    monkeypatch.setattr(e,'is_a_share_closed',lambda:False)
    rows=pd.DataFrame({'date':pd.date_range('2025-09-01',periods=375),'close':[100.0]*375})
    rows.loc[len(rows)-1,'close']=999
    def fetch(**kw):
        assert kw['adjust']=='qfq' and kw['timeout']>0
        return rows
    monkeypatch.setattr(akshare,'stock_zh_a_hist_tx',fetch)
    result=e.get_long_term('300750')
    assert '前复权' in result and '2026-09-09' in result and '999' not in result
    assert '250' in result
    rows.loc[3,'close']=float('nan')
    assert '⚠️' in e.get_long_term('300750')


def test_supplement_warnings_survive_model_omission():
    from duanxian.deepdive.store import serialize
    result=serialize({'supplement': {'risk':'资料\n[⚠️ 财务缺失]'},'risk_report':'模型省略警告'})
    assert '财务缺失' in result['reports']['risk']


def test_capital_keeps_zero_negative_and_excludes_future(monkeypatch):
    from duanxian.deepdive import evidence as e
    monkeypatch.setattr(e,'china_now',lambda:datetime.datetime(2026,9,10,17))
    monkeypatch.setattr(e.fetchers,'fetch_individual_fund_flow',lambda:({'300750':{'inflow_raw':0}},[]))
    monkeypatch.setattr(astock,'margin_trading',lambda code:[{'date':'2026-09-09','rzye':0}, {'date':'2026-09-11','rzye':123456}])
    monkeypatch.setattr(astock,'block_trade',lambda code:[{'date':'2026-09-09','premium_pct':-2}])
    result=e.get_capital_context('300750')
    assert '"inflow_raw": 0' in result and '-2' in result and '123456' not in result
    assert '120日历史' in result and '未返回源交易时间' in result


def test_strict_datacenter_distinguishes_empty_from_error(monkeypatch):
    monkeypatch.setattr(astock,'em_get',lambda *a, **kw:SimpleNamespace(json=lambda:{'success':False,'message':'返回数据为空'}))
    assert astock.eastmoney_datacenter('test',strict=True)==[]
    monkeypatch.setattr(astock,'em_get',lambda *a, **kw:SimpleNamespace(json=lambda:{'success':False,'message':'bad column'}))
    with pytest.raises(ValueError): astock.eastmoney_datacenter('test',strict=True)


def test_complete_pagination_rejects_truncated_or_duplicate(monkeypatch):
    from duanxian import fetchers as f
    monkeypatch.setattr(f,'_direct_get',lambda *a, **kw:SimpleNamespace(json=lambda:{'data':{'total':2,'diff':[{'f12':'x'}]}}))
    with pytest.raises(ValueError): f._clist('x','x','x',max_pages=1,require_complete=True)
    with pytest.raises(ValueError): f._clist('x','x','x',max_pages=2,require_complete=True)


def test_financial_zero_remains_zero(monkeypatch):
    import pandas as pd
    monkeypatch.setattr(astock,'_akshare',lambda:SimpleNamespace(stock_financial_abstract_ths=lambda **kw:pd.DataFrame([{'报告期':'2026-06-30','净利润':0,'基本每股收益':0}])))
    result=astock.financials('300750')
    assert result['net_profit']==0 and result['eps']==0


def test_new_getters_are_frozen_and_allowlisted(tmp_path,monkeypatch):
    from review_agent.deepdive import FrozenStockInputs
    from review_agent import public_worker
    calls=[]
    monkeypatch.setattr(public_worker,'fetch_public',lambda name,args,*a: calls.append(name) or 'public')
    source=FrozenStockInputs(tmp_path,lambda:30)
    for name in ('get_long_term','get_sector_context','get_capital_context','get_risk_context'):
        assert name in public_worker.DEEPDIVE_CALLS
        assert getattr(source,name)('300750')==getattr(source,name)('300750')=='public'
    assert len(calls)==len(source.values)==4
    with pytest.raises(AttributeError): source.private_account
