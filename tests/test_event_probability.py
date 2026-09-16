import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "vr"))
import probability as p

NOW = datetime(2026, 9, 8, tzinfo=timezone.utc)
TODAY = "2026-09-08"


def test_contract_parsing_and_filters():
    row = {"question": "Will the Fed cut rates?", "endDate": "2026-12-15",
           "volume24hr": "5000", "volume": "90000", "outcomes": '["No","Yes"]',
           "outcomePrices": '["0.73","0.27"]'}
    out, dropped = [], {}
    p._poly_shape([row], TODAY, dropped, out, None, p._stamp())
    assert out[0]["prob"] == 0.27 and out[0]["leg"] == "Yes"
    for changes in ({"outcomePrices": '["0.5"]'}, {"outcomes": '["Above","Below"]'},
                    {"endDate": "invalid"}, {"endDate": "2026-01-01"},
                    {"outcomePrices": '["0.2","NaN"]'},
                    {"question": "Borussia Dortmund", "sportsMarketType": "moneyline"}):
        out = []
        p._poly_shape([{**row, **changes}], TODAY, {}, out, None, p._stamp())
        assert not out
    assert p._pick_leg([{"last_price": "45"}])["_price_type"] == "last"
    assert p._pick_leg([{"yes_ask_dollars": "0.62"}])["_prob"] == 0.62
    assert p.keep_contract("2027-12-01", TODAY, 0, 1000) == "far_illiquid"
    assert p.keep_contract("2027-12-01", TODAY, 10, 1000) is None


def test_fetch_partial_pages_and_cache_survive_failure(monkeypatch, tmp_path):
    def fake_get(url, params):
        if url == p.KALSHI_EVENTS:
            raise OSError("source unavailable")
        if url == p.POLY_TAGS:
            return b"[]"
        if params.get("offset") == "100":
            raise TimeoutError("next page timeout")
        return json.dumps([{"question": "Fed rate cut?", "endDate": "2026-12-15",
                            "volume": "1000", "outcomes": ["No", "Yes"],
                            "outcomePrices": ["0.6", "0.4"]}]).encode()

    monkeypatch.setattr(p, "_get", fake_get)
    result = p.macro_probability(NOW)
    assert len(result["items"]) == 1
    assert result["sources_partial"] == ["polymarket"]
    assert result["errors"] and result["warnings"]
    monkeypatch.setattr(p, "CACHE_FILE", tmp_path / "probability.json")
    monkeypatch.setattr(p, "macro_probability", lambda: result)
    assert p.get_probability()["updated"] == ""
    saved = p.get_probability(True)
    assert saved["items"][0]["volume"] is None
    assert saved["partial"] and saved["items"][0]["prob"] == 0.4
    assert p.get_probability() == saved
    original = p.CACHE_FILE.read_bytes()

    def fail():
        raise p.ProbabilityError("offline")

    monkeypatch.setattr(p, "macro_probability", fail)
    with pytest.raises(p.ProbabilityError):
        p.get_probability(True)
    assert p.CACHE_FILE.read_bytes() == original
    monkeypatch.setattr(p, "macro_probability", lambda: {**result, "items": []})
    with pytest.raises(p.ProbabilityError):
        p.get_probability(True)
    assert p.CACHE_FILE.read_bytes() == original


def test_ranking_and_source_failures(monkeypatch):
    items = [{"module": "宏观经济", "venue": "kalshi", "title": str(i),
              "volume": i, "open_interest": 100 if i == 0 else 0} for i in range(5)]
    monkeypatch.setattr(p, "_kalshi", lambda *args: (items + items, [], None, True))
    monkeypatch.setattr(p, "_polymarket", lambda *args: ([], [], None, True))
    result = p.macro_probability(NOW)
    assert [x["title"] for x in result["items"]] == ["0", "4", "3"]
    def fail(*args):
        raise OSError("offline")
    monkeypatch.setattr(p, "_kalshi", fail)
    assert p.macro_probability(NOW)["sources_ok"] == ["polymarket"]
    monkeypatch.setattr(p, "_polymarket", fail)
    with pytest.raises(p.ProbabilityError, match="两个"):
        p.macro_probability(NOW)


def test_events_routes_in_main_app(monkeypatch):
    from fastapi.testclient import TestClient
    import server

    calls = []
    payload = {"items": [], "updated": "", "partial": False, "warnings": [], "how_to_read": []}
    monkeypatch.setattr(p, "get_probability", lambda force=False: calls.append(force) or payload)
    monkeypatch.setattr(server, "_VR_API_KEY", "")
    client = TestClient(server.app, base_url="http://localhost")
    assert client.get("/api/radar/events").json() == {"data": payload}
    assert client.post("/api/radar/events/refresh").json() == {"data": payload}
    assert calls == [False, True]
    assert client.post("/api/radar/events/refresh", headers={"Origin": "https://evil.example"}).status_code == 403
    assert calls == [False, True]
    monkeypatch.setattr(server, "_VR_API_KEY", "test-key")
    assert client.get("/api/radar/events").status_code == 401
    assert client.get("/api/radar/events", headers={"Authorization": "Bearer test-key"}).status_code == 200
    monkeypatch.setattr(server, "_VR_API_KEY", "")
    def fail(force=False):
        raise p.ProbabilityError("offline")
    monkeypatch.setattr(p, "get_probability", fail)
    response = client.post("/api/radar/events/refresh")
    assert response.status_code == 502 and "offline" in response.json()["detail"]
