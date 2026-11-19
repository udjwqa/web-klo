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

import asyncio

import auth
import settings
from fastapi.testclient import TestClient
from app import app
from models import CampaignIn
from store import apply_snapshot, campaign_dict, get_campaign, upsert_campaign

settings.ENGINE_SECRET = "test-secret"
auth.ENGINE_SECRET = "test-secret"


def test_sync_requires_key():
    with TestClient(app) as client:
        res = client.get("/v1/sync")
        assert res.status_code == 404


def test_sync_returns_campaigns_and_lists():
    with TestClient(app) as client:
        res = client.get("/v1/sync", headers={"X-Klo-Key": "test-secret"})
        assert res.status_code == 200
        body = res.json()
        assert "campaigns" in body
        assert "lists" in body
        assert "ip_ranges" in body
        slugs = [item["slug"] for item in body["campaigns"]]
        assert "demo" in slugs


def test_ingest_is_idempotent():
    with TestClient(app) as client:
        payload = {
            "logs": [
                {
                    "id": "ing-1-" + str(os.getpid()),
                    "campaign": "demo",
                    "ip": "203.0.113.77",
                    "verdict": "white",
                    "reason": "edge-test",
                    "score": 100,
                }
            ]
        }
        first = client.post("/v1/ingest", headers={"X-Klo-Key": "test-secret"}, json=payload)
        second = client.post("/v1/ingest", headers={"X-Klo-Key": "test-secret"}, json=payload)
        assert first.status_code == 200
        assert first.json()["added"] == 1
        assert second.status_code == 200
        assert second.json()["added"] == 0


def test_bridge_url_used_for_grey():
    async def setup():
        await upsert_campaign(
            CampaignIn(
                slug="demo",
                name="Demo campaign",
                domain="localhost",
                offer_url="https://example.com/offer",
                bridge_url="https://go.localhost",
                geos=["US"],
                threshold=100,
                enabled=True,
            )
        )
        row = await get_campaign(slug="demo")
        assert campaign_dict(row)["bridge_url"] == "https://go.localhost"

    asyncio.run(setup())
    with TestClient(app) as client:
        res = client.post(
            "/v1/decide",
            headers={"X-Klo-Key": "test-secret"},
            json={
                "host": "localhost",
                "ip": "203.0.113.91",
                "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
                "headers": {"cf-ipcountry": "US"},
                "accept_language": "en-US",
                "query": {"fbclid": "IwAR0bridge"},
                "path": "/",
            },
        )
        assert res.status_code == 200
        body = res.json()
        assert body["verdict"] == "grey"
        assert body["url"].startswith("https://localhost/go")
        assert "fbclid=IwAR0bridge" in body["url"]
        assert "klo=" not in body["url"]
        assert "go.localhost" not in body["url"]
        assert "example.com/offer" not in body["url"]


def test_apply_snapshot_updates_bridge():
    async def run():
        await apply_snapshot(
            {
                "campaigns": [
                    {
                        "slug": "demo",
                        "name": "Demo campaign",
                        "domain": "localhost",
                        "offer_url": "https://example.com/offer",
                        "bridge_url": "https://go.example.test",
                        "geos": ["US"],
                        "threshold": 100,
                        "enabled": True,
                        "filters": {},
                    }
                ],
                "banned": [],
                "allowed": [],
                "settings": {"default_threshold": 100, "challenge_band": 20},
                "lists": {},
            }
        )
        row = await get_campaign(slug="demo")
        return row.bridge_url

    assert asyncio.run(run()) == "https://go.example.test"
