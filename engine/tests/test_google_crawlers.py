import asyncio
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite://")

from google_crawlers import google_crawlers
from lists import lists
from scoring import scoring

CLEAN_CHROME = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)
FIXTURE_IP = "198.51.100.10"
COMCAST_IP = "203.0.113.40"


def setup_module():
    lists.load()


def setup_function():
    google_crawlers.load_prefixes(["198.51.100.0/24"])


def run(coro):
    return asyncio.run(coro)


def test_special_crawler_ip_chrome_ua_is_white():
    result = run(scoring.score(
        ip=FIXTURE_IP,
        user_agent=CLEAN_CHROME,
        country_hint="US",
        geos=["US"],
        threshold=100,
        accept_language="en-US,en;q=0.9",
    ))
    assert result.verdict == "white"
    assert result.reason == "google_crawler"


def test_comcast_ip_is_not_google_crawler():
    result = run(scoring.score(
        ip=COMCAST_IP,
        user_agent=CLEAN_CHROME,
        country_hint="US",
        geos=["US"],
        threshold=100,
        accept_language="en-US,en;q=0.9",
    ))
    assert result.reason != "google_crawler"
    assert result.verdict == "grey"


def test_fake_adsbot_ua_without_google_ip_is_not_google_crawler():
    result = run(scoring.score(
        ip=COMCAST_IP,
        user_agent="AdsBot-Google (+http://www.google.com/adsbot.html)",
        country_hint="US",
        geos=["US"],
        threshold=100,
        accept_language="en-US",
    ))
    assert result.reason != "google_crawler"
    assert result.verdict == "white"
    assert result.reason == "bot_user_agent"


def test_googlebot_ua_still_white():
    result = run(scoring.score(
        ip=COMCAST_IP,
        user_agent="Mozilla/5.0 (compatible; Googlebot/2.1)",
        country_hint="US",
        geos=["US"],
        threshold=100,
        accept_language="en-US",
    ))
    assert result.verdict == "white"
    assert result.reason in {"bot_user_agent", "google_crawler"}


def test_refresh_failure_keeps_cache(tmp_path, monkeypatch):
    cache = tmp_path / "google_crawlers_cache.json"
    cache.write_text(json.dumps({
        "updated": 0,
        "prefixes": ["198.51.100.0/24"],
    }), encoding="utf-8")
    monkeypatch.setattr(google_crawlers, "_cache_path", lambda: cache)

    def boom(url):
        raise RuntimeError("network down")

    monkeypatch.setattr(google_crawlers, "_fetch_json", boom)
    google_crawlers.load(force_refresh=True)
    assert google_crawlers.is_crawler(FIXTURE_IP) is True
    assert google_crawlers.is_crawler(COMCAST_IP) is False


def test_refresh_failure_without_cache_does_not_raise(tmp_path, monkeypatch):
    cache = tmp_path / "missing.json"
    monkeypatch.setattr(google_crawlers, "_cache_path", lambda: cache)

    def boom(url):
        raise RuntimeError("network down")

    monkeypatch.setattr(google_crawlers, "_fetch_json", boom)
    google_crawlers.load(force_refresh=True)
    assert google_crawlers.is_crawler(FIXTURE_IP) is False
