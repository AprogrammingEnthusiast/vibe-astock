import json
from types import SimpleNamespace

import pytest

from duanxian.deepdive import data, graph
from duanxian.llm_errors import LlmConfigError
from duanxian.prompts import RESEARCH_PACK


@pytest.mark.parametrize('stamp,phase', [('20260910092000', '开盘集合竞价'),
    ('20260910103000', '盘中'), ('20260910145800', '收盘集合竞价'),
    ('20260910161451', '收盘后'), ('bad', '时段未知')])
def test_quote_phase_uses_quote_timestamp(monkeypatch, stamp, phase):
    fields = ['0'] * 55
    fields[1], fields[3], fields[30], fields[32] = '测试', '100', stamp, '0.36'
    monkeypatch.setattr(data.urllib.request, 'urlopen', lambda *a, **kw:
                        SimpleNamespace(read=lambda: '~'.join(fields).encode('gbk')))
    value = data.get_profile('300750')
    assert phase in value and '单日涨跌幅' in value
    if phase == '收盘后':
        assert '试撮合' not in value


KLINE = '已收盘K线截至 2026-09-10；2连涨；最近已收盘日成交量是此前5个完整交易日均量的 0.9 倍'


def run_graph(reply, judge_reply=None, supplement=None):
    calls, fetches = [], []
    def kline(code):
        fetches.append(code)
        return KLINE
    source = SimpleNamespace(resolve=lambda s: ('300750', '测试'), get_profile=lambda c: '单日涨跌幅 0.36%',
        get_kline=kline, get_theme=lambda *a: '电池；有日期的新闻', get_lhb=lambda c: '窗口内未查到龙虎榜记录')
    for name, getter in (supplement or {}).items():
        setattr(source, name, getter)
    def invoke(prompt):
        calls.append(prompt)
        if '个股深挖裁判' in prompt:
            obj = json.loads(RESEARCH_PACK.verdict_skeleton)
            # Use the real model schema with minimal valid textual fields.
            obj.update(one_liner='资料已核对', theme='题材', capital='资金', technical=judge_reply or reply,
                       risks=['资料局限'], debate_takeaway='双方存在分歧')
            return SimpleNamespace(content=json.dumps(obj, ensure_ascii=False))
        return SimpleNamespace(content=reply)
    result = graph.run('300750', '2026-09-10', llm=SimpleNamespace(invoke=invoke), data_source=source, pack=RESEARCH_PACK)
    return result, calls, fetches


def test_all_roles_share_original_facts_and_kline_is_fetched_once():
    result, prompts, fetches = run_graph('成交量约为此前5日均量的90%。')
    assert result['verdict_struct']
    assert fetches == ['300750']
    assert len(prompts) == 7
    assert all(KLINE in p and '单日涨跌幅 0.36%' in p for p in prompts)


@pytest.mark.parametrize('reply', ['成交量约为此前5日均量的0.9%。', '成交量约为前五日平均成交量的1.9倍。'])
def test_wrong_volume_unit_or_value_stops_graph(reply):
    with pytest.raises(LlmConfigError, match='成交量'):
        run_graph(reply)


def test_judge_cannot_reintroduce_wrong_units():
    with pytest.raises(LlmConfigError, match='成交量'):
        run_graph('成交量为此前5日均量的0.9倍。', '成交量为此前5日均量的0.9%。')


def test_supplement_shared_once_and_failure_isolated(monkeypatch):
    monkeypatch.setattr(graph,'china_today',lambda:'2026-09-10')
    calls=[]
    def good(code):
        calls.append(code)
        return '长期证据标记'
    def failed(code):
        raise TimeoutError()
    result,prompts,_=run_graph('数据有局限。',supplement={'get_long_term':good,'get_capital_context':failed})
    assert calls==['300750'] and len(prompts)==7
    assert all('长期证据标记' in p and 'TimeoutError' in p for p in prompts)
    assert result['verdict_struct']


@pytest.mark.parametrize('reply', ['成交量为此前5日均量的0.9倍。', '成交量比此前5日均量下降10%。',
                                  '换手率0.9%，成交量偏弱。'])
def test_correct_units_and_other_percentages_are_not_rejected(reply):
    assert run_graph(reply)[0]['verdict_struct']
