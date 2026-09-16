# Adapted from Vibe-Research sources/probability.py (GlobalPercent taxonomy).
# MIT License
#
# Copyright (c) 2026 simonlin1212
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.
from __future__ import annotations

import contextvars
import json
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from typing import Optional

import os
import tempfile
from pathlib import Path
from threading import Lock

CACHE_FILE = Path(__file__).with_name(".cache") / "probability.json"
_refresh_lock = Lock()

KALSHI_EVENTS = "https://api.elections.kalshi.com/trade-api/v2/events"
KALSHI_SERIES = "https://api.elections.kalshi.com/trade-api/v2/series"
POLY_MARKETS = "https://gamma-api.polymarket.com/markets"
POLY_TAGS = "https://gamma-api.polymarket.com/tags"
UA = "Mozilla/5.0 (vibe-research-agent)"

CORE_MODULES = ("货币政策", "宏观经济", "地缘政治", "政治选举", "股指大宗", "AI科技")
REFERENCE_MODULES = ("加密", "体育", "娱乐", "其他")

PER_MODULE = 3

# 协作式预算限制逐块读取；DNS 等待仍取决于系统超时。
SOURCE_BUDGET_SECONDS = 65.0
_source_deadline: contextvars.ContextVar[Optional[float]] = contextvars.ContextVar("macro_source_deadline", default=None)

HORIZON_DAYS = 800

FAR_DAYS = 180

KALSHI_PAGES = 6
POLY_PAGES = 4

KALSHI_MACRO_CATEGORIES = ("Economics", "Financials")
KALSHI_MACRO_SERIES_MAX = 12
_MACRO_SERIES_KW = ("cpi", "pce", "ppi", "inflation", "gdp", "recession", "unemploy", "payroll",
                    "jobless", "fed ", "fomc", "interest rate", "treasury", "yield")
_POLY_MACRO_TAG_KW = ("macro", "econom", "inflation", "recession", "fed", "interest rate")

GUARD = ("读法:预测市场概率是**市场当前的定价预期**,不是事实也不是预测,更不是本报告的判断;"
         "概率随时在变、只在 as_of 那一刻成立,引用必须带日期;低成交量合约噪音极大,量小的不要当信号;"
         "不得写成会发生 / 将发生 / 预计")

_GEO = ["china", "taiwan", "tariff", "trade war", "xi jinping", "hormuz", "iran", "venezuela",
        "russia", "ukraine", "blockade", "north korea", "israel", "gaza", "hezbollah", "lebanon",
        "syria", "middle east", " nato", "nuclear", "missile", "ceasefire", "invade", "war ",
        "military", "peace deal", "strike on"]
_MONETARY = ["fed ", "fed decision", "fed funds", "federal reserve", "interest rate", "rate cut",
             "rate hike", "fomc", "powell", "basis point", "rate after"]
_MACRO = ["recession", " gdp", "inflation", " cpi", "unemployment", "jobs report", "jobs numbers",
          "payroll", "nonfarm", "jobless", " ppi", " pce", "gas price"]
_AI = ["nvidia", "openai", " agi", "semiconductor", "tsmc", " chip", "anthropic", "gpt", "chatgpt",
       "llm", "grok", "gemini", "claude", "deepmind", "artificial intelligence", "best ai",
       "humanoid robot", "deepseek"]
_INDEX = ["s&p", "nasdaq", "dow ", " stock", "earnings", " ipo", "market cap", "crude oil",
          "wti", "brent", "oil price", "gold price", "gold hit", "gold above", " xau",
          "commodit", " spy ", "valuation"]
_ELECTION = ["election", "president", " senate", "congress", "nominee", "potus", "white house",
             "governor", " mayor", "parliament", "prime minister", "referendum", "trump", "newsom",
             " vance", "midterm", "impeach", "attorney general", "reconciliation", "election winner"]
_CRYPTO = ["bitcoin", " btc", "ethereum", "crypto", "microstrategy", " mstr", "solana", "dogecoin",
           "coinbase", "stablecoin", "ripple", " xrp"]
_SPORTS = ["nba", "nfl", " mlb", "world series", "super bowl", "stanley cup", "tennis", " atp", " wta",
           "wimbledon", "us open", "french open", "australian open", "ufc", "boxing", "premier league",
           "la liga", "champions league", "grand prix", " pga ", "esports", " lol ", "cs2", "valorant",
           "dota", " vs.", " vs ", "world cup", "fifa", "golf", "tournament", "playoff", "champion"]
_ENT = ["movie", "oscar", "grammy", "box office", "taylor swift", "tweet", "person of the year",
        "rotten tomatoes", "billboard", "spotify", "netflix", "love island", "celebrity", "album",
        " song ", "emmy", "what will"]
_KALSHI_CAT = {"Economics": "宏观经济", "Financials": "股指大宗", "Commodities": "股指大宗",
               "Companies": "股指大宗", "Elections": "政治选举", "Politics": "政治选举",
               "World": "地缘政治", "Crypto": "加密", "Sports": "体育", "Entertainment": "娱乐"}

# ponytail: 上游关键词分类会有歧义；出现误归类时优先补充源的结构化类别。
def classify(question: Optional[str], kalshi_category: Optional[str] = None) -> str:

    t = " " + (question or "").lower() + " "
    if "world cup" in t or "fifa" in t:
        return "体育"
    for kws, mod in ((_GEO, "地缘政治"), (_MONETARY, "货币政策"), (_MACRO, "宏观经济"), (_AI, "AI科技"),
                     (_CRYPTO, "加密"), (_INDEX, "股指大宗"), (_ELECTION, "政治选举"),
                     (_SPORTS, "体育"), (_ENT, "娱乐")):
        if any(k in t for k in kws):
            return mod
    return _KALSHI_CAT.get(kalshi_category or "", "其他")

def _polymarket_module(row: dict, title: str) -> str:

    events = row.get("events")
    has_game = isinstance(events, list) and any(
        isinstance(event, dict) and event.get("gameId") is not None for event in events
    )
    if row.get("sportsMarketType") or row.get("gameStartTime") or has_game:
        return "体育"
    return classify(title)

class ProbabilityError(RuntimeError):
    pass

def _get(url: str, params: dict, timeout: int = 25) -> bytes:

    deadline = _source_deadline.get()
    def remaining() -> float:
        left = deadline - time.monotonic() if deadline is not None else float(timeout)
        if left <= 0:
            raise TimeoutError("本源取数时间预算已用尽，未查完的部分保持未知")
        return left

    q = f"{url}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(q, headers={"User-Agent": UA, "Accept": "application/json"})

    with urllib.request.urlopen(req, timeout=min(float(timeout), 10.0, remaining())) as response:
        chunks = []
        while True:
            remaining()
            chunk = response.read1(64 * 1024)
            remaining()
            if not chunk:
                return b"".join(chunks)
            chunks.append(chunk)

def _f(v) -> Optional[float]:
    try:
        x = float(v)
        return x if x == x and x not in (float("inf"), float("-inf")) else None
    except (TypeError, ValueError):
        return None

def _valid_day(v: str) -> bool:

    if len(v) != 10:
        return False
    try:
        datetime.strptime(v, "%Y-%m-%d")
        return True
    except ValueError:
        return False

def _days_out(close_day: str, today: str) -> Optional[int]:

    if not close_day or len(close_day) != 10:
        return None
    try:
        return (datetime.strptime(close_day, "%Y-%m-%d") - datetime.strptime(today, "%Y-%m-%d")).days
    except ValueError:
        return None

def keep_contract(close_day: str, today: str, vol24: float, vol_total: float, open_interest: float = 0.0) -> Optional[str]:

    d = _days_out(close_day, today)
    if d is not None and d < 0:
        return "expired"
    if d is not None and d > HORIZON_DAYS:
        return "far_dated"
    if vol24 <= 0 and vol_total <= 0 and open_interest <= 0:
        return "dead"
    if d is not None and d > FAR_DAYS and vol24 <= 0:
        return "far_illiquid"
    return None

def _pick_leg(markets: list) -> Optional[dict]:

    best, bestd = None, 9.9
    for m in markets:
        if not isinstance(m, dict):
            continue

        p, kind = _f(m.get("yes_ask_dollars")), "ask"
        if p is None:
            p, kind = _f(m.get("last_price_dollars")), "last"
        if p is None:
            cents = _f(m.get("yes_ask"))
            p, kind = (cents / 100 if cents is not None else None), "ask"
        if p is None:
            cents = _f(m.get("last_price"))
            p, kind = (cents / 100 if cents is not None else None), "last"
        if p is None or not 0 < p < 1:
            continue
        d = abs(p - 0.5)
        if d < bestd:
            best, bestd = {**m, "_prob": p, "_price_type": kind}, d
    return best

def _stamp() -> str:

    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

def _get_stamped(url: str, params: dict) -> tuple[bytes, str]:

    body = _get(url, params)
    return body, _stamp()

def _kalshi_shape(evs: list, today: str, dropped: dict, out: list, raw_ref: Optional[str],
                  fetched_at: str) -> None:

    for ev in evs:
        if not isinstance(ev, dict):
            continue
        title = str(ev.get("title") or "")
        mod = classify(title, str(ev.get("category") or ""))
        if mod not in CORE_MODULES:
            continue
        leg = _pick_leg(ev.get("markets") or [])
        if not leg:
            continue
        close = str(leg.get("close_time") or ev.get("close_time") or "")[:10]
        if not _valid_day(close):

            dropped["missing_close"] = dropped.get("missing_close", 0) + 1
            continue

        v24 = _f(leg.get("volume_24h_fp")) or 0.0
        vtot = _f(leg.get("volume_fp")) or 0.0
        oi = _f(leg.get("open_interest_fp")) or 0.0
        why = keep_contract(close, today, v24, vtot, oi)
        if why:
            dropped[why] = dropped.get(why, 0) + 1
            continue
        out.append({"module": mod, "venue": "kalshi", "title": title,
                    "leg": str(leg.get("yes_sub_title") or leg.get("subtitle") or leg.get("ticker") or ""),
                    "prob": leg["_prob"], "price_type": leg.get("_price_type") or "unknown",
                    "volume": v24, "volume_total": vtot, "open_interest": oi,
                    "volume_missing": _f(leg.get("volume_24h_fp")) is None,
                    "ticker": str(leg.get("ticker") or ev.get("event_ticker") or ""),
                    "close": close, "as_of": fetched_at, "raw_ref": raw_ref})

def _kalshi_macro_series(warns: Optional[list] = None) -> tuple[list, Optional[str], bool]:

    tickers: list = []
    raw_ref = None
    page_truncated = False
    for cat in KALSHI_MACRO_CATEGORIES:
        body = _get(KALSHI_SERIES, {"limit": "1000", "category": cat})
        page_ref = None
        raw_ref = raw_ref or page_ref
        data = json.loads(body)
        if not isinstance(data, dict) or not isinstance(data.get("series"), list):
            raise ProbabilityError(f"Kalshi /series({cat}) 响应缺 series 数组(结构变了)")
        rows = data["series"]
        if len(rows) >= 1000:
            page_truncated = True
            if warns is not None:
                warns.append(f"Kalshi /series({cat}) 返回满 1000 条,可能还有更多系列未纳入(抽样不是全量)")
        for sr in rows:
            if not isinstance(sr, dict):
                continue
            t = f" {str(sr.get('title') or '').lower()} "
            if any(k in t for k in _MACRO_SERIES_KW) and sr.get("ticker"):
                tickers.append(str(sr["ticker"]))
    seen: set = set()
    uniq = [t for t in tickers if not (t in seen or seen.add(t))]
    over_cap = len(uniq) > KALSHI_MACRO_SERIES_MAX
    truncated = page_truncated or over_cap
    if warns is not None and over_cap:

        warns.append(f"匹配到 {len(uniq)} 个 Kalshi 宏观系列,只取前 {KALSHI_MACRO_SERIES_MAX} 个")

    return uniq[:KALSHI_MACRO_SERIES_MAX], raw_ref, truncated

def _kalshi(today: str, dropped: dict) -> tuple[list, list, Optional[str], bool]:

    out: list = []
    warns: list = []
    complete = True
    cursor, raw_ref = "", None
    for _page in range(KALSHI_PAGES):
        params = {"limit": "200", "status": "open", "with_nested_markets": "true"}
        if cursor:
            params["cursor"] = cursor
        try:
            body, fetched = _get_stamped(KALSHI_EVENTS, params)
            page_ref = None
            raw_ref = raw_ref or page_ref
            data = json.loads(body)
            evs = data.get("events") if isinstance(data, dict) else None
            if not isinstance(evs, list):
                raise ProbabilityError("Kalshi 响应缺 events 数组(结构变了)")
        except Exception as e:
            if _page == 0:
                raise
            warns.append(f"Kalshi 广度取数失败，保留已取得页面，后续范围未知:{type(e).__name__}: {str(e)[:100]}")
            complete = False
            break
        _kalshi_shape(evs, today, dropped, out, page_ref, fetched)
        cursor = str(data.get("cursor") or "") if isinstance(data, dict) else ""
        if not cursor:
            break
    else:

        if cursor:
            warns.append(f"Kalshi 广度采样翻满 {KALSHI_PAGES} 页仍有下一页,后续合约未纳入(结果是抽样不是全量)")
            complete = False
    try:
        series, sref, series_truncated = _kalshi_macro_series(warns)
        raw_ref = raw_ref or sref
        complete = complete and not series_truncated
        for tk in series:
            body, fetched = _get_stamped(KALSHI_EVENTS, {"status": "open", "with_nested_markets": "true",
                                                          "series_ticker": tk, "limit": "50"})
            sub_ref = None
            data = json.loads(body)
            evs = data.get("events") if isinstance(data, dict) else None
            if not isinstance(evs, list):

                raise ProbabilityError(f"Kalshi 系列 {tk} 响应缺 events 数组(结构变了)")
            if len(evs) >= 50:
                warns.append(f"Kalshi 系列 {tk} 返回满 50 条事件,可能还有更多未纳入")
                complete = False
            _kalshi_shape(evs, today, dropped, out, sub_ref, fetched)
    except Exception as e:
        warns.append(f"Kalshi 宏观系列定向取数失败(广度采样仍在,但宏观经济模块可能因此空缺):{type(e).__name__}: {str(e)[:100]}")
        complete = False
    if not out and complete:

        warns.append("Kalshi 开放事件里没有落入 6 个核心模块的合约(不是故障)")
    return out, warns, raw_ref, complete

def _as_list(v):

    if isinstance(v, str):
        try:
            v = json.loads(v)
        except ValueError:
            return []
    return v if isinstance(v, list) else []

def _poly_shape(rows: list, today: str, dropped: dict, out: list, raw_ref: Optional[str],
                fetched_at: str) -> None:
    for m in rows:
        if not isinstance(m, dict):
            continue
        title = str(m.get("question") or "")
        mod = _polymarket_module(m, title)
        if mod not in CORE_MODULES:
            continue

        prices, outcomes = _as_list(m.get("outcomePrices")), _as_list(m.get("outcomes"))
        p, leg_label, price_type = None, "", "outcome_price"
        if prices and outcomes and len(prices) == len(outcomes):
            for name, px in zip(outcomes, prices):
                if str(name).strip().lower() == "yes":
                    p, leg_label = _f(px), "Yes"
                    break
            if p is None:

                key = "no_price" if leg_label == "Yes" else "no_yes_leg"
                dropped[key] = dropped.get(key, 0) + 1
                continue
        elif prices or outcomes:

            dropped["outcome_shape_drift"] = dropped.get("outcome_shape_drift", 0) + 1
            continue
        else:

            dropped["outcome_shape_drift"] = dropped.get("outcome_shape_drift", 0) + 1
            continue
        if p is None or not 0 < p < 1:
            dropped["no_price"] = dropped.get("no_price", 0) + 1
            continue
        close = str(m.get("endDate") or "")[:10]
        if not _valid_day(close):
            dropped["missing_close"] = dropped.get("missing_close", 0) + 1
            continue
        v24 = _f(m.get("volume24hr")) or 0.0
        vtot = _f(m.get("volume")) or 0.0
        why = keep_contract(close, today, v24, vtot)
        if why:
            dropped[why] = dropped.get(why, 0) + 1
            continue
        out.append({"module": mod, "venue": "polymarket", "title": title, "leg": leg_label,
                    "prob": p, "price_type": price_type,
                    "volume": v24, "volume_total": vtot, "open_interest": 0.0,
                    "volume_missing": _f(m.get("volume24hr")) is None,
                    "ticker": str(m.get("slug") or m.get("conditionId") or ""),
                    "close": close, "as_of": fetched_at, "raw_ref": raw_ref})

def _poly_macro_tags(warns: Optional[list] = None) -> tuple[list, bool]:

    body = _get(POLY_TAGS, {"limit": "500"})

    data = json.loads(body)
    if not isinstance(data, list):
        raise ProbabilityError("Polymarket /tags 响应不是数组(结构变了)")
    truncated = len(data) >= 500
    if warns is not None and truncated:
        warns.append("Polymarket /tags 返回满 500 条,可能还有更多标签未纳入(抽样不是全量)")
    ids = []
    for t in data:
        if not isinstance(t, dict):
            continue
        txt = f"{str(t.get('label') or '').lower()} {str(t.get('slug') or '').lower()}"
        if any(k in txt for k in _POLY_MACRO_TAG_KW) and t.get("id") is not None:
            ids.append(str(t["id"]))
    if len(ids) > 8:
        truncated = True
        if warns is not None:
            warns.append(f"匹配到 {len(ids)} 个 Polymarket 宏观标签,只取前 8 个")
    return ids[:8], truncated

def _polymarket(today: str, dropped: dict) -> tuple[list, list, Optional[str], bool]:

    out: list = []
    warns: list = []
    complete = True
    raw_ref = None
    full_pages = 0
    for page in range(POLY_PAGES):
        params = {"active": "true", "closed": "false", "limit": "100",
                  "offset": str(page * 100), "order": "volume24hr", "ascending": "false"}
        try:
            body, fetched = _get_stamped(POLY_MARKETS, params)
            page_ref = None
            raw_ref = raw_ref or page_ref
            data = json.loads(body)
            if not isinstance(data, list):
                raise ProbabilityError("Polymarket 响应不是数组(结构变了)")
        except Exception as e:
            if page == 0:
                raise
            warns.append(f"Polymarket 广度取数失败，保留已取得页面，后续范围未知:{type(e).__name__}: {str(e)[:100]}")
            complete = False
            break
        if not data:
            break
        full_pages = page + 1 if len(data) >= 100 else full_pages
        _poly_shape(data, today, dropped, out, page_ref, fetched)
    if full_pages >= POLY_PAGES:
        warns.append(f"Polymarket 广度采样翻满 {POLY_PAGES} 页且末页仍是满的,后续市场未纳入(抽样不是全量)")
        complete = False
    try:
        tag_ids, tags_truncated = _poly_macro_tags(warns)
        complete = complete and not tags_truncated
        for tid in tag_ids:
            body, fetched = _get_stamped(POLY_MARKETS, {"tag_id": tid, "active": "true", "closed": "false",
                                                        "limit": "50", "order": "volume24hr", "ascending": "false"})
            sub_ref = None
            data = json.loads(body)
            if not isinstance(data, list):
                raise ProbabilityError(f"Polymarket 标签 {tid} 响应不是数组(结构变了)")
            if len(data) >= 50:
                warns.append(f"Polymarket 标签 {tid} 返回满 50 条,可能还有更多未纳入")
                complete = False
            _poly_shape(data, today, dropped, out, sub_ref, fetched)
    except Exception as e:
        warns.append(f"Polymarket 宏观标签定向取数失败(广度采样仍在):{type(e).__name__}: {str(e)[:100]}")
        complete = False
    if not out and complete:
        warns.append("Polymarket 活跃市场里没有落入 6 个核心模块的合约(不是故障)")
    return out, warns, raw_ref, complete

def macro_probability(now: Optional[datetime] = None) -> dict:

    _now = (now or datetime.now(timezone.utc))
    _now = _now.astimezone(timezone.utc) if _now.tzinfo else _now.replace(tzinfo=timezone.utc)
    today = _now.strftime("%Y-%m-%d")

    fetch_started = _now.strftime("%Y-%m-%dT%H:%M:%SZ")
    items: list = []
    warns: list = []
    errors: list = []
    refs: dict = {}
    dropped: dict = {}
    ok_sources = 0
    ok_names: list = []
    partial_names: list = []
    for name, fn in (("kalshi", _kalshi), ("polymarket", _polymarket)):
        budget_token = _source_deadline.set(time.monotonic() + SOURCE_BUDGET_SECONDS)
        try:
            got, w, ref, complete = fn(today, dropped)
            items.extend(got)
            warns.extend(w)
            refs[name] = ref
            ok_sources += 1

            (ok_names if complete else partial_names).append(name)
        except Exception as e:
            errors.append(f"{name}: {type(e).__name__}: {str(e)[:140]}")
        finally:
            _source_deadline.reset(budget_token)
    if ok_sources == 0:

        raise ProbabilityError("两个预测市场源都失败:" + "; ".join(errors))

    picked: list = []
    seen: set = set()
    for mod in CORE_MODULES:

        rows = sorted([x for x in items if x["module"] == mod],
                      key=lambda x: (-max(x["volume"], x.get("open_interest", 0.0)), -x.get("volume_total", 0.0)))
        n = 0
        for r in rows:
            key = (r["venue"], r["title"][:80])
            if key in seen:
                continue
            seen.add(key)
            picked.append(r)
            n += 1
            if n >= PER_MODULE:
                break

    empty = [m for m in CORE_MODULES if not any(x["module"] == m for x in picked)]

    return {"today": today, "as_of": _stamp(), "fetch_started": fetch_started, "items": picked, "sources_ok": ok_names, "sources_partial": partial_names, "modules": list(CORE_MODULES), "empty_modules_diagnostic": empty,
            "dropped_reference_modules": list(REFERENCE_MODULES), "per_module_cap": PER_MODULE,
            "raw_refs": refs, "warnings": warns, "errors": errors, "guard": GUARD,
            "horizon_days": HORIZON_DAYS, "dropped": dropped}


def get_probability(force: bool = False) -> dict:
    """读存档；刷新失败保留旧文件，并由界面标记旧数据。"""
    started = time.time()
    def cached():
        try:
            data = json.loads(CACHE_FILE.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) and isinstance(data.get("items"), list) and data.get("updated") else None
        except (OSError, ValueError):
            return None

    if not force:
        return cached() or {"items": [], "updated": "", "partial": False, "how_to_read": [], "warnings": []}
    with _refresh_lock:
        previous = cached()
        if previous and CACHE_FILE.stat().st_mtime >= started:
            return previous
        result = macro_probability()
        if not result["items"] and (result["errors"] or result["sources_partial"]):
            raise ProbabilityError("本轮未取得合约报价，数据覆盖不完整，请稍后重试")
        data = {
            "items": [{"topic": it["module"], "source": it["venue"], "title": it["title"],
                       "leg": it["leg"], "prob": it["prob"], "settle": it["close"],
                       "volume": None if it["volume_missing"] else it["volume"],
                       "price_type": it["price_type"], "as_of": it["as_of"]}
                      for it in result["items"]],
            "updated": result["as_of"],
            "partial": bool(result["errors"] or result["sources_partial"]),
            "warnings": result["warnings"] + result["errors"],
            "how_to_read": [result["guard"].removeprefix("读法:").replace("**", "")],
        }
        CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
        tmp = None
        try:
            with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=CACHE_FILE.parent,
                                             suffix=".tmp", delete=False) as f:
                tmp = f.name
                json.dump(data, f, ensure_ascii=False, allow_nan=False)
            os.replace(tmp, CACHE_FILE)
        finally:
            if tmp and os.path.exists(tmp):
                os.unlink(tmp)
        return data
