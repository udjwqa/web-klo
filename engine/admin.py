from fastapi import APIRouter, Depends, Request, Response
from pydantic import BaseModel, Field

from auth import check_admin_password, require_admin, sign_admin
from decide import run_decide
from lists import DEFINITIONS, lists
from models import CampaignIn, DecideIn
from settings import CLOAKER_API_URL, IPINFO_TOKEN, IPQS_API_KEY
from store import format_msk
from reviewers import import_reviewers_from_logs
from store import (
    allow_ip,
    ban_ip,
    delete_campaign,
    disallow_ip,
    get_engine_settings,
    list_allowed,
    list_bans,
    list_campaigns,
    list_logs,
    save_engine_settings,
    set_panic,
    stats,
    unban_ip,
    upsert_campaign,
)

router = APIRouter(prefix="/admin/api")


class LoginIn(BaseModel):
    password: str


class BanIn(BaseModel):
    ip: str
    reason: str = "manual"
    source: str = "manual"


class ReviewerImportIn(BaseModel):
    campaign: str = ""
    date: str = ""


class PanicIn(BaseModel):
    panic: bool


class ListIn(BaseModel):
    items: list[str]


class AllowIn(BaseModel):
    ip: str
    note: str = ""


class EngineIn(BaseModel):
    default_threshold: int
    challenge_band: int


class SimulateIn(BaseModel):
    campaign: str = ""
    host: str = ""
    ip: str = "203.0.113.10"
    country: str = "US"
    user_agent: str = ""
    accept_language: str = ""
    referer: str = ""
    query: dict = Field(default_factory=dict)


@router.post("/login")
async def login(body: LoginIn, response: Response):
    if not check_admin_password(body.password):
        return Response(status_code=401)
    response.set_cookie(
        "klo_admin",
        sign_admin(),
        httponly=True,
        samesite="lax",
        max_age=60 * 60 * 24 * 7,
    )
    return {"ok": True}


@router.post("/logout")
async def logout(response: Response):
    response.delete_cookie("klo_admin")
    return {"ok": True}


@router.get("/me", dependencies=[Depends(require_admin)])
async def me():
    return {"ok": True}


@router.get("/stats", dependencies=[Depends(require_admin)])
async def get_stats(campaign: str = "", range: str = "today"):
    return await stats(campaign=campaign, span=range)


def _client_profile(user_agent: str) -> tuple[str, str]:
    low = (user_agent or "").lower()
    if "windows" in low:
        system = "Windows"
    elif "android" in low:
        system = "Android"
    elif "iphone" in low or "ipad" in low:
        system = "iOS"
    elif "mac os" in low:
        system = "macOS"
    elif "linux" in low or "x11" in low:
        system = "Linux"
    else:
        system = ""
    if any(token in low for token in ("bot", "spider", "crawler", "curl", "wget", "headless")):
        browser = "Бот"
    elif "edg/" in low:
        browser = "Edge"
    elif "firefox" in low:
        browser = "Firefox"
    elif "chrome/" in low or "crios" in low:
        browser = "Chrome"
    elif "safari" in low:
        browser = "Safari"
    else:
        browser = ""
    return system, browser


def _anon_badge(reason: str, details: list) -> str:
    checks = {item.get("check") for item in details or [] if isinstance(item, dict)}
    if reason in {"bot_user_agent", "headless", "bot_detected"} or "bot_ua" in checks or "headless" in checks:
        return "BOT"
    if reason == "tor" or "tor" in checks:
        return "TOR"
    if reason == "vpn" or "vpn" in checks:
        return "VPN"
    if reason in {"hosting", "asn_blocked", "ip_range_blocked", "isp"} or "hosting" in checks or "asn_block" in checks:
        return "HOST"
    return ""


def _log_item(row) -> dict:
    system, browser = _client_profile(row.user_agent or "")
    details = row.details or []
    return {
        "id": row.id,
        "timestamp": format_msk(row.timestamp),
        "campaign": row.campaign,
        "ip": row.ip,
        "country": row.country,
        "city": row.city,
        "isp": row.isp or "",
        "referer": row.referer or "",
        "language": row.language or "",
        "os": system,
        "browser": browser,
        "badge": _anon_badge(row.reason or "", details),
        "score": row.score,
        "verdict": row.verdict,
        "reason": row.reason,
        "user_agent": row.user_agent,
        "details": details,
        "query": row.query or {},
    }


@router.get("/logs", dependencies=[Depends(require_admin)])
async def get_logs(
    limit: int = 80,
    campaign: str = "",
    verdict: str = "",
    reason: str = "",
    country: str = "",
    q: str = "",
    date_from: str = "",
    date_to: str = "",
    count: int = 0,
):
    rows, total = await list_logs(
        limit=limit,
        campaign=campaign,
        verdict=verdict,
        reason=reason,
        country=country,
        q=q,
        date_from=date_from,
        date_to=date_to,
    )
    items = [_log_item(row) for row in rows]
    if count:
        return {"total": total, "items": items}
    return items


@router.get("/campaigns", dependencies=[Depends(require_admin)])
async def get_campaigns():
    rows = await list_campaigns()
    return [
        {
            "id": r.id,
            "slug": r.slug,
            "name": r.name,
            "domain": r.domain,
            "offer_url": r.offer_url,
            "bridge_url": getattr(r, "bridge_url", "") or "",
            "white_mode": r.white_mode,
            "white_url": r.white_url,
            "geos": r.geos,
            "threshold": r.threshold,
            "challenge_enabled": r.challenge_enabled,
            "panic": r.panic,
            "ads_review": r.panic,
            "enabled": r.enabled,
            "filters": r.filters,
        }
        for r in rows
    ]


@router.post("/campaigns", dependencies=[Depends(require_admin)])
async def post_campaign(body: CampaignIn):
    row = await upsert_campaign(body)
    return {"id": row.id}


@router.put("/campaigns/{campaign_id}", dependencies=[Depends(require_admin)])
async def put_campaign(campaign_id: str, body: CampaignIn):
    row = await upsert_campaign(body, campaign_id=campaign_id)
    return {"id": row.id}


@router.post("/campaigns/{campaign_id}/panic", dependencies=[Depends(require_admin)])
async def panic(campaign_id: str, body: PanicIn):
    row = await set_panic(campaign_id, body.panic)
    if row is None:
        return Response(status_code=404)
    return {"ok": True, "panic": row.panic, "ads_review": row.panic}


@router.delete("/campaigns/{campaign_id}", dependencies=[Depends(require_admin)])
async def remove_campaign(campaign_id: str):
    await delete_campaign(campaign_id)
    return {"ok": True}


@router.get("/lists", dependencies=[Depends(require_admin)])
async def get_lists():
    return lists.all()


@router.put("/lists/{name}", dependencies=[Depends(require_admin)])
async def put_list(name: str, body: ListIn):
    if name not in DEFINITIONS:
        return Response(status_code=404)
    lists.set(name, body.items)
    return {"ok": True}


@router.get("/bans", dependencies=[Depends(require_admin)])
async def get_bans():
    return [
        {
            "ip": r.ip,
            "reason": r.reason,
            "source": r.source,
            "expires_at": r.expires_at.isoformat() if r.expires_at else None,
        }
        for r in await list_bans()
    ]


@router.post("/bans", dependencies=[Depends(require_admin)])
async def post_ban(body: BanIn):
    source = (body.source or "manual").strip() or "manual"
    try:
        await ban_ip(body.ip, body.reason, source)
    except ValueError:
        return Response(status_code=400)
    return {"ok": True}


@router.delete("/bans/{ip:path}", dependencies=[Depends(require_admin)])
async def delete_ban(ip: str):
    await unban_ip(ip)
    return {"ok": True}


@router.post("/reviewers/import", dependencies=[Depends(require_admin)])
async def post_reviewer_import(body: ReviewerImportIn):
    day = (body.date or "").strip()
    return await import_reviewers_from_logs(campaign=body.campaign or "", date_from=day, date_to=day)


@router.get("/allow", dependencies=[Depends(require_admin)])
async def get_allow():
    return [{"ip": r.ip, "note": r.note} for r in await list_allowed()]


@router.post("/allow", dependencies=[Depends(require_admin)])
async def post_allow(body: AllowIn):
    await allow_ip(body.ip.strip(), body.note)
    return {"ok": True}


@router.delete("/allow/{ip}", dependencies=[Depends(require_admin)])
async def delete_allow(ip: str):
    await disallow_ip(ip)
    return {"ok": True}


@router.get("/engine", dependencies=[Depends(require_admin)])
async def get_engine():
    row = await get_engine_settings()
    return {
        "ipqs": bool(IPQS_API_KEY),
        "ipinfo": bool(IPINFO_TOKEN),
        "cloaker": bool(CLOAKER_API_URL),
        "default_threshold": row.default_threshold,
        "challenge_band": row.challenge_band,
    }


@router.put("/engine", dependencies=[Depends(require_admin)])
async def put_engine(body: EngineIn):
    row = await save_engine_settings(body.default_threshold, body.challenge_band)
    return {
        "ipqs": bool(IPQS_API_KEY),
        "ipinfo": bool(IPINFO_TOKEN),
        "cloaker": bool(CLOAKER_API_URL),
        "default_threshold": row.default_threshold,
        "challenge_band": row.challenge_band,
    }


@router.post("/simulate", dependencies=[Depends(require_admin)])
async def simulate(body: SimulateIn, request: Request):
    decision = await run_decide(
        DecideIn(
            campaign=body.campaign,
            host=body.host,
            ip=body.ip,
            user_agent=body.user_agent,
            accept_language=body.accept_language,
            headers={"cf-ipcountry": body.country, "referer": body.referer},
            query=body.query,
        ),
        request,
    )
    return decision.model_dump()
