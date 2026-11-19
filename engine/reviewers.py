from __future__ import annotations

import ipaddress
from datetime import timedelta

from ipinfo import HOSTING_MARKERS

REVIEWER_REASONS = frozenset(
    {
        "review_burst",
        "google_crawler",
        "honeypot",
        "headless",
        "ip_range_blocked",
        "hosting",
        "asn_blocked",
        "cloaker_api",
    }
)

SAFE_ISP_MARKERS = (
    "comcast",
    "xfinity",
    "at&t",
    "at and t",
    "att enterprises",
    "att internet",
    "charter communications",
    "spectrum",
    "verizon",
    "cox communication",
    "centurylink",
    "lumen",
    "frontier",
    "optimum",
)

TTL_DAYS = 90


def should_remember(reason: str) -> bool:
    return (reason or "") in REVIEWER_REASONS


def normalize_ban_target(raw: str) -> str:
    text = (raw or "").strip()
    if not text:
        return ""
    try:
        if "/" in text:
            return str(ipaddress.ip_network(text, strict=False))
        return str(ipaddress.ip_address(text))
    except ValueError:
        return ""


def isp_is_safe(isp: str) -> bool:
    low = (isp or "").lower()
    return bool(low) and any(marker in low for marker in SAFE_ISP_MARKERS)


def isp_is_hosting(isp: str) -> bool:
    low = (isp or "").lower()
    return bool(low) and any(marker in low for marker in HOSTING_MARKERS)


async def remember_reviewer(ip: str, reason: str) -> None:
    target = normalize_ban_target(ip)
    if not target or not should_remember(reason):
        return
    from store import ban_ip, is_allowed

    if await is_allowed(target):
        return
    await ban_ip(target, reason, source="reviewer")


async def import_reviewers_from_logs(campaign: str, date_from: str = "", date_to: str = "") -> dict:
    from store import ban_ip, is_allowed, is_banned, list_logs

    day_from = (date_from or "").strip()
    day_to = (date_to or day_from).strip()
    rows, _ = await list_logs(
        limit=5000,
        campaign=campaign or "",
        verdict="grey",
        date_from=day_from,
        date_to=day_to,
    )
    added = 0
    skipped_safe = 0
    skipped_other = 0
    seen: set[str] = set()
    for row in rows:
        target = normalize_ban_target(row.ip)
        if not target or target in seen:
            continue
        seen.add(target)
        if isp_is_safe(row.isp):
            skipped_safe += 1
            continue
        if not isp_is_hosting(row.isp):
            skipped_other += 1
            continue
        if await is_allowed(target) or await is_banned(target):
            skipped_other += 1
            continue
        await ban_ip(target, f"import:{row.isp}", source="reviewer")
        added += 1
    return {"added": added, "skipped_safe": skipped_safe, "skipped_other": skipped_other}
