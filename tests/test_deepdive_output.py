import json

import pytest

from duanxian.deepdive import graph
from duanxian.deepdive.evidence import notice_facts
from duanxian.deepdive.store import serialize
from duanxian.llm_errors import LlmConfigError
from test_deepdive_facts import run_graph


def test_blanket_grade_rewrites_once_without_mutating_input(monkeypatch):
    states = []
    def node(state):
        states.append(state)
        return {'theme_report': '具体资金序列缺失' if state.get('_output_correction') else '总体风险等级：无法判断'}
    monkeypatch.setattr(graph, 'create_theme_analyst', lambda *a: node)
    result, _, _ = run_graph('已有依据')
    assert len(states) == 2 and '_output_correction' not in states[0]
    assert result['theme_report'] == '具体资金序列缺失'


def test_repeated_blanket_grade_stops_and_judge_is_checked():
    assert graph._has_blanket_grade({'risks':['总体风险等级无法判断，公告覆盖存在缺口。']})
    assert graph._has_blanket_grade({'risk_report':'**总体风险等级**：无法判断'})
    with pytest.raises(LlmConfigError, match='原报告已保留'):
        run_graph('总体风险等级：无法判断')
    with pytest.raises(LlmConfigError, match='原报告已保留'):
        run_graph('具体事实', '总体风险均无法判断')
    assert not graph._has_blanket_grade({'risk_report':'缺少历史资金序列，连续方向无法判断。'})


def test_notice_facts_survive_model_omission_and_are_escaped():
    source = ('本次拟归属的限制性股票数量：422,839股。\n\n'
              '授予价格（调整后）：124.29元/股。\n\n'
              '2023-2025年累计营业收入为11,866.31亿元，未达到12,900亿元考核目标。')
    facts = notice_facts(source)
    assert len(facts) == 3 and '2023-2025' in facts[-1] and '124.29元/股' in facts[1]
    facts.append('<script>bad()</script>')
    value = json.dumps({'正文核验':[{'标题':'公告<img>', '日期':'2026-09-08',
        '链接':'https://data.eastmoney.com/notices/detail/300750/AN123.html', '原文事实摘录':facts}]}, ensure_ascii=False)
    report = serialize({'risk_report':'模型没有提公告', 'supplement':{'risk':value}})['reports']['risk']
    assert '422,839股' in report and '公告原文事实摘录' in report
    assert '<script>' not in report and '&lt;script&gt;' in report
    assert 'href="https://data.eastmoney.com' in report


def test_old_reports_and_failed_notices_remain_compatible():
    assert '公告原文事实摘录' not in serialize({'risk_report':'旧报告'})['reports']['risk']
    assert notice_facts('没有明确数量的普通标题') == []
