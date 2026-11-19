import asyncio
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite://")
os.environ["CLOAKER_API_URL"] = ""
os.environ["CLOAKER_API_KEY"] = ""
os.environ["CLOAKER_CAMPAIGN_ID"] = ""

from cloaker_api import parse_cloaker_payload
from ipinfo import IPInfoResult, ipinfo_client
from lists import lists
from scoring import scoring


def setup_module():
    lists.load()


def run(coro):
    return asyncio.run(coro)


CLEAN_CHROME = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)


def _score(**kwargs):
    payload = dict(
        ip="203.0.113.95",
        user_agent=CLEAN_CHROME,
        country_hint="US",
        geos=["US"],
        threshold=100,
        accept_language="en-US,en;q=0.9",
    )
    payload.update(kwargs)
    return run(scoring.score(**payload))


def test_parse_magicchecker_ban_is_white():
    assert parse_cloaker_payload({"success": 1, "ban": 1}) == "white"


def test_parse_adspect_safe_is_white():
    assert parse_cloaker_payload({"action": "safe"}) == "white"
    assert parse_cloaker_payload({"action": "ban"}) == "white"


def test_parse_real_is_grey():
    assert parse_cloaker_payload({"success": 1, "ban": 0}) == "grey"
    assert parse_cloaker_payload({"action": "real"}) == "grey"
    assert parse_cloaker_payload({"verdict": "ok"}) == "grey"


def test_parse_empty_or_garbage_is_white():
    assert parse_cloaker_payload({}) == "white"
    assert parse_cloaker_payload(None) == "white"
    assert parse_cloaker_payload("nope") == "white"


def test_api_ban_keeps_clean_chrome_on_white(monkeypatch):
    from cloaker_api import cloaker_client

    async def ban(**kwargs):
        return "white"

    monkeypatch.setattr(cloaker_client, "check", ban)
    result = _score()
    assert result.verdict == "white"
    assert result.reason == "cloaker_api"


def test_api_down_is_white_not_grey(monkeypatch):
    from cloaker_api import cloaker_client

    async def boom(**kwargs):
        raise RuntimeError("network down")

    monkeypatch.setattr(cloaker_client, "check", boom)
    result = _score()
    assert result.verdict == "white"
    assert result.reason == "cloaker_api"
    assert result.verdict != "grey"


def test_api_real_leaves_local_grey(monkeypatch):
    from cloaker_api import cloaker_client

    async def real(**kwargs):
        return "grey"

    monkeypatch.setattr(cloaker_client, "check", real)
    result = _score()
    assert result.verdict == "grey"
    assert result.reason == "ok"
    assert all(item.check != "cloaker_api" for item in result.details)


def test_api_real_does_not_cancel_local_hosting(monkeypatch):
    from cloaker_api import cloaker_client

    seen = []

    async def real(**kwargs):
        seen.append(kwargs)
        return "grey"

    async def tencent(ip):
        return IPInfoResult({
            "org": "AS132203 Tencent Building, Kejizhongyi Avenue",
            "country": "US",
            "privacy": {},
        })

    monkeypatch.setattr(cloaker_client, "check", real)
    monkeypatch.setattr(ipinfo_client, "lookup", tencent)
    result = _score(ip="203.0.113.88")
    assert result.verdict == "white"
    assert result.reason == "hosting"
    assert seen == []


def test_unconfigured_api_is_not_called(monkeypatch):
    from cloaker_api import cloaker_client

    async def boom(**kwargs):
        raise AssertionError("cloaker must stay off without URL")

    monkeypatch.setattr("cloaker_api.CLOAKER_API_URL", "")
    monkeypatch.setattr(cloaker_client, "check", cloaker_client.check)
    monkeypatch.setattr(cloaker_client, "_request", boom)
    result = _score(ip="203.0.113.96")
    assert result.verdict == "grey"
    assert result.reason == "ok"
