from __future__ import annotations

import ipaddress
import time
from collections import defaultdict, deque
from dataclasses import dataclass

BOT_REASONS = frozenset(
    {
        "bot_user_agent",
        "google_crawler",
        "hosting",
        "asn_blocked",
        "ip_range_blocked",
        "headless",
    }
)

DEFAULT_WINDOW_SEC = 120
DEFAULT_MIN_ASN = 3


@dataclass
class BurstEvent:
    ip: str
    asn: str
    verdict: str
    reason: str
    path: str
    ts: float


def _now(ts: float) -> float:
    return float(ts) if ts else time.time()


def net_key(ip: str) -> str:
    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        return ip or ""
    prefix = 24 if addr.version == 4 else 48
    return str(ipaddress.ip_network(f"{addr}/{prefix}", strict=False))


def normalize_path(path: str) -> str:
    return (path or "/").rstrip("/") or "/"


def burst_config(filters: dict | None) -> dict:
    raw = (filters or {}).get("burst")
    mode = "hard"
    window_sec = DEFAULT_WINDOW_SEC
    min_asn = DEFAULT_MIN_ASN
    if raw is False:
        mode = "off"
    elif isinstance(raw, dict):
        mode = str(raw.get("mode") or "hard")
        try:
            window_sec = int(raw.get("window_sec") if raw.get("window_sec") is not None else DEFAULT_WINDOW_SEC)
        except (TypeError, ValueError):
            window_sec = DEFAULT_WINDOW_SEC
        try:
            min_asn = int(raw.get("min_asn") if raw.get("min_asn") is not None else DEFAULT_MIN_ASN)
        except (TypeError, ValueError):
            min_asn = DEFAULT_MIN_ASN
    if mode not in ("off", "hard", "points"):
        mode = "hard"
    return {
        "mode": mode,
        "window_sec": max(1, window_sec),
        "min_asn": max(2, min_asn),
    }


class BurstWindow:
    def __init__(self) -> None:
        self._events: dict[str, deque[BurstEvent]] = defaultdict(deque)

    def clear(self, campaign: str | None = None) -> None:
        if campaign is None:
            self._events.clear()
            return
        self._events.pop(campaign, None)

    def remember(
        self,
        campaign: str,
        *,
        ip: str,
        asn: str = "",
        verdict: str = "",
        reason: str = "",
        path: str = "/",
        ts: float = 0.0,
    ) -> None:
        if not campaign:
            return
        event = BurstEvent(
            ip=ip or "",
            asn=str(asn or "").strip(),
            verdict=verdict,
            reason=reason,
            path=normalize_path(path),
            ts=_now(ts),
        )
        bucket = self._events[campaign]
        bucket.append(event)
        cutoff = event.ts - 3600
        while bucket and bucket[0].ts < cutoff:
            bucket.popleft()

    def _recent(self, campaign: str, now: float, window_sec: int) -> list[BurstEvent]:
        bucket = self._events[campaign]
        cutoff = now - window_sec
        while bucket and bucket[0].ts < cutoff:
            bucket.popleft()
        return [item for item in bucket if item.ts >= cutoff]

    def should_hold(
        self,
        campaign: str,
        *,
        ip: str,
        asn: str = "",
        path: str = "/",
        window_sec: int = DEFAULT_WINDOW_SEC,
        min_asn: int = DEFAULT_MIN_ASN,
        ts: float = 0.0,
    ) -> bool:
        if not campaign:
            return False
        now = _now(ts)
        recent = self._recent(campaign, now, window_sec)
        current_net = net_key(ip)
        for item in recent:
            if item.verdict != "white":
                continue
            if item.reason not in BOT_REASONS:
                continue
            prior_net = net_key(item.ip)
            if prior_net and current_net and prior_net != current_net:
                return True
        if normalize_path(path) != "/":
            return False
        asns = {item.asn for item in recent if item.asn and item.path == "/"}
        current_asn = str(asn or "").strip()
        if current_asn:
            asns.add(current_asn)
        return len(asns) >= min_asn


burst_window = BurstWindow()
