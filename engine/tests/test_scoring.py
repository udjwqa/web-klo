import asyncio
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite://")

from ipinfo import IPInfoResult, ipinfo_client
from lists import lists
from scoring import scoring


def setup_module():
    lists.load()


def run(coro):
    return asyncio.run(coro)


def test_bot_ua_is_white():
    result = run(scoring.score(
        ip="8.8.8.8",
        user_agent="Mozilla/5.0 (compatible; Googlebot/2.1)",
        country_hint="US",
        geos=["US"],
        threshold=70,
    ))
    assert result.verdict == "white"
    assert result.score >= 70


def test_direct_visit_without_click_id_is_grey():
    result = run(scoring.score(
        ip="1.2.3.4",
        user_agent="Mozilla/5.0 (Linux; Android 14) Chrome/120.0.0.0 Mobile Safari/537.36",
        country_hint="US",
        geos=["US"],
        threshold=70,
        accept_language="en-US",
    ))
    assert result.verdict == "grey"
    assert all(d.check != "click_id" for d in result.details)


def test_stale_click_id_hard_is_ignored():
    result = run(scoring.score(
        ip="1.2.3.4",
        user_agent="Mozilla/5.0 (Linux; Android 14) Chrome/120.0.0.0 Mobile Safari/537.36",
        country_hint="US",
        geos=["US"],
        threshold=70,
        accept_language="en-US",
        filters={"click_id": {"mode": "hard"}},
    ))
    assert result.verdict == "grey"
    assert all(d.check != "click_id" for d in result.details)


def test_empty_accept_language_is_white():
    result = run(scoring.score(
        ip="1.2.3.4",
        user_agent="Mozilla/5.0 (Linux; Android 14) Chrome/120.0.0.0 Mobile Safari/537.36",
        country_hint="US",
        geos=["US"],
        threshold=70,
        query={"fbclid": "IwAR0test"},
    ))
    assert result.verdict == "white"
    assert result.reason == "empty_lang"


def test_hosting_org_is_flagged():
    hetzner = IPInfoResult({"org": "AS24940 Hetzner Online GmbH", "country": "DE", "privacy": {}})
    tencent = IPInfoResult({"org": "AS132203 Tencent Building, Kejizhongyi Avenue", "country": "US", "privacy": {}})
    comcast = IPInfoResult({"org": "AS7922 Comcast Cable Communications", "country": "US", "privacy": {}})
    att = IPInfoResult({"org": "AS7018 AT&T Enterprises, LLC", "country": "US", "privacy": {}})
    assert hetzner.hosting is True
    assert tencent.hosting is True
    assert comcast.hosting is False
    assert att.hosting is False


def test_empty_lang_off_allows():
    result = run(scoring.score(
        ip="1.2.3.4",
        user_agent="Mozilla/5.0 (Linux; Android 14) Chrome/120.0.0.0 Mobile Safari/537.36",
        country_hint="US",
        geos=["US"],
        threshold=70,
        query={"fbclid": "IwAR0test"},
        filters={"empty_lang": {"mode": "off"}},
    ))
    assert result.verdict == "grey"


def test_fbclid_passes_when_clean():
    result = run(scoring.score(
        ip="1.2.3.4",
        user_agent="Mozilla/5.0 (Linux; Android 14) Chrome/120.0.0.0 Mobile Safari/537.36",
        country_hint="US",
        geos=["US"],
        threshold=70,
        accept_language="en-US,en;q=0.9",
        query={"fbclid": "IwAR0test"},
    ))
    assert result.verdict == "grey"
    assert all(d.check != "click_id" for d in result.details)


def test_in_app_facebook_is_not_bot():
    result = run(scoring.score(
        ip="1.2.3.4",
        user_agent="Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148 [FBAN/FBIOS;FBAV/1.0]",
        country_hint="US",
        geos=["US"],
        threshold=70,
        accept_language="en-US",
        query={"fbclid": "IwAR0test"},
    ))
    assert result.verdict == "grey"
    assert all(d.check != "bot_ua" for d in result.details)


def test_geo_miss_is_white():
    result = run(scoring.score(
        ip="1.2.3.4",
        user_agent="Mozilla/5.0 (Linux; Android 14) Chrome/120.0.0.0 Mobile Safari/537.36",
        country_hint="DE",
        geos=["US"],
        threshold=70,
    ))
    assert result.verdict == "white"
    assert result.reason == "geo_miss"


def test_desktop_is_not_cut():
    result = run(scoring.score(
        ip="1.2.3.4",
        user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) Chrome/120.0.0.0",
        country_hint="US",
        geos=["US"],
        threshold=70,
        accept_language="en-US",
        query={"fbclid": "1"},
    ))
    assert result.verdict == "grey"
    assert all(item.check != "desktop_ua" for item in result.details)


def test_allowlist_passes_bot():
    result = run(scoring.score(
        ip="1.2.3.4",
        user_agent="Mozilla/5.0 (compatible; Googlebot/2.1)",
        country_hint="DE",
        geos=["US"],
        allowed=True,
    ))
    assert result.verdict == "grey"
    assert result.reason == "allowlist"


def test_ban_beats_allowlist():
    result = run(scoring.score(
        ip="1.2.3.4",
        user_agent="Mozilla/5.0 (Linux; Android 14) Chrome/120.0.0.0 Mobile",
        country_hint="US",
        geos=["US"],
        banned=True,
        allowed=True,
    ))
    assert result.verdict == "white"
    assert result.reason == "banned"


def test_banned_tencent_is_white_without_ipinfo(monkeypatch):
    async def boom(ip):
        raise AssertionError("ipinfo must not run for banned IP")

    monkeypatch.setattr(ipinfo_client, "lookup", boom)
    result = run(scoring.score(
        ip="203.0.113.88",
        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
        country_hint="US",
        geos=["US"],
        threshold=100,
        accept_language="en-US",
        banned=True,
    ))
    assert result.verdict == "white"
    assert result.reason == "banned"


def test_googlebot_stays_cut_even_if_old_toggle_off():
    result = run(scoring.score(
        ip="1.2.3.4",
        user_agent="Mozilla/5.0 (compatible; Googlebot/2.1)",
        country_hint="US",
        geos=["US"],
        threshold=70,
        filters={"bots": False},
    ))
    assert result.verdict == "white"


def test_vpn_asn_hard_cuts_and_off_does_not():
    hard = run(scoring.score(
        ip="1.2.3.4",
        user_agent="Mozilla/5.0 (Linux; Android 14) Chrome/120.0.0.0 Mobile",
        country_hint="US",
        geos=["US"],
        asn_hint="9009",
        filters={"vpn": {"mode": "hard", "points": 25}},
    ))
    assert hard.verdict == "white"
    assert hard.reason == "vpn"
    soft = run(scoring.score(
        ip="1.2.3.4",
        user_agent="Mozilla/5.0 (Linux; Android 14) Chrome/120.0.0.0 Mobile",
        country_hint="US",
        geos=["US"],
        asn_hint="9009",
        accept_language="en-US",
        query={"gclid": "abc"},
        filters={"vpn": {"mode": "off"}},
    ))
    assert soft.verdict == "grey"


def test_ads_cabinet_referer_is_white_and_facebook_click_is_not():
    cabinet = run(scoring.score(
        ip="1.2.3.4",
        user_agent="Mozilla/5.0 (Linux; Android 14) Chrome/120.0.0.0 Mobile",
        country_hint="US",
        geos=["US"],
        referer="https://ads.google.com/aw/overview",
    ))
    assert cabinet.verdict == "white"
    assert cabinet.reason == "ads_referer"
    click = run(scoring.score(
        ip="1.2.3.4",
        user_agent="Mozilla/5.0 (Linux; Android 14) Chrome/120.0.0.0 Mobile",
        country_hint="US",
        geos=["US"],
        referer="https://l.facebook.com/l.php",
        accept_language="en-US",
        query={"fbclid": "IwAR0test"},
    ))
    assert click.verdict == "grey"


def test_plain_http_referer_is_white_and_ad_http_is_not():
    scanner = run(scoring.score(
        ip="1.2.3.4",
        user_agent="Mozilla/5.0 (Linux; Android 14) Chrome/120.0.0.0 Mobile",
        country_hint="US",
        geos=["US"],
        accept_language="en-US",
        referer="http://scanner.example/check",
    ))
    assert scanner.verdict == "white"
    assert scanner.reason == "http_referer"
    ad = run(scoring.score(
        ip="1.2.3.4",
        user_agent="Mozilla/5.0 (Linux; Android 14) Chrome/120.0.0.0 Mobile",
        country_hint="US",
        geos=["US"],
        accept_language="en-US",
        referer="http://l.facebook.com/l.php",
    ))
    assert ad.verdict == "grey"
    direct = run(scoring.score(
        ip="1.2.3.4",
        user_agent="Mozilla/5.0 (Linux; Android 14) Chrome/120.0.0.0 Mobile",
        country_hint="US",
        geos=["US"],
        accept_language="en-US",
        referer="https://example.com/page",
    ))
    assert direct.verdict == "grey"


def test_language_points_only_when_enabled():
    missed = run(scoring.score(
        ip="1.2.3.4",
        user_agent="Mozilla/5.0 (Linux; Android 14) Chrome/120.0.0.0 Mobile",
        country_hint="US",
        geos=["US"],
        accept_language="ru-RU,ru;q=0.9",
        threshold=70,
        query={"fbclid": "1"},
        filters={"language": {"mode": "points", "points": 80, "langs": ["en", "es"]}},
    ))
    assert missed.verdict == "white"
    assert missed.reason == "language"
    skipped = run(scoring.score(
        ip="1.2.3.4",
        user_agent="Mozilla/5.0 (Linux; Android 14) Chrome/120.0.0.0 Mobile",
        country_hint="US",
        geos=["US"],
        accept_language="ru-RU",
        query={"gclid": "abc"},
        filters={"language": {"mode": "off", "points": 80, "langs": ["en"]}},
    ))
    assert skipped.verdict == "grey"


def test_clean_mobile_passes():
    result = run(scoring.score(
        ip="1.2.3.4",
        user_agent="Mozilla/5.0 (Linux; Android 14; Pixel 7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36",
        country_hint="US",
        geos=["US"],
        threshold=70,
        accept_language="en-US,en;q=0.9",
        query={"fbclid": "IwAR0test"},
    ))
    assert result.verdict == "grey"
    assert result.score < 70


def test_white_before_ipinfo_does_not_lookup(monkeypatch):
    async def fail_lookup(ip):
        raise AssertionError(ip)

    monkeypatch.setattr(ipinfo_client, "lookup", fail_lookup)
    bot = run(scoring.score(
        ip="8.8.8.8",
        user_agent="Mozilla/5.0 (compatible; Googlebot/2.1)",
        country_hint="US",
        geos=["US"],
        threshold=100,
        accept_language="en-US",
    ))
    assert bot.verdict == "white"
    abroad = run(scoring.score(
        ip="1.2.3.4",
        user_agent="Mozilla/5.0 (Linux; Android 14) Chrome/120.0.0.0 Mobile Safari/537.36",
        country_hint="DE",
        geos=["US"],
        threshold=100,
        accept_language="en-US",
    ))
    assert abroad.reason == "geo_miss"


def test_possible_offer_asks_ipinfo_and_hosting_stays_white(monkeypatch):
    seen = []

    async def hosting(ip):
        seen.append(ip)
        return IPInfoResult({"org": "AS24940 Hetzner Online GmbH", "country": "US", "privacy": {}})

    monkeypatch.setattr(ipinfo_client, "lookup", hosting)
    result = run(scoring.score(
        ip="203.0.113.77",
        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
        country_hint="US",
        geos=["US"],
        threshold=100,
        accept_language="en-US",
    ))
    assert seen == ["203.0.113.77"]
    assert result.verdict == "white"
    assert result.reason == "hosting"


CLEAN_CHROME = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"


def test_tencent_org_is_white_via_ipinfo(monkeypatch):
    seen = []

    async def tencent_lookup(ip):
        seen.append(ip)
        return IPInfoResult({
            "org": "AS132203 Tencent Building, Kejizhongyi Avenue",
            "country": "US",
            "privacy": {},
        })

    monkeypatch.setattr(ipinfo_client, "lookup", tencent_lookup)
    result = run(scoring.score(
        ip="203.0.113.88",
        user_agent=CLEAN_CHROME,
        country_hint="US",
        geos=["US"],
        threshold=100,
        accept_language="en-US",
    ))
    assert seen == ["203.0.113.88"]
    assert result.verdict == "white"
    assert result.reason == "hosting"


def test_comcast_and_att_org_stay_grey(monkeypatch):
    async def comcast_lookup(ip):
        return IPInfoResult({
            "org": "AS7922 Comcast Cable Communications, LLC",
            "country": "US",
            "privacy": {},
        })

    monkeypatch.setattr(ipinfo_client, "lookup", comcast_lookup)
    comcast = run(scoring.score(
        ip="203.0.113.89",
        user_agent=CLEAN_CHROME,
        country_hint="US",
        geos=["US"],
        threshold=100,
        accept_language="en-US",
    ))
    assert comcast.verdict == "grey"
    assert comcast.reason == "ok"

    async def att_lookup(ip):
        return IPInfoResult({
            "org": "AS7018 AT&T Enterprises, LLC",
            "country": "US",
            "privacy": {},
        })

    monkeypatch.setattr(ipinfo_client, "lookup", att_lookup)
    att = run(scoring.score(
        ip="203.0.113.90",
        user_agent=CLEAN_CHROME,
        country_hint="US",
        geos=["US"],
        threshold=100,
        accept_language="en-US",
    ))
    assert att.verdict == "grey"
    assert att.reason == "ok"


def test_tencent_and_alibaba_asn_hint_is_white_without_ipinfo(monkeypatch):
    async def fail_lookup(ip):
        raise AssertionError("ipinfo must not run after asn_block")

    monkeypatch.setattr(ipinfo_client, "lookup", fail_lookup)
    tencent = run(scoring.score(
        ip="203.0.113.91",
        user_agent=CLEAN_CHROME,
        country_hint="US",
        geos=["US"],
        threshold=100,
        accept_language="en-US",
        asn_hint="132203",
    ))
    assert tencent.verdict == "white"
    assert tencent.reason == "asn_blocked"

    alibaba = run(scoring.score(
        ip="203.0.113.92",
        user_agent=CLEAN_CHROME,
        country_hint="US",
        geos=["US"],
        threshold=100,
        accept_language="en-US",
        asn_hint="45102",
    ))
    assert alibaba.verdict == "white"
    assert alibaba.reason == "asn_blocked"
