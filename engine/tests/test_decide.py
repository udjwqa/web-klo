import asyncio
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///" + str(Path("/tmp/webklo-test.db"))
os.environ["ENGINE_SECRET"] = "test-secret"
os.environ["ADMIN_PASSWORD"] = "test-admin"
os.environ["PANEL_USER"] = "tester"
os.environ["PANEL_HOST"] = "klo.local"
os.environ["PANEL_PATH"] = "test-entry"
os.environ["IPQS_API_KEY"] = ""
os.environ["IPINFO_TOKEN"] = ""

from fastapi.testclient import TestClient

import auth
import settings
from app import app

settings.ENGINE_SECRET = "test-secret"
auth.ENGINE_SECRET = "test-secret"


def test_payment_from_offer_host_counts_once():
    import asyncio
    from store import stats as read_stats

    async def read():
        return await read_stats(campaign="demo", span="today")

    with TestClient(app) as client:
        before = asyncio.run(read())
        ip = "198.51.100." + str(20 + (os.getpid() % 200))
        first = client.get("/v1/pay", params={"source": "example.com"}, headers={"CF-Connecting-IP": ip})
        second = client.get("/v1/pay", params={"source": "example.com"}, headers={"CF-Connecting-IP": ip})
        assert first.status_code == 204
        assert second.status_code == 204
        after = asyncio.run(read())
        assert after["uniqueOffer"] == before["uniqueOffer"] + 1
        assert after["grey"] == before["grey"]
        assert after["total"] == before["total"]


def test_homepage_without_query_is_accepted():
    with TestClient(app) as client:
        res = client.post(
            "/v1/decide",
            headers={"X-Klo-Key": "test-secret"},
            json={
                "host": "localhost",
                "ip": "203.0.113.80",
                "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
                "headers": {"cf-ipcountry": "US", "cf-asn": "", "referer": ""},
                "accept_language": "en-US,en;q=0.9",
                "query": [],
                "path": "/",
            },
        )
        assert res.status_code == 200
        body = res.json()
        assert body["verdict"] == "grey"
        assert body["action"] == "redirect_offer"
        assert body["reason"] == "ok"
        assert body["url"].startswith("https://localhost/go")
        assert "example.com/offer" not in (body.get("url") or "")


def test_homepage_with_fbclid_goes_grey():
    with TestClient(app) as client:
        res = client.post(
            "/v1/decide",
            headers={"X-Klo-Key": "test-secret"},
            json={
                "host": "localhost",
                "ip": "203.0.113.81",
                "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
                "headers": {"cf-ipcountry": "US", "cf-asn": "", "referer": "https://l.facebook.com/"},
                "accept_language": "en-US,en;q=0.9",
                "query": {"fbclid": "IwAR0test"},
                "path": "/",
            },
        )
        assert res.status_code == 200
        body = res.json()
        assert body["verdict"] == "grey"
        assert body["action"] == "redirect_offer"
        assert body["url"].startswith("https://localhost/go")
        assert "fbclid=IwAR0test" in body["url"]
        assert "klo=" not in body["url"]
        assert "example.com/offer" not in body["url"]


def test_health_is_hidden():
    with TestClient(app) as client:
        res = client.get("/health")
        assert res.status_code == 404
        assert "nginx" in res.text
        by_ip = client.get("/admin", headers={"Host": "127.0.0.1:8088"})
        assert by_ip.status_code == 404
        docs = client.get("/docs", headers={"Host": "klo.local"})
        assert docs.status_code == 404


def test_decide_requires_key():
    with TestClient(app) as client:
        res = client.post("/v1/decide", json={"host": "localhost"})
        assert res.status_code == 404


def test_decide_demo_geo_and_bot():
    with TestClient(app) as client:
        bot = client.post(
            "/v1/decide",
            headers={"X-Klo-Key": "test-secret"},
            json={
                "host": "localhost",
                "ip": "203.0.113.10",
                "user_agent": "Googlebot/2.1",
                "headers": {"cf-ipcountry": "US"},
            },
        )
        assert bot.status_code == 200
        assert bot.json()["verdict"] == "white"
        assert bot.json()["action"] == "show_white"
        assert "/go" not in (bot.json().get("url") or "")
        assert "example.com/offer" not in (bot.json().get("url") or "")

        human = client.post(
            "/v1/decide",
            headers={"X-Klo-Key": "test-secret"},
            json={
                "host": "localhost",
                "ip": "203.0.113.11",
                "user_agent": "Mozilla/5.0 (Linux; Android 14) Chrome/120.0.0.0 Mobile Safari/537.36",
                "headers": {"cf-ipcountry": "US"},
                "accept_language": "en-US",
                "query": {"utm_source": "fb", "fbclid": "IwAR0test"},
            },
        )
        assert human.status_code == 200
        body = human.json()
        assert body["verdict"] == "grey"
        if body["verdict"] == "grey":
            assert "utm_source=fb" in body["url"]
            assert "klo=" not in body["url"]
            import asyncio
            from store import stats as read_stats

            async def _read():
                return await read_stats(campaign=body["campaign"], span="today")

            before = asyncio.run(_read())
            ip = "203.0.113." + str(20 + (os.getpid() % 200))
            pay = client.get("/v1/pay", params={"klo": body["request_id"]}, headers={"CF-Connecting-IP": ip})
            assert pay.status_code == 204
            again = client.get("/v1/pay", params={"klo": body["request_id"]}, headers={"CF-Connecting-IP": ip})
            assert again.status_code == 204
            missed = client.get("/v1/pay", params={"klo": "missing"})
            assert missed.status_code == 204
            other = client.post(
                "/v1/decide",
                headers={"X-Klo-Key": "test-secret"},
                json={
                    "host": "localhost",
                    "ip": "203.0.113.12",
                        "user_agent": "Mozilla/5.0 (Linux; Android 14) Chrome/120.0.0.0 Mobile Safari/537.36",
                        "headers": {"cf-ipcountry": "US"},
                        "accept_language": "en-US",
                        "query": {"fbclid": "IwAR0other"},
                    },
                )
            assert other.status_code == 200
            after = asyncio.run(_read())
            assert after["grey"] == before["grey"] + 1
            assert after["uniqueOffer"] == before["uniqueOffer"] + 1
            assert after["total"] == after["grey"] + after["white"]


US_CHROME = {
    "host": "localhost",
    "ip": "203.0.113.82",
    "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "headers": {"cf-ipcountry": "US", "cf-asn": "", "referer": ""},
    "accept_language": "en-US,en;q=0.9",
    "query": [],
    "path": "/",
}


def _set_demo_panic(value: bool) -> None:
    import asyncio
    from store import list_campaigns, set_panic

    async def go():
        rows = await list_campaigns()
        demo = next(row for row in rows if row.slug == "demo")
        await set_panic(demo.id, value)

    asyncio.run(go())


def test_ads_review_panic_keeps_us_chrome_on_white():
    with TestClient(app) as client:
        _set_demo_panic(True)
        try:
            res = client.post(
                "/v1/decide",
                headers={"X-Klo-Key": "test-secret"},
                json=US_CHROME,
            )
            assert res.status_code == 200
            body = res.json()
            assert body["verdict"] == "white"
            assert body["reason"] == "panic"
            assert body["action"] == "show_white"
            assert body["action"] != "redirect_offer"
            assert "example.com/offer" not in (body.get("url") or "")
        finally:
            _set_demo_panic(False)


def test_ads_review_off_us_chrome_goes_grey():
    with TestClient(app) as client:
        _set_demo_panic(False)
        res = client.post(
            "/v1/decide",
            headers={"X-Klo-Key": "test-secret"},
            json={**US_CHROME, "ip": "203.0.113.83"},
        )
        assert res.status_code == 200
        body = res.json()
        assert body["verdict"] == "grey"
        assert body["action"] == "redirect_offer"
        assert body["reason"] == "ok"


def test_ads_review_flag_mirrors_panic_in_admin_api():
    panel = {
        "Host": settings.PANEL_HOST,
        "Cookie": "klo_admin=" + auth.sign_admin(),
    }
    with TestClient(app) as client:
        rows = client.get("/admin/api/campaigns", headers=panel).json()
        demo = next(row for row in rows if row["slug"] == "demo")
        assert demo["panic"] is False
        assert demo["ads_review"] is False
        try:
            flipped = client.post(
                "/admin/api/campaigns/" + demo["id"] + "/panic",
                headers=panel,
                json={"panic": True},
            )
            assert flipped.status_code == 200
            assert flipped.json()["panic"] is True
            assert flipped.json()["ads_review"] is True
            rows = client.get("/admin/api/campaigns", headers=panel).json()
            demo = next(row for row in rows if row["slug"] == "demo")
            assert demo["panic"] is True
            assert demo["ads_review"] is True
        finally:
            client.post(
                "/admin/api/campaigns/" + demo["id"] + "/panic",
                headers=panel,
                json={"panic": False},
            )


def _chrome(ip: str, asn: str = "") -> dict:
    return {
        **US_CHROME,
        "ip": ip,
        "headers": {"cf-ipcountry": "US", "cf-asn": asn, "referer": ""},
    }


def test_googlebot_then_us_chrome_is_review_burst():
    from burst import burst_window
    from store import unban_ip

    burst_window.clear()
    with TestClient(app) as client:
        asyncio.run(unban_ip("198.51.100.10"))
        asyncio.run(unban_ip("203.0.113.40"))
        bot = client.post(
            "/v1/decide",
            headers={"X-Klo-Key": "test-secret"},
            json={
                "host": "localhost",
                "ip": "198.51.100.10",
                "user_agent": "Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)",
                "headers": {"cf-ipcountry": "US", "cf-asn": "15169"},
                "accept_language": "en-US",
                "query": [],
                "path": "/",
            },
        )
        assert bot.status_code == 200
        assert bot.json()["verdict"] == "white"
        human = client.post(
            "/v1/decide",
            headers={"X-Klo-Key": "test-secret"},
            json=_chrome("203.0.113.40", "7922"),
        )
        assert human.status_code == 200
        body = human.json()
        assert body["verdict"] == "white"
        assert body["reason"] == "review_burst"
        assert body["action"] == "show_white"
        assert body["action"] != "redirect_offer"


def test_single_comcast_without_bot_stays_grey():
    from burst import burst_window
    from store import unban_ip

    burst_window.clear()
    with TestClient(app) as client:
        asyncio.run(unban_ip("203.0.113.41"))
        res = client.post(
            "/v1/decide",
            headers={"X-Klo-Key": "test-secret"},
            json=_chrome("203.0.113.41", "7922"),
        )
        assert res.status_code == 200
        body = res.json()
        assert body["verdict"] == "grey"
        assert body["reason"] != "review_burst"
        assert body["action"] == "redirect_offer"


def test_same_asn_many_slash24s_stay_grey():
    from burst import burst_window

    burst_window.clear()
    ips = ("203.0.113.50", "198.18.10.50", "198.18.11.50", "198.18.11.51", "198.18.10.51")
    with TestClient(app) as client:
        from store import unban_ip

        for ip in ips:
            asyncio.run(unban_ip(ip))
        last = None
        for ip in ips:
            last = client.post(
                "/v1/decide",
                headers={"X-Klo-Key": "test-secret"},
                json=_chrome(ip, "7922"),
            )
            assert last.status_code == 200
            body = last.json()
            assert body["verdict"] == "grey"
            assert body["reason"] != "review_burst"


def test_us_chrome_homepage_goes_to_same_host_go():
    with TestClient(app) as client:
        res = client.post(
            "/v1/decide",
            headers={"X-Klo-Key": "test-secret"},
            json={**US_CHROME, "ip": "203.0.113.84", "path": "/"},
        )
        assert res.status_code == 200
        body = res.json()
        assert body["verdict"] == "grey"
        assert body["action"] == "redirect_offer"
        assert body["url"].startswith("https://localhost/go")
        assert "example.com/offer" not in body["url"]
        assert "go.localhost" not in body["url"]


def test_go_path_shows_preland_with_offer_query():
    with TestClient(app) as client:
        res = client.post(
            "/v1/decide",
            headers={"X-Klo-Key": "test-secret"},
            json={
                **US_CHROME,
                "ip": "203.0.113.85",
                "path": "/go",
                "query": {"utm_source": "fb", "fbclid": "IwAR0go"},
            },
        )
        assert res.status_code == 200
        body = res.json()
        assert body["verdict"] == "grey"
        assert body["action"] == "show_preland"
        assert body["url"].startswith("https://example.com/offer")
        assert "utm_source=fb" in body["url"]
        assert "fbclid=IwAR0go" in body["url"]
        assert "klo=" not in body["url"]


def test_googlebot_on_go_stays_white():
    with TestClient(app) as client:
        res = client.post(
            "/v1/decide",
            headers={"X-Klo-Key": "test-secret"},
            json={
                "host": "localhost",
                "ip": "198.51.100.11",
                "user_agent": "Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)",
                "headers": {"cf-ipcountry": "US"},
                "path": "/go",
            },
        )
        assert res.status_code == 200
        body = res.json()
        assert body["verdict"] == "white"
        assert body["action"] == "show_white"
        assert body["action"] != "show_preland"
        assert "example.com/offer" not in (body.get("url") or "")


def test_dropin_preland_contract():
    root = Path(__file__).resolve().parents[2]
    php = (root / "dropin" / "index.php").read_text(encoding="utf-8")
    html = (root / "dropin" / "go.html").read_text(encoding="utf-8")
    assert "show_preland" in php
    assert "go.html" in php
    assert "OFFER_URL" in html
    assert "Location" in php
