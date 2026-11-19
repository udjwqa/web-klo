from __future__ import annotations

import uuid

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse, Response

from auth import check_engine_key
from burst import burst_config, burst_window
from models import CampaignRow, DecideIn, DecideOut, DecisionRow, ScoringDetail
from reviewers import remember_reviewer
from scoring import scoring
from settings import COLLECT_DELAY_MS
from store import (
    build_snapshot,
    finalize_decision,
    get_campaign,
    get_decision,
    get_engine_settings,
    ingest_logs,
    is_allowed,
    is_banned,
    list_campaigns,
    log_request,
    recent_hits,
    save_decision,
)
from urllib.parse import urlsplit

from urls import with_query

router = APIRouter()

HONEYPOT = {
    "/admin",
    "/wp-admin",
    "/wp-login.php",
    "/.env",
    "/.git/config",
    "/phpmyadmin",
    "/xmlrpc.php",
    "/login",
    "/debug",
}


def _client_ip(request: Request, body_ip: str) -> str:
    if body_ip:
        return body_ip
    forwarded = request.headers.get("cf-connecting-ip") or request.headers.get("x-forwarded-for", "")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "0.0.0.0"


def _is_go_path(path: str) -> bool:
    return (path or "/").rstrip("/") == "/go"


def _same_host_go(host: str, domain: str = "") -> str:
    name = (host or domain or "").split(":")[0].strip().lower()
    if name.startswith("www."):
        name = name[4:]
    if not name:
        return "/go"
    return f"https://{name}/go"


def _grey_url(campaign: CampaignRow, host: str = "", path: str = "/") -> str:
    if _is_go_path(path):
        return (campaign.offer_url or "").strip()
    return _same_host_go(host, campaign.domain or "")


def _action_for(campaign: CampaignRow, verdict: str, host: str = "", path: str = "/") -> tuple[str, str]:
    if verdict == "grey":
        url = _grey_url(campaign, host=host, path=path)
        if _is_go_path(path):
            return "show_preland", url
        return "redirect_offer", url
    if campaign.white_mode == "redirect" and campaign.white_url:
        return "redirect_white", campaign.white_url
    return "show_white", campaign.white_url or "/ind-w.html"


async def run_decide(body: DecideIn, request: Request) -> DecideOut:
    campaign = await get_campaign(slug=body.campaign, host=body.host)
    if campaign is None or not campaign.enabled:
        return DecideOut(
            request_id=str(uuid.uuid4()),
            verdict="white",
            action="show_white",
            reason="unknown_campaign",
        )

    ip = _client_ip(request, body.ip)
    ua = body.user_agent or request.headers.get("user-agent", "")
    path = (body.path or "/").rstrip("/") or "/"
    country_hint = (
        body.headers.get("cf-ipcountry")
        or request.headers.get("cf-ipcountry")
        or ""
    )
    asn_hint = str(body.headers.get("cf-asn") or request.headers.get("cf-asn") or "")

    if campaign.panic:
        action, url = _action_for(campaign, "white", host=body.host, path=path)
        out = DecideOut(
            request_id=str(uuid.uuid4()),
            verdict="white",
            action=action,
            url=url,
            reason="panic",
            campaign=campaign.slug,
        )
        await log_request(
            campaign=campaign.slug,
            ip=ip,
            country=country_hint.upper(),
            user_agent=ua,
            score=100,
            verdict="white",
            reason="panic",
            query=body.query,
            referer=str(body.headers.get("referer") or ""),
            language=(body.accept_language or "")[:80],
        )
        return out

    settings_row = await get_engine_settings()
    challenge_band = settings_row.challenge_band

    if path in HONEYPOT or any(path.startswith(p + "/") for p in HONEYPOT):
        result_reason = "honeypot"
        result_score = 100
        result_verdict = "white"
        details = []
        country = country_hint.upper()
        city = ""
        isp_name = ""
    else:
        result = await scoring.score(
            ip=ip,
            user_agent=ua,
            accept_language=body.accept_language,
            country_hint=country_hint,
            asn_hint=asn_hint,
            geos=campaign.geos or [],
            threshold=campaign.threshold,
            filters=campaign.filters or {},
            js_metrics=body.js_metrics,
            banned=await is_banned(ip),
            allowed=await is_allowed(ip),
            referer=str(body.headers.get("referer") or body.headers.get("referrer") or ""),
            recent_hits=await recent_hits(campaign.slug, ip),
            query=body.query,
        )
        result_reason = result.reason
        result_score = result.score
        result_verdict = result.verdict
        details = result.details
        country = result.country
        city = result.city
        isp_name = result.isp

    verdict = result_verdict
    cfg = burst_config(campaign.filters)
    if (
        verdict == "grey"
        and cfg["mode"] != "off"
        and burst_window.should_hold(
            campaign.slug,
            ip=ip,
            asn=asn_hint,
            path=path,
            window_sec=cfg["window_sec"],
            min_asn=cfg["min_asn"],
        )
    ):
        verdict = "white"
        result_verdict = "white"
        result_reason = "review_burst"
        result_score = max(result_score, 100)
        details = list(details) + [
            ScoringDetail(check="burst", points=100, reason="Dual-fetch: бот или хостинг уже были на этой кампании")
        ]
    if (
        verdict == "grey"
        and campaign.challenge_enabled
        and body.js_metrics is None
        and result_score >= max(0, campaign.threshold - challenge_band)
    ):
        verdict = "challenge"

    request_id = body.request_id or str(uuid.uuid4())
    action, url = _action_for(
        campaign,
        "grey" if verdict == "grey" else "white",
        host=body.host,
        path=path,
    )
    if verdict == "challenge":
        action, url = "challenge", ""
    if verdict == "grey":
        url = with_query(url, {k: v for k, v in body.query.items() if k != "klo"})

    await save_decision(
        DecisionRow(
            id=request_id,
            campaign=campaign.slug,
            ip=ip,
            user_agent=ua,
            query=body.query,
            headers=body.headers,
            score=result_score,
            verdict=verdict,
            reason=result_reason,
            details=[d.model_dump() for d in details],
            country=country,
            city=city,
            offer_url=with_query(campaign.offer_url, {k: v for k, v in body.query.items() if k != "klo"}),
            finalized=verdict != "challenge",
        )
    )
    if verdict != "challenge":
        await log_request(
            campaign=campaign.slug,
            ip=ip,
            country=country,
            city=city,
            user_agent=ua,
            score=result_score,
            verdict=verdict,
            reason=result_reason,
            details=[d.model_dump() for d in details],
            query=body.query,
            isp=isp_name,
            referer=str(body.headers.get("referer") or ""),
            language=(body.accept_language or "")[:80],
        )
        burst_window.remember(
            campaign.slug,
            ip=ip,
            asn=asn_hint,
            verdict=verdict,
            reason=result_reason,
            path=path,
        )
        await remember_reviewer(ip, result_reason)

    return DecideOut(
        request_id=request_id,
        verdict=verdict,
        action=action,
        url=url,
        score=result_score,
        reason=result_reason,
        campaign=campaign.slug,
        details=details,
    )


def _offer_host(url: str) -> str:
    host = urlsplit(url or "").netloc.lower().split(":")[0]
    return host.removeprefix("www.")


async def _campaign_for_payment(klo: str, source: str) -> str:
    pending = await get_decision(klo) if klo else None
    if pending and pending.verdict == "grey" and pending.campaign:
        return pending.campaign
    host = (source or "").split(":")[0].strip().lower().removeprefix("www.")
    if not host:
        return ""
    matches = [row.slug for row in await list_campaigns() if _offer_host(row.offer_url) == host]
    if len(matches) == 1:
        return matches[0]
    return ""


def _visitor_ip(request: Request) -> str:
    for header in ("cf-connecting-ip", "x-real-ip"):
        raw = request.headers.get(header) or ""
        ip = raw.split(",")[0].strip()
        if ip:
            return ip[:45]
    if request.client and request.client.host:
        return request.client.host[:45]
    return ""


@router.api_route("/v1/pay", methods=["GET", "POST"])
async def pay(request: Request):
    klo = request.query_params.get("klo") or ""
    source = request.query_params.get("source") or ""
    if request.method == "POST" and not klo:
        try:
            payload = await request.json()
        except Exception:
            payload = {}
        klo = str((payload or {}).get("klo") or "")
        source = source or str((payload or {}).get("source") or "")
    campaign = await _campaign_for_payment(klo, source)
    if campaign:
        await log_request(
            campaign=campaign,
            ip=_visitor_ip(request),
            verdict="payment",
            reason="payment",
            query={"klo": klo, "source": source},
        )
    return Response(status_code=204)


@router.get("/v1/sync")
async def sync(request: Request):
    check_engine_key(request)
    return await build_snapshot()


@router.post("/v1/ingest")
async def ingest(request: Request):
    check_engine_key(request)
    try:
        payload = await request.json()
    except Exception:
        payload = {}
    items = (payload or {}).get("logs") or []
    if not isinstance(items, list):
        return JSONResponse({"error": "bad logs"}, status_code=400)
    added = await ingest_logs(items[:400])
    return {"ok": True, "added": added}


@router.post("/v1/decide")
async def decide(body: DecideIn, request: Request):
    check_engine_key(request)
    return await run_decide(body, request)


@router.post("/v1/collect")
async def collect(request: Request):
    payload = await request.json()
    request_id = payload.get("request_id") or ""
    metrics = payload.get("metrics") or payload
    pending = await get_decision(request_id) if request_id else None
    if pending is None:
        return JSONResponse({"error": "unknown request"}, status_code=404)

    campaign = await get_campaign(slug=pending.campaign)
    if campaign is None:
        return JSONResponse({"error": "unknown campaign"}, status_code=404)

    result = await scoring.score(
        ip=pending.ip,
        user_agent=pending.user_agent,
        geos=campaign.geos or [],
        threshold=campaign.threshold,
        filters=campaign.filters or {},
        js_metrics=metrics,
        banned=await is_banned(pending.ip),
        allowed=await is_allowed(pending.ip),
        country_hint=pending.country,
    )
    verdict = result.verdict
    reason = result.reason
    score = result.score
    details = list(result.details)
    cfg = burst_config(campaign.filters)
    if (
        verdict == "grey"
        and cfg["mode"] != "off"
        and burst_window.should_hold(
            campaign.slug,
            ip=pending.ip,
            path="/",
            window_sec=cfg["window_sec"],
            min_asn=cfg["min_asn"],
        )
    ):
        verdict = "white"
        reason = "review_burst"
        score = max(score, 100)
        details.append(ScoringDetail(check="burst", points=100, reason="Dual-fetch: бот или хостинг уже были на этой кампании"))
    action, url = _action_for(campaign, verdict, host=campaign.domain, path="/")
    if verdict == "grey":
        url = with_query(url, {k: v for k, v in (pending.query or {}).items() if k != "klo"})

    await finalize_decision(
        request_id,
        score=score,
        verdict=verdict,
        reason=reason,
        details=[d.model_dump() for d in details],
        country=result.country,
        city=result.city,
    )
    await log_request(
        campaign=campaign.slug,
        ip=pending.ip,
        country=result.country,
        city=result.city,
        user_agent=pending.user_agent,
        score=score,
        verdict=verdict,
        reason=reason,
        details=[d.model_dump() for d in details],
        query=pending.query,
        isp=result.isp,
        referer=str((pending.headers or {}).get("referer") or ""),
    )
    burst_window.remember(
        campaign.slug,
        ip=pending.ip,
        verdict=verdict,
        reason=reason,
        path="/",
    )
    await remember_reviewer(pending.ip, reason)
    return DecideOut(
        request_id=request_id,
        verdict=verdict,
        action=action,
        url=url,
        score=score,
        reason=reason,
        campaign=campaign.slug,
        details=details,
    )


@router.get("/v1/challenge")
async def challenge_page(rid: str):
    pending = await get_decision(rid)
    if pending is None:
        return HTMLResponse("expired", status_code=404)
    html = (open_challenge()).replace("__RID__", rid).replace("__DELAY__", str(COLLECT_DELAY_MS))
    return HTMLResponse(html)


def open_challenge() -> str:
    from pathlib import Path

    return (Path(__file__).parent / "templates" / "challenge.html").read_text(encoding="utf-8")
