"""Compatible presentation envelope for existing stock deep-dive archives."""
import html
import json
import re
from ..util import china_now
from ..util import is_degraded_report
from ..review_store import md_to_html as _md_to_html, strip_prefix as _strip_prefix
SCHEMA_VERSION = 1

def _notice_excerpt_html(supplement):
    sections = []
    for line in supplement.splitlines():
        try:
            value = json.loads(line)
        except (ValueError, TypeError):
            continue
        if not isinstance(value, dict):
            continue
        for notice in value.get('正文核验', []):
            facts = notice.get('原文事实摘录', [])
            url = notice.get('链接', '')
            if not facts or not re.fullmatch(r'https://data\.eastmoney\.com/notices/detail/[0-9]{6}/AN[0-9]+\.html', url):
                continue
            title = html.escape(str(notice.get('标题', '公告')))
            date = html.escape(str(notice.get('日期', '日期未提供'))[:10])
            items = ''.join('<li>' + html.escape(str(fact)) + '</li>' for fact in facts)
            sections.append(f'<p><a href="{url}">{title}</a> · {date}</p><ul>{items}</ul>')
    if not sections:
        return ''
    return '<h4>公告原文事实摘录</h4><p>以下直接摘自已取得的公告正文，非模型推断；保留原文条件，不代表事项已实施。</p>' + ''.join(sections)


def serialize(final: dict) -> dict:
    ds = final.get("debate_state", {}) or {}
    now = china_now().strftime("%Y-%m-%d %H:%M") + " CST"
    def report(field):
        text = final.get(field + "_report", "")
        warnings = [line for line in final.get("supplement", {}).get(field, "").splitlines() if is_degraded_report(line)]
        rendered = _md_to_html("\n\n".join([text, *warnings]))
        if field == 'risk':
            rendered += _notice_excerpt_html(final.get('supplement', {}).get(field, ''))
        return rendered
    return {
        "schema_version": SCHEMA_VERSION,
        "run_type": "stock_deepdive",
        "code": final.get("code", ""),
        "name": final.get("name", ""),
        "trade_date": final.get("trade_date", ""),
        "generated_at": now,
        "verdict": final.get("verdict_struct"),
        "verdict_md": final.get("verdict", ""),
        "reports": {
            "theme": report("theme"),
            "capital": report("capital"),
            "technical": report("technical"),
            "risk": report("risk"),
        },
        "debate": {
            "join": _md_to_html(_strip_prefix(_strip_prefix(ds.get("join_history", ""), "正方:"), "参与派:")),
            "avoid": _md_to_html(_strip_prefix(_strip_prefix(ds.get("avoid_history", ""), "反方:"), "回避派:")),
        },
    }
