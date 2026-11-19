import time
from typing import Optional

import httpx

from settings import IPINFO_TOKEN

TIMEOUT = 4.0
TTL = 86400


HOSTING_MARKERS = (
    "amazon.com",
    "amazon technologies",
    "digitalocean",
    "hetzner",
    "ovh",
    "linode",
    "vultr",
    "google llc",
    "google cloud",
    "microsoft corporation",
    "m247",
    "leaseweb",
    "choopa",
    "psychz",
    "colocation",
    "datacenter",
    "data center",
    "dedicated",
    "cloudflare",
    "contabo",
    "hivelocity",
    "ovhcloud",
    "tencent",
    "hostroyale",
    "egihosting",
    "web2objects",
    "upcloud",
    "cherry servers",
    "netcup",
    "alibaba",
    "thg hosting",
    "sakura clouds",
    "stat express",
)


class IPInfoResult:
    def __init__(self, data: dict):
        self.country = (data.get("country") or "").upper()
        self.city = data.get("city") or ""
        self.org = data.get("org") or ""
        self.timezone = data.get("timezone") or ""
        privacy = data.get("privacy") or {}
        self.vpn = bool(privacy.get("vpn") or privacy.get("proxy") or privacy.get("relay"))
        self.proxy = bool(privacy.get("proxy"))
        self.hosting = bool(privacy.get("hosting"))
        self.tor = bool(privacy.get("tor"))
        self.asn = ""
        asn = data.get("asn")
        if isinstance(asn, dict):
            self.asn = str(asn.get("asn") or "").replace("AS", "")
            self.org = self.org or str(asn.get("name") or "")
        if not self.asn and self.org.startswith("AS"):
            self.asn = self.org.split(" ", 1)[0][2:]
        org_low = self.org.lower()
        if not self.hosting and any(marker in org_low for marker in HOSTING_MARKERS):
            self.hosting = True

    @property
    def isp(self) -> str:
        if self.org and " " in self.org:
            return self.org.split(" ", 1)[1]
        return self.org


class IPInfoClient:
    def __init__(self) -> None:
        self._cache: dict[str, tuple[IPInfoResult, float]] = {}
        self._http: Optional[httpx.AsyncClient] = None

    async def _client(self) -> httpx.AsyncClient:
        if self._http is None or self._http.is_closed:
            self._http = httpx.AsyncClient(timeout=TIMEOUT)
        return self._http

    async def lookup(self, ip: str) -> Optional[IPInfoResult]:
        if not IPINFO_TOKEN or ip in {"127.0.0.1", "0.0.0.0", "::1", "localhost", ""}:
            return None
        hit = self._cache.get(ip)
        if hit and time.time() - hit[1] < TTL:
            return hit[0]
        try:
            http = await self._client()
            resp = await http.get(f"https://ipinfo.io/{ip}", params={"token": IPINFO_TOKEN})
            resp.raise_for_status()
            result = IPInfoResult(resp.json())
            self._cache[ip] = (result, time.time())
            return result
        except Exception:
            return None

    async def close(self) -> None:
        if self._http and not self._http.is_closed:
            await self._http.aclose()


ipinfo_client = IPInfoClient()
