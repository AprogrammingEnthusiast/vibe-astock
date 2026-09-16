"""个股深挖图装配 + run 入口。

四分析师串行 → 正方⚔反方辩论环 → 裁判。辩论循环沿用 count 计数模式。
"""

from __future__ import annotations

import json
import re
from decimal import Decimal

from langgraph.graph import END, START, StateGraph

from . import data
from .agents import (
    AVOID, JOIN,
    create_avoid_debator, create_capital_analyst, create_join_debator,
    create_judge, create_risk_analyst, create_technical_analyst, create_theme_analyst,
)
from .state import StockDeepDiveState, new_stock_debate_state
from ..config import make_llm
from ..debate import make_debate_router
from ..util import china_today, is_degraded_report
from ..llm_errors import LlmConfigError

_JUDGE = "裁判"
_ROUTES = {JOIN: JOIN, AVOID: AVOID, _JUDGE: _JUDGE}


def _has_blanket_grade(result):
    # ponytail: explicit blanket grading only; specific uncertainties remain allowed.
    text = re.sub(r'[*_`]', '', json.dumps(result, ensure_ascii=False))
    return bool(re.search(r'(?:总体|整体|综合)风险(?:等级|评级)|(?:总体|整体|综合)风险\s*(?:[：:]|为|是|均|无法判断)|风险(?:等级|评级)\s*[：:]', text))


def _validate_volume(kline, result):
    source = re.search(r"此前5个完整交易日均量的\s*([0-9]+(?:\.[0-9]+)?)\s*倍", kline)
    if not source:
        return
    expected = Decimal(source[1])
    # ponytail: 只核对数字形式的均量比例；更广的语义核验需结构化事实引用。
    for value, unit in re.findall(
        r"(?:均量|平均成交量)(?:的|约|为|是|\s)*([0-9]+(?:\.[0-9]+)?)\s*(倍|[%％])",
        json.dumps(result, ensure_ascii=False),
    ):
        actual = Decimal(value) / (100 if unit != "倍" else 1)
        if actual != expected:
            raise LlmConfigError("成交量相对均量的数值或单位与原始资料不一致，已停止；原报告已保留，请重试")


def build_deepdive_graph(max_rounds: int = 1, *, llm=None, data_source=None, progress=None, check=None, pack=None):
    router = make_debate_router(JOIN, AVOID, _JUDGE, max_rounds)  # 共享路由，含轮数校验
    quick = llm if llm is not None else make_llm(deep=False)
    deep = llm if llm is not None else make_llm(deep=True)
    def stage(name, node):
        def invoke(state):
            if check: check()
            if progress: progress(name)
            result = node(state)
            if _has_blanket_grade(result):
                if check: check()
                if progress: progress(name + '：校正证据表述')
                corrected = dict(state, _output_correction=(
                    '【输出校验反馈】上次回答含无定义的整体风险分级。请重新生成，删除分级句；'
                    '按具体事项分别陈述已知事实、证据日期和缺少的材料。不要复述本反馈。'))
                result = node(corrected)
                if _has_blanket_grade(result):
                    raise LlmConfigError('报告仍含无依据的整体风险分级，已停止；原报告已保留')
            _validate_volume(state.get("kline", ""), result)
            if check: check()
            return result
        return invoke
    g = StateGraph(StockDeepDiveState)
    g.add_node("题材归属", stage("题材归属", create_theme_analyst(quick, data_source, pack)))
    g.add_node("资金流向", stage("资金流向", create_capital_analyst(quick, data_source, pack)))
    g.add_node("技术形态", stage("技术形态", create_technical_analyst(quick, data_source, pack)))
    g.add_node("风险排查", stage("风险排查", create_risk_analyst(quick, data_source, pack)))
    g.add_node(JOIN, stage(JOIN, create_join_debator(quick)))
    g.add_node(AVOID, stage(AVOID, create_avoid_debator(quick)))
    g.add_node(_JUDGE, stage(_JUDGE, create_judge(deep, pack)))

    g.add_edge(START, "题材归属")
    g.add_edge("题材归属", "资金流向")
    g.add_edge("资金流向", "技术形态")
    g.add_edge("技术形态", "风险排查")
    g.add_edge("风险排查", JOIN)
    g.add_conditional_edges(JOIN, router, _ROUTES)
    g.add_conditional_edges(AVOID, router, _ROUTES)
    g.add_edge(_JUDGE, END)
    return g.compile()


def run(code_or_name: str, trade_date: str | None = None, *, llm=None, data_source=None, progress=None, check=None, pack=None) -> dict:
    """深挖一只票。返回 final state，含 verdict / verdict_struct / 四报告 / 辩论。"""
    source = data_source if data_source is not None else data
    if check: check()
    code, name = source.resolve(code_or_name)
    if not code:
        return {"error": f"无法识别标的：{code_or_name!r}（请给 6 位代码或准确简称）"}
    profile = source.get_profile(code)  # 一次性行情快照，各分析师共享
    if is_degraded_report(profile):   # 连行情都取不到 → 停牌/无效标的，别白跑 7 次 LLM
        return {"error": f"{name or code} 行情不可用（可能停牌或非有效标的），已中止深挖"}
    trade_date = trade_date or china_today()   # 始终以交易所时区记录资料日期
    supplement = {}
    for field, method, label in (
        ("technical", "get_long_term", "长期技术"), ("theme", "get_sector_context", "板块强弱"),
        ("capital", "get_capital_context", "资金资料"), ("risk", "get_risk_context", "风险资料"),
    ):
        if check: check()
        if progress: progress("获取" + label)
        try:
            getter = getattr(source, method, None)
            supplement[field] = getter(code) if getter and trade_date == china_today() else f"[⚠️ {label}未获取，当前补充源不提供历史时点资料]"
        except LlmConfigError:
            raise
        except Exception as exc:
            supplement[field] = f"[⚠️ {label}获取失败：{type(exc).__name__}；其他资料仍可使用]"
        if check: check()
    init = {
        "code": code, "name": name or code, "trade_date": trade_date, "profile": profile,
        "kline": source.get_kline(code),
        "supplement": supplement,
        "theme_report": "", "capital_report": "", "technical_report": "", "risk_report": "",
        "debate_state": new_stock_debate_state(),
        "verdict": "", "verdict_struct": None,
    }
    graph = build_deepdive_graph(llm=llm, data_source=data_source, progress=progress, check=check, pack=pack)
    return graph.invoke(init, {"recursion_limit": 50})
