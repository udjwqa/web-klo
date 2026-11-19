from __future__ import annotations

AUTOBAN = 100

SPECS = {
    "vpn": {"modes": ("off", "points", "hard"), "mode": "hard", "points": 100},
    "ipqs": {"modes": ("off", "points", "hard"), "mode": "off", "points": 40},
    "hosting": {"modes": ("off", "points", "hard"), "mode": "hard", "points": 100},
    "language": {"modes": ("off", "points"), "mode": "off", "points": 20},
    "empty_lang": {"modes": ("off", "hard"), "mode": "hard", "points": 100},
    "referer": {"modes": ("off", "hard"), "mode": "hard", "points": 100},
    "http_referer": {"modes": ("off", "hard"), "mode": "hard", "points": 100},
    "city": {"modes": ("off", "points", "hard"), "mode": "points", "points": 15},
    "isp": {"modes": ("off", "points", "hard"), "mode": "points", "points": 20},
    "velocity": {"modes": ("off", "points", "hard"), "mode": "points", "points": 40, "limit": 25},
    "cloaker": {"modes": ("off", "hard"), "mode": "hard", "points": 100},
}

BAD_REFERERS = (
    "ads.google.",
    "adwords.google.",
    "adsmanager",
    "business.facebook.com",
    "facebook.com/ads",
    "tagassistant.google.",
    "tagmanager.google.",
    "ads.tiktok.com",
)


def rule(filters: dict | None, key: str) -> dict:
    spec = SPECS[key]
    raw = (filters or {}).get(key)
    mode = spec["mode"]
    points = spec["points"]
    limit = spec.get("limit", 25)
    langs: list[str] = []
    if isinstance(raw, bool):
        mode = spec["mode"] if raw else "off"
    elif isinstance(raw, dict):
        mode = str(raw.get("mode") or spec["mode"])
        try:
            points = int(raw.get("points") if raw.get("points") is not None else spec["points"])
        except (TypeError, ValueError):
            points = spec["points"]
        try:
            limit = int(raw.get("limit") or spec.get("limit") or 25)
        except (TypeError, ValueError):
            limit = spec.get("limit", 25)
        langs = [str(item).lower().split("-")[0][:2] for item in (raw.get("langs") or []) if str(item).strip()]
    if mode not in spec["modes"]:
        mode = spec["mode"]
    if mode == "hard":
        points = AUTOBAN
    return {"mode": mode, "points": max(0, points), "limit": max(2, limit), "langs": langs}


def browser_langs(header: str) -> list[str]:
    found = []
    for part in (header or "").split(","):
        tag = part.split(";")[0].strip().lower()
        if not tag:
            continue
        found.append(tag.split("-")[0][:2])
    return found


def bad_referer(referer: str) -> bool:
    low = (referer or "").lower()
    return any(token in low for token in BAD_REFERERS)


def insecure_referer(referer: str) -> bool:
    low = (referer or "").strip().lower()
    if not low.startswith("http://"):
        return False
    return not any(token in low for token in ("google", "facebook", "instagram"))
