import asyncio
import os
import sys
from datetime import timedelta
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
from models import utcnow

settings.ENGINE_SECRET = "test-secret"
auth.ENGINE_SECRET = "test-secret"

CLEAN_CHROME = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)
PANEL = {
    "Host": settings.PANEL_HOST,
    "Cookie": "klo_admin=" + auth.sign_admin(),
}


def _chrome(ip: str) -> dict:
    return {
        "host": "localhost",
        "ip": ip,
        "user_agent": CLEAN_CHROME,
        "headers": {"cf-ipcountry": "US", "cf-asn": "7922", "referer": ""},
        "accept_language": "en-US,en;q=0.9",
        "query": [],
        "path": "/",
    }


def test_review_burst_ip_banned_on_repeat_without_ipinfo(monkeypatch):
    from burst import burst_window
    from ipinfo import ipinfo_client
    from store import is_banned, unban_ip

    burst_window.clear()
    seen = []

    async def track(ip):
        seen.append(ip)
        return None

    monkeypatch.setattr(ipinfo_client, "lookup", track)
    ip = "203.0.113.210"
    with TestClient(app) as client:
        asyncio.run(unban_ip(ip))
        asyncio.run(unban_ip("198.51.100.210"))
        bot = client.post(
            "/v1/decide",
            headers={"X-Klo-Key": "test-secret"},
            json={
                "host": "localhost",
                "ip": "198.51.100.210",
                "user_agent": "Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)",
                "headers": {"cf-ipcountry": "US", "cf-asn": "15169"},
                "accept_language": "en-US",
                "query": [],
                "path": "/",
            },
        )
        assert bot.status_code == 200
        assert bot.json()["verdict"] == "white"
        first = client.post("/v1/decide", headers={"X-Klo-Key": "test-secret"}, json=_chrome(ip))
        assert first.status_code == 200
        assert first.json()["reason"] == "review_burst"
        assert asyncio.run(is_banned(ip)) is True
        seen.clear()
        again = client.post("/v1/decide", headers={"X-Klo-Key": "test-secret"}, json=_chrome(ip))
        assert again.status_code == 200
        body = again.json()
        assert body["verdict"] == "white"
        assert body["reason"] == "banned"
        assert seen == []
    asyncio.run(unban_ip(ip))
    asyncio.run(unban_ip("198.51.100.210"))


def test_slash24_ban_matches_host_and_syncs():
    from store import apply_snapshot, build_snapshot, is_banned, unban_ip

    net = "198.18.200.0/24"
    host = "198.18.200.77"
    with TestClient(app) as client:
        asyncio.run(unban_ip(net))
        asyncio.run(unban_ip(host))
        asyncio.run(unban_ip("198.18.200.77/24"))
        asyncio.run(unban_ip("192.0.2.0/24"))
        asyncio.run(unban_ip("192.0.2.77/24"))
        added = client.post(
            "/admin/api/bans",
            headers=PANEL,
            json={"ip": "198.18.200.77/24", "reason": "reviewer /24", "source": "reviewer"},
        )
        assert added.status_code == 200
        rows = client.get("/admin/api/bans", headers=PANEL).json()
        match = next(row for row in rows if row["ip"] == net)
        assert match["source"] == "reviewer"
        assert match.get("expires_at")
        assert asyncio.run(is_banned(host)) is True
        assert asyncio.run(is_banned("203.0.113.77")) is False
        snap = asyncio.run(build_snapshot())
        banned = [row for row in snap["banned"] if row["ip"] == net]
        assert banned and banned[0]["source"] == "reviewer"
        assert banned[0].get("expires_at")
        asyncio.run(unban_ip(net))
        assert asyncio.run(is_banned(host)) is False
        asyncio.run(apply_snapshot({"campaigns": snap["campaigns"], "banned": snap["banned"], "allowed": snap["allowed"], "settings": snap["settings"], "lists": {}}))
        assert asyncio.run(is_banned(host)) is True
    asyncio.run(unban_ip(net))


def test_expired_reviewer_ban_does_not_match():
    from store import ban_ip, is_banned, unban_ip

    ip = "203.0.113.211"
    with TestClient(app):
        asyncio.run(unban_ip(ip))
        asyncio.run(ban_ip(ip, "review_burst", source="reviewer", expires_at=utcnow() - timedelta(days=1)))
        assert asyncio.run(is_banned(ip)) is False
        asyncio.run(unban_ip(ip))


def test_import_tencent_grey_skips_comcast():
    from datetime import datetime
    from reviewers import import_reviewers_from_logs
    from store import MSK, is_banned, log_request, unban_ip

    tencent_ip = "203.0.113.220"
    comcast_ip = "203.0.113.221"
    day = datetime.now(MSK).strftime("%Y-%m-%d")
    with TestClient(app) as client:
        asyncio.run(unban_ip(tencent_ip))
        asyncio.run(unban_ip(comcast_ip))
        asyncio.run(log_request(
            campaign="demo",
            ip=tencent_ip,
            country="US",
            isp="AS132203 Tencent Building, Kejizhongyi Avenue",
            user_agent=CLEAN_CHROME,
            verdict="grey",
            reason="ok",
        ))
        asyncio.run(log_request(
            campaign="demo",
            ip=comcast_ip,
            country="US",
            isp="AS7922 Comcast Cable Communications, LLC",
            user_agent=CLEAN_CHROME,
            verdict="grey",
            reason="ok",
        ))
        result = asyncio.run(import_reviewers_from_logs(campaign="demo", date_from=day, date_to=day))
        assert result["added"] >= 1
        assert result["skipped_safe"] >= 1
        assert asyncio.run(is_banned(tencent_ip)) is True
        assert asyncio.run(is_banned(comcast_ip)) is False
        posted = client.post(
            "/admin/api/reviewers/import",
            headers=PANEL,
            json={"campaign": "demo", "date": day},
        )
        assert posted.status_code == 200
        body = posted.json()
        assert "added" in body
        assert "skipped_safe" in body
    asyncio.run(unban_ip(tencent_ip))
    asyncio.run(unban_ip(comcast_ip))
