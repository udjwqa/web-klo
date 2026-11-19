from __future__ import annotations

FILTER_KEYS = (
    "bots",
    "asn",
    "ip_ranges",
    "ipqs",
    "vpn",
    "hosting",
    "cities",
    "isp",
    "desktop",
    "gpu",
)

DEFAULT_WEIGHTS = {
    "vpn": 20,
    "proxy": 25,
    "tor": 80,
    "hosting": 35,
    "fraud": 40,
    "fraud_high": 60,
    "city": 12,
    "isp": 20,
    "desktop": 15,
    "mouse": 20,
    "timezone": 15,
    "static": 15,
    "battery": 25,
}


def default_filters() -> dict:
    return {
        "vpn": {"mode": "hard"},
        "ipqs": {"mode": "off", "points": 40},
        "hosting": {"mode": "hard"},
        "language": {"mode": "off", "points": 20, "langs": []},
        "empty_lang": {"mode": "hard"},
        "referer": {"mode": "hard"},
        "http_referer": {"mode": "hard"},
        "city": {"mode": "points", "points": 15},
        "isp": {"mode": "points", "points": 20},
        "velocity": {"mode": "points", "points": 40, "limit": 25},
        "burst": {"mode": "hard", "window_sec": 120, "min_asn": 3},
        "cloaker": {"mode": "hard"},
    }


def strip_removed_filters(filters: dict | None) -> dict:
    data = dict(filters or {})
    data.pop("click_id", None)
    return data


def weight(filters: dict | None, key: str) -> int:
    raw = ((filters or {}).get("weights") or {}).get(key, DEFAULT_WEIGHTS[key])
    try:
        return int(raw)
    except (TypeError, ValueError):
        return DEFAULT_WEIGHTS[key]
