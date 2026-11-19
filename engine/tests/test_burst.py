import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite://")

from burst import BurstWindow, burst_config


def _window() -> BurstWindow:
    return BurstWindow()


def test_bot_then_other_slash24_is_burst():
    window = _window()
    window.remember(
        "demo",
        ip="198.51.100.10",
        asn="15169",
        verdict="white",
        reason="bot_user_agent",
        path="/",
        ts=1000,
    )
    assert window.should_hold(
        "demo",
        ip="203.0.113.40",
        asn="7922",
        path="/",
        window_sec=120,
        min_asn=3,
        ts=1001,
    ) is True


def test_hosting_white_then_other_slash24_is_burst():
    window = _window()
    window.remember(
        "demo",
        ip="1.2.3.4",
        asn="132203",
        verdict="white",
        reason="hosting",
        path="/",
        ts=1000,
    )
    assert window.should_hold(
        "demo",
        ip="203.0.113.40",
        asn="7922",
        path="/",
        ts=1001,
    ) is True


def test_same_slash24_bot_then_chrome_is_not_burst():
    window = _window()
    window.remember(
        "demo",
        ip="203.0.113.10",
        asn="",
        verdict="white",
        reason="bot_user_agent",
        path="/",
        ts=1000,
    )
    assert window.should_hold(
        "demo",
        ip="203.0.113.11",
        asn="",
        path="/",
        ts=1001,
    ) is False


def test_single_comcast_without_bot_is_not_burst():
    window = _window()
    assert window.should_hold(
        "demo",
        ip="203.0.113.40",
        asn="7922",
        path="/",
        ts=1000,
    ) is False


def test_same_asn_many_slash24s_are_not_burst():
    window = _window()
    peers = (
        "203.0.113.10",
        "198.51.100.10",
        "192.0.2.10",
        "192.0.2.20",
        "198.51.100.20",
    )
    for index, ip in enumerate(peers):
        window.remember(
            "demo",
            ip=ip,
            asn="7922",
            verdict="grey",
            reason="ok",
            path="/",
            ts=1000 + index,
        )
    assert window.should_hold(
        "demo",
        ip="203.0.113.50",
        asn="7922",
        path="/",
        ts=1006,
    ) is False


def test_three_asns_on_home_is_burst():
    window = _window()
    window.remember("demo", ip="203.0.113.10", asn="7922", verdict="grey", reason="ok", path="/", ts=1000)
    window.remember("demo", ip="198.51.100.10", asn="701", verdict="grey", reason="ok", path="/", ts=1001)
    assert window.should_hold(
        "demo",
        ip="192.0.2.10",
        asn="21928",
        path="/",
        min_asn=3,
        ts=1002,
    ) is True


def test_expired_bot_outside_window_is_not_burst():
    window = _window()
    window.remember(
        "demo",
        ip="198.51.100.10",
        asn="15169",
        verdict="white",
        reason="google_crawler",
        path="/",
        ts=1000,
    )
    assert window.should_hold(
        "demo",
        ip="203.0.113.40",
        asn="7922",
        path="/",
        window_sec=120,
        ts=1121,
    ) is False


def test_other_campaign_bot_does_not_bleed():
    window = _window()
    window.remember(
        "other",
        ip="198.51.100.10",
        asn="15169",
        verdict="white",
        reason="bot_user_agent",
        path="/",
        ts=1000,
    )
    assert window.should_hold(
        "demo",
        ip="203.0.113.40",
        asn="7922",
        path="/",
        ts=1001,
    ) is False


def test_burst_config_defaults_hard():
    cfg = burst_config({})
    assert cfg["mode"] == "hard"
    assert cfg["window_sec"] == 120
    assert cfg["min_asn"] == 3
    assert burst_config({"burst": {"mode": "off"}})["mode"] == "off"
