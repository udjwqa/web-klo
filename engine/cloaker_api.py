from __future__ import annotations

from typing import Any, Optional

import httpx

from settings import CLOAKER_API_KEY, CLOAKER_API_URL, CLOAKER_CAMPAIGN_ID

TIMEOUT = 6.0
WHITE = "white"
GREY = "grey"
SKIP = "skip"

_BAN_ACTIONS = {"ban", "safe", "white", "block", "bot"}
_REAL_ACTIONS = {"real", "ok", "grey", "allow", "pass"}


def configured() -> bool:
    return bool(CLOAKER_API_URL)


def parse_cloaker_payload(data: Any) -> str:
    if not isinstance(data, dict) or not data:
        return WHITE
    ban = data.get("ban")
    action = str(
        data.get("action")
        or data.get("result")
        or data.get("verdict")
        or data.get("status")
        or ""
    ).strip().lower()
    if ban in (1, "1", True, "true", "ban"):
        return WHITE
    if action in _BAN_ACTIONS:
        return WHITE
    if action in _REAL_ACTIONS:
        return GREY
    if ban in (0, "0", False, "false"):
        return GREY
    if data.get("success") in (1, True, "1"):
        return GREY
    return WHITE


class CloakerClient:
    def __init__(self) -> None:
        self._http: Optional[httpx.AsyncClient] = None

    async def _client(self) -> httpx.AsyncClient:
        if self._http is None or self._http.is_closed:
            self._http = httpx.AsyncClient(timeout=TIMEOUT)
        return self._http

    async def check(
        self,
        *,
        ip: str,
        user_agent: str = "",
        accept_language: str = "",
        referer: str = "",
        country: str = "",
        asn: str = "",
        host: str = "",
        path: str = "/",
        query: dict | None = None,
    ) -> str:
        if not configured():
            return SKIP
        try:
            payload = await self._request(
                ip=ip,
                user_agent=user_agent,
                accept_language=accept_language,
                referer=referer,
                country=country,
                asn=asn,
                host=host,
                path=path,
                query=query or {},
            )
            return parse_cloaker_payload(payload)
        except Exception:
            return WHITE

    async def _request(
        self,
        *,
        ip: str,
        user_agent: str,
        accept_language: str,
        referer: str,
        country: str,
        asn: str,
        host: str,
        path: str,
        query: dict,
    ) -> Any:
        http = await self._client()
        headers = {"Accept": "application/json"}
        if CLOAKER_API_KEY:
            headers["X-Api-Key"] = CLOAKER_API_KEY
        body = {
            "key": CLOAKER_API_KEY,
            "campaign": CLOAKER_CAMPAIGN_ID,
            "cmp": CLOAKER_CAMPAIGN_ID,
            "adapi": "2.2",
            "ip": ip,
            "user_agent": user_agent,
            "country": country,
            "asn": asn,
            "host": host,
            "path": path,
            "query": query,
            "headers": {
                "REMOTE_ADDR": ip,
                "HTTP_USER_AGENT": user_agent,
                "HTTP_ACCEPT_LANGUAGE": accept_language,
                "HTTP_REFERER": referer,
                "HTTP_CF_IPCOUNTRY": country,
                "HTTP_CF_ASN": asn,
                "HTTP_HOST": host,
            },
        }
        url = CLOAKER_API_URL
        if "magicchecker" in url.lower():
            resp = await http.post(url, data={"cmp": CLOAKER_CAMPAIGN_ID, "adapi": "2.2", "headers": body["headers"]}, headers={"adapi": "2.2"})
        else:
            resp = await http.post(url, json=body, headers=headers)
        resp.raise_for_status()
        if not resp.content:
            raise RuntimeError("empty cloaker response")
        try:
            return resp.json()
        except ValueError as exc:
            raise RuntimeError("cloaker response is not json") from exc

    async def close(self) -> None:
        if self._http and not self._http.is_closed:
            await self._http.aclose()


cloaker_client = CloakerClient()
