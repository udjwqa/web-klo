from __future__ import annotations

import ipaddress
import json
import logging
import time
from pathlib import Path
from typing import Any, Optional

import httpx

from settings import DATA_DIR

logger = logging.getLogger("google_crawlers")

SOURCES = (
    "https://developers.google.com/static/crawling/ipranges/special-crawlers.json",
    "https://developers.google.com/static/crawling/ipranges/common-crawlers.json",
)
TTL_SEC = 86400
TIMEOUT = 8.0


class GoogleCrawlerChecker:
    def __init__(self) -> None:
        self._networks: list[ipaddress._BaseNetwork] = []
        self._loaded = False

    def _cache_path(self) -> Path:
        return DATA_DIR / "google_crawlers_cache.json"

    def load_prefixes(self, prefixes: list[str]) -> None:
        networks: list[ipaddress._BaseNetwork] = []
        for item in prefixes:
            try:
                networks.append(ipaddress.ip_network(item, strict=False))
            except ValueError:
                continue
        self._networks = networks
        self._loaded = True

    def is_crawler(self, ip: str) -> bool:
        if not ip:
            return False
        if not self._loaded:
            self.load()
        try:
            addr = ipaddress.ip_address(ip)
        except ValueError:
            return False
        return any(addr in net for net in self._networks)

    def load(self, force_refresh: bool = False) -> None:
        cached = self._read_cache()
        if cached and not force_refresh and time.time() - float(cached.get("updated") or 0) < TTL_SEC:
            self.load_prefixes(list(cached.get("prefixes") or []))
            return
        if force_refresh or not cached:
            prefixes = self._download_prefixes()
            if prefixes:
                self._write_cache(prefixes)
                self.load_prefixes(prefixes)
                return
        if cached:
            self.load_prefixes(list(cached.get("prefixes") or []))
            return
        self._networks = []
        self._loaded = True

    def _read_cache(self) -> Optional[dict[str, Any]]:
        path = self._cache_path()
        if not path.exists():
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        return data if isinstance(data, dict) else None

    def _write_cache(self, prefixes: list[str]) -> None:
        path = self._cache_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps({"updated": time.time(), "prefixes": prefixes}),
            encoding="utf-8",
        )

    def _fetch_json(self, url: str) -> dict:
        with httpx.Client(timeout=TIMEOUT) as client:
            resp = client.get(url)
            resp.raise_for_status()
            data = resp.json()
        if not isinstance(data, dict):
            raise ValueError("unexpected crawler list")
        return data

    def _download_prefixes(self) -> list[str]:
        prefixes: list[str] = []
        try:
            for url in SOURCES:
                payload = self._fetch_json(url)
                for row in payload.get("prefixes") or []:
                    if not isinstance(row, dict):
                        continue
                    cidr = row.get("ipv4Prefix") or row.get("ipv6Prefix")
                    if cidr:
                        prefixes.append(str(cidr))
        except Exception as exc:
            logger.warning("google crawler list refresh failed: %s", exc)
            return []
        return prefixes


google_crawlers = GoogleCrawlerChecker()
