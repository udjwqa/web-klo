import time
from typing import Optional

import httpx

from settings import IPQS_API_KEY

TIMEOUT = 4.0


class IPQSResult:
    def __init__(self, data: dict):
        self.success = bool(data.get("success"))
        self.fraud_score = int(data.get("fraud_score") or 0)
        self.vpn = bool(data.get("vpn"))
        self.proxy = bool(data.get("proxy"))
        self.tor = bool(data.get("tor"))
        self.bot_status = bool(data.get("bot_status"))
        self.is_crawler = bool(data.get("is_crawler"))
        self.country_code = (data.get("country_code") or "").upper()
        self.city = data.get("city") or ""
        self.isp = data.get("ISP") or ""


class IPQSClient:
    def __init__(self) -> None:
        self._cache: dict[str, tuple[IPQSResult, float]] = {}
        self._http: Optional[httpx.AsyncClient] = None

    async def _client(self) -> httpx.AsyncClient:
        if self._http is None or self._http.is_closed:
            self._http = httpx.AsyncClient(timeout=TIMEOUT)
        return self._http

    async def lookup(self, ip: str) -> Optional[IPQSResult]:
        if not IPQS_API_KEY or _is_local(ip):
            return None
        hit = self._cache.get(ip)
        if hit and time.time() - hit[1] < 3600:
            return hit[0]
        try:
            http = await self._client()
            resp = await http.get(
                f"https://ipqualityscore.com/api/json/ip/{IPQS_API_KEY}/{ip}",
                params={
                    "strictness": 0,
                    "allow_public_access_points": "true",
                    "lighter_penalties": "true",
                },
            )
            resp.raise_for_status()
            result = IPQSResult(resp.json())
            self._cache[ip] = (result, time.time())
            return result
        except Exception:
            return None

    async def close(self) -> None:
        if self._http and not self._http.is_closed:
            await self._http.aclose()


def _is_local(ip: str) -> bool:
    return ip in {"127.0.0.1", "0.0.0.0", "::1", "localhost", ""}


ipqs_client = IPQSClient()
