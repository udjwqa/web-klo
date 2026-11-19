from __future__ import annotations

import ipaddress
import json
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from sqlalchemy import delete, desc, func, or_, select

from db import Session
from defaults import default_filters, strip_removed_filters
from models import (
    AllowedIPRow,
    BannedIPRow,
    CampaignIn,
    CampaignRow,
    DecisionRow,
    EngineSettingsRow,
    RequestLogRow,
    utcnow,
)
from reviewers import TTL_DAYS, normalize_ban_target, remember_reviewer
from settings import CHALLENGE_BAND, DEFAULT_THRESHOLD, DATA_DIR, WEBKLO_ROLE

_after_log = None
OUTBOX = DATA_DIR / "outbox.jsonl"


async def seed_if_empty() -> None:
    async with Session() as session:
        count = (await session.execute(select(func.count()).select_from(CampaignRow))).scalar_one()
        if count:
            return
        session.add(
            CampaignRow(
                slug="demo",
                name="Demo campaign",
                domain="localhost",
                offer_url="https://example.com/offer",
                white_mode="local_html",
                white_url="",
                geos=["US"],
                threshold=100,
                challenge_enabled=False,
                filters=default_filters(),
            )
        )
        await session.commit()


async def get_campaign(slug: str = "", host: str = "") -> CampaignRow | None:
    host = (host or "").split(":")[0].lower().removeprefix("www.")
    async with Session() as session:
        row = None
        if slug:
            row = (
                await session.execute(select(CampaignRow).where(CampaignRow.slug == slug))
            ).scalar_one_or_none()
        if row is None and host:
            rows = (await session.execute(select(CampaignRow))).scalars().all()
            for item in rows:
                domain = (item.domain or "").lower().removeprefix("www.")
                if domain and (host == domain or host.endswith("." + domain)):
                    row = item
                    break
        if row is None:
            return None
        session.expunge(row)
        return row


async def list_campaigns() -> list[CampaignRow]:
    async with Session() as session:
        rows = (await session.execute(select(CampaignRow).order_by(CampaignRow.name))).scalars().all()
        for row in rows:
            session.expunge(row)
        return rows


async def upsert_campaign(data: CampaignIn, campaign_id: str | None = None) -> CampaignRow:
    async with Session() as session:
        row = None
        if campaign_id:
            row = await session.get(CampaignRow, campaign_id)
        if row is None:
            row = (
                await session.execute(select(CampaignRow).where(CampaignRow.slug == data.slug))
            ).scalar_one_or_none()
        if row is None:
            row = CampaignRow(slug=data.slug)
            session.add(row)
        row.slug = data.slug
        row.name = data.name
        row.domain = data.domain
        row.offer_url = data.offer_url
        row.bridge_url = data.bridge_url or ""
        row.white_mode = data.white_mode
        row.white_url = data.white_url
        row.geos = data.geos
        row.threshold = data.threshold
        row.challenge_enabled = data.challenge_enabled
        row.panic = data.panic
        row.enabled = data.enabled
        row.filters = strip_removed_filters(data.filters)
        await session.commit()
        await session.refresh(row)
        session.expunge(row)
        return row


async def delete_campaign(campaign_id: str) -> None:
    async with Session() as session:
        row = await session.get(CampaignRow, campaign_id)
        if row:
            await session.delete(row)
            await session.commit()


async def set_panic(campaign_id: str, panic: bool) -> CampaignRow | None:
    async with Session() as session:
        row = await session.get(CampaignRow, campaign_id)
        if not row:
            return None
        row.panic = panic
        await session.commit()
        await session.refresh(row)
        session.expunge(row)
        return row


def _ban_active(row: BannedIPRow, now: datetime | None = None) -> bool:
    if row.expires_at is None:
        return True
    stamp = now or utcnow()
    expires = row.expires_at.replace(tzinfo=None) if row.expires_at.tzinfo else row.expires_at
    return expires > stamp


def _parse_expires(value) -> datetime | None:
    if not value:
        return None
    if isinstance(value, datetime):
        return value.replace(tzinfo=None) if value.tzinfo else value
    if isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
        return parsed.replace(tzinfo=None) if parsed.tzinfo else parsed
    return None


async def is_banned(ip: str) -> bool:
    target = (ip or "").strip()
    if not target:
        return False
    now = utcnow()
    async with Session() as session:
        row = await session.get(BannedIPRow, target)
        if row is not None and _ban_active(row, now):
            return True
        try:
            addr = ipaddress.ip_address(target)
        except ValueError:
            return False
        rows = (await session.execute(select(BannedIPRow))).scalars().all()
        for item in rows:
            if "/" not in (item.ip or "") or not _ban_active(item, now):
                continue
            try:
                network = ipaddress.ip_network(item.ip, strict=False)
            except ValueError:
                continue
            if addr in network:
                return True
        return False


async def ban_ip(ip: str, reason: str, source: str = "manual", expires_at: datetime | None = None) -> str:
    target = normalize_ban_target(ip)
    if not target:
        raise ValueError("bad ip")
    if expires_at is None and source == "reviewer":
        expires_at = utcnow() + timedelta(days=TTL_DAYS)
    async with Session() as session:
        row = await session.get(BannedIPRow, target)
        if row is None:
            session.add(BannedIPRow(ip=target, reason=reason, source=source, expires_at=expires_at))
        elif source == "reviewer" and row.source == "manual":
            pass
        else:
            row.reason = reason
            row.source = source
            if expires_at is not None:
                row.expires_at = expires_at
        await session.commit()
    return target


async def unban_ip(ip: str) -> None:
    raw = (ip or "").strip()
    target = normalize_ban_target(ip) or raw
    keys = {item for item in (raw, target) if item}
    async with Session() as session:
        deleted = False
        for key in keys:
            row = await session.get(BannedIPRow, key)
            if row:
                await session.delete(row)
                deleted = True
        if deleted:
            await session.commit()


async def is_allowed(ip: str) -> bool:
    async with Session() as session:
        return (await session.get(AllowedIPRow, ip)) is not None


async def allow_ip(ip: str, note: str = "") -> None:
    async with Session() as session:
        row = await session.get(AllowedIPRow, ip)
        if row is None:
            session.add(AllowedIPRow(ip=ip, note=note))
        else:
            row.note = note
        await session.commit()


async def disallow_ip(ip: str) -> None:
    async with Session() as session:
        row = await session.get(AllowedIPRow, ip)
        if row:
            await session.delete(row)
            await session.commit()


async def list_allowed() -> list[AllowedIPRow]:
    async with Session() as session:
        rows = (await session.execute(select(AllowedIPRow))).scalars().all()
        for row in rows:
            session.expunge(row)
        return rows


async def get_engine_settings() -> EngineSettingsRow:
    async with Session() as session:
        row = await session.get(EngineSettingsRow, 1)
        if row is None:
            row = EngineSettingsRow(id=1, default_threshold=DEFAULT_THRESHOLD, challenge_band=CHALLENGE_BAND)
            session.add(row)
            await session.commit()
            await session.refresh(row)
        session.expunge(row)
        return row


async def save_engine_settings(default_threshold: int, challenge_band: int) -> EngineSettingsRow:
    async with Session() as session:
        row = await session.get(EngineSettingsRow, 1)
        if row is None:
            row = EngineSettingsRow(id=1)
            session.add(row)
        row.default_threshold = default_threshold
        row.challenge_band = challenge_band
        await session.commit()
        await session.refresh(row)
        session.expunge(row)
        return row


async def list_bans() -> list[BannedIPRow]:
    async with Session() as session:
        rows = (await session.execute(select(BannedIPRow))).scalars().all()
        for row in rows:
            session.expunge(row)
        return rows


async def save_decision(row: DecisionRow) -> None:
    async with Session() as session:
        session.add(row)
        await session.commit()


async def get_decision(request_id: str) -> DecisionRow | None:
    async with Session() as session:
        row = await session.get(DecisionRow, request_id)
        if row:
            session.expunge(row)
        return row


async def finalize_decision(request_id: str, **fields) -> DecisionRow | None:
    async with Session() as session:
        row = await session.get(DecisionRow, request_id)
        if not row:
            return None
        for key, value in fields.items():
            setattr(row, key, value)
        row.finalized = True
        await session.commit()
        await session.refresh(row)
        session.expunge(row)
        return row


async def recent_hits(campaign: str, ip: str, minutes: int = 60) -> int:
    since = utcnow() - timedelta(minutes=minutes)
    async with Session() as session:
        stmt = select(func.count()).select_from(RequestLogRow).where(
            RequestLogRow.campaign == campaign,
            RequestLogRow.ip == ip,
            RequestLogRow.timestamp >= since,
            RequestLogRow.verdict != "payment",
        )
        return int((await session.execute(stmt)).scalar_one() or 0)


async def log_request(**fields) -> None:
    async with Session() as session:
        row = RequestLogRow(**fields)
        session.add(row)
        await session.commit()
        await session.refresh(row)
        payload = _log_payload(row)
    if WEBKLO_ROLE == "edge":
        _append_outbox(payload)
    if _after_log:
        _after_log(payload)


def _log_payload(row: RequestLogRow) -> dict:
    ts = row.timestamp.isoformat() if row.timestamp else ""
    return {
        "id": row.id,
        "timestamp": ts,
        "campaign": row.campaign,
        "ip": row.ip,
        "country": row.country,
        "city": row.city,
        "isp": row.isp,
        "referer": row.referer,
        "language": row.language,
        "user_agent": row.user_agent,
        "score": row.score,
        "verdict": row.verdict,
        "reason": row.reason,
        "details": row.details or [],
        "query": row.query or {},
    }


def _append_outbox(payload: dict) -> None:
    OUTBOX.parent.mkdir(parents=True, exist_ok=True)
    with OUTBOX.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, ensure_ascii=False) + "\n")


def campaign_dict(row: CampaignRow) -> dict:
    return {
        "slug": row.slug,
        "name": row.name,
        "domain": row.domain or "",
        "offer_url": row.offer_url,
        "bridge_url": getattr(row, "bridge_url", "") or "",
        "white_mode": row.white_mode,
        "white_url": row.white_url or "",
        "geos": row.geos or [],
        "threshold": row.threshold,
        "challenge_enabled": bool(row.challenge_enabled),
        "panic": bool(row.panic),
        "enabled": bool(row.enabled),
        "filters": strip_removed_filters(row.filters),
    }


async def build_snapshot() -> dict:
    settings_row = await get_engine_settings()
    from lists import DEFINITIONS, lists
    from ip_ranges import ip_range_checker

    return {
        "campaigns": [campaign_dict(row) for row in await list_campaigns()],
        "banned": [
            {
                "ip": r.ip,
                "reason": r.reason,
                "source": r.source,
                "expires_at": r.expires_at.isoformat() if r.expires_at else None,
            }
            for r in await list_bans()
        ],
        "allowed": [{"ip": r.ip, "note": r.note} for r in await list_allowed()],
        "settings": {
            "default_threshold": settings_row.default_threshold,
            "challenge_band": settings_row.challenge_band,
        },
        "lists": {name: lists.get(name) for name in DEFINITIONS},
        "ip_ranges": ip_range_checker.lines(),
    }


async def apply_snapshot(payload: dict) -> None:
    campaigns = payload.get("campaigns") or []
    keep = {item.get("slug") for item in campaigns if item.get("slug")}
    for row in await list_campaigns():
        if row.slug not in keep:
            await delete_campaign(row.id)
    for item in campaigns:
        await upsert_campaign(
            CampaignIn(
                slug=item["slug"],
                name=item.get("name") or item["slug"],
                domain=item.get("domain") or "",
                offer_url=item.get("offer_url") or "",
                bridge_url=item.get("bridge_url") or "",
                white_mode=item.get("white_mode") or "local_html",
                white_url=item.get("white_url") or "",
                geos=item.get("geos") or [],
                threshold=int(item.get("threshold") or DEFAULT_THRESHOLD),
                challenge_enabled=bool(item.get("challenge_enabled")),
                panic=bool(item.get("panic")),
                enabled=bool(item.get("enabled")),
                filters=item.get("filters") or default_filters(),
            )
        )
    await replace_ip_lists(payload.get("banned") or [], payload.get("allowed") or [])
    settings = payload.get("settings") or {}
    if settings:
        await save_engine_settings(
            int(settings.get("default_threshold") or DEFAULT_THRESHOLD),
            int(settings.get("challenge_band") or CHALLENGE_BAND),
        )
    from lists import DEFINITIONS, lists
    from ip_ranges import ip_range_checker

    for name, items in (payload.get("lists") or {}).items():
        if name in DEFINITIONS and isinstance(items, list):
            lists.set(name, items)
    if "ip_ranges" in payload:
        ip_range_checker.replace(payload.get("ip_ranges") or [])


async def replace_ip_lists(banned: list[dict], allowed: list[dict]) -> None:
    async with Session() as session:
        await session.execute(delete(BannedIPRow))
        await session.execute(delete(AllowedIPRow))
        for item in banned:
            ip = normalize_ban_target(item.get("ip") or "") or (item.get("ip") or "").strip()
            if ip:
                session.add(
                    BannedIPRow(
                        ip=ip,
                        reason=item.get("reason") or "",
                        source=item.get("source") or "sync",
                        expires_at=_parse_expires(item.get("expires_at")),
                    )
                )
        for item in allowed:
            ip = (item.get("ip") or "").strip()
            if ip:
                session.add(AllowedIPRow(ip=ip, note=item.get("note") or ""))
        await session.commit()


async def ingest_logs(items: list[dict]) -> int:
    added = 0
    pending: list[tuple[str, str]] = []
    async with Session() as session:
        for item in items:
            log_id = str(item.get("id") or "")
            if log_id:
                exists = await session.get(RequestLogRow, log_id)
                if exists:
                    continue
            ts = item.get("timestamp")
            moment = utcnow()
            if isinstance(ts, datetime):
                moment = ts.replace(tzinfo=None) if ts.tzinfo else ts
            elif isinstance(ts, str) and ts:
                try:
                    parsed = datetime.fromisoformat(ts.replace("Z", ""))
                    moment = parsed.replace(tzinfo=None) if parsed.tzinfo else parsed
                except ValueError:
                    moment = utcnow()
            fields = {
                "campaign": item.get("campaign") or "",
                "ip": item.get("ip") or "",
                "country": item.get("country") or "",
                "city": item.get("city") or "",
                "isp": item.get("isp") or "",
                "referer": item.get("referer") or "",
                "language": (item.get("language") or "")[:80],
                "user_agent": item.get("user_agent") or "",
                "score": int(item.get("score") or 0),
                "verdict": item.get("verdict") or "white",
                "reason": item.get("reason") or "",
                "details": item.get("details") or [],
                "query": item.get("query") or {},
                "timestamp": moment,
            }
            if log_id:
                fields["id"] = log_id
            session.add(RequestLogRow(**fields))
            added += 1
            if (fields["verdict"] or "white") != "payment":
                pending.append((fields["ip"], fields["reason"]))
        await session.commit()
    for ip, reason in pending:
        await remember_reviewer(ip, reason)
    return added


def read_outbox() -> list[dict]:
    if not OUTBOX.exists():
        return []
    rows = []
    for line in OUTBOX.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except Exception:
            continue
    return rows


def replace_outbox(rows: list[dict]) -> None:
    if not rows:
        if OUTBOX.exists():
            OUTBOX.unlink()
        return
    OUTBOX.write_text(
        "\n".join(json.dumps(item, ensure_ascii=False) for item in rows) + "\n",
        encoding="utf-8",
    )


def _msk_bounds(date_from: str, date_to: str) -> tuple[datetime | None, datetime | None]:
    start = end = None
    if date_from:
        start = datetime.strptime(date_from, "%Y-%m-%d").replace(tzinfo=MSK).astimezone(timezone.utc).replace(tzinfo=None)
    if date_to:
        end = (datetime.strptime(date_to, "%Y-%m-%d") + timedelta(days=1)).replace(tzinfo=MSK).astimezone(timezone.utc).replace(tzinfo=None)
    return start, end


def format_msk(moment: datetime | None) -> str:
    if not moment:
        return ""
    return _as_msk(moment).strftime("%d.%m.%Y %H:%M:%S")


async def list_logs(
    limit: int = 80,
    campaign: str = "",
    verdict: str = "",
    reason: str = "",
    country: str = "",
    q: str = "",
    date_from: str = "",
    date_to: str = "",
) -> tuple[list[RequestLogRow], int]:
    async with Session() as session:
        filters = []
        if campaign:
            filters.append(RequestLogRow.campaign == campaign)
        if verdict:
            filters.append(RequestLogRow.verdict == verdict)
        if reason:
            filters.append(RequestLogRow.reason == reason)
        if country:
            filters.append(RequestLogRow.country == country.upper())
        if q:
            like = f"%{q.strip()}%"
            filters.append(or_(
                RequestLogRow.ip.like(like),
                RequestLogRow.user_agent.like(like),
                RequestLogRow.isp.like(like),
                RequestLogRow.referer.like(like),
            ))
        start, end = _msk_bounds(date_from, date_to)
        if start:
            filters.append(RequestLogRow.timestamp >= start)
        if end:
            filters.append(RequestLogRow.timestamp < end)
        count_stmt = select(func.count()).select_from(RequestLogRow)
        stmt = select(RequestLogRow).order_by(desc(RequestLogRow.timestamp)).limit(limit)
        for item in filters:
            count_stmt = count_stmt.where(item)
            stmt = stmt.where(item)
        total = int((await session.execute(count_stmt)).scalar_one() or 0)
        rows = (await session.execute(stmt)).scalars().all()
        for row in rows:
            session.expunge(row)
        return rows, total


MSK = ZoneInfo("Europe/Moscow")


def _as_msk(moment: datetime) -> datetime:
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return moment.astimezone(MSK)


def _bucket_key(moment: datetime, step: str) -> str:
    local = _as_msk(moment)
    if step == "hour":
        return local.strftime("%Y-%m-%d %H")
    return local.strftime("%Y-%m-%d")


def _axis(span: str, now: datetime) -> tuple[datetime, str, list[datetime]]:
    local = _as_msk(now)
    if span == "30d":
        start_day = local.date() - timedelta(days=29)
        count = 30
        step = "day"
    elif span == "7d":
        start_day = local.date() - timedelta(days=6)
        count = 7
        step = "day"
    else:
        start_local = local.replace(hour=0, minute=0, second=0, microsecond=0)
        marks = [start_local + timedelta(hours=i) for i in range(24)]
        start_utc = marks[0].astimezone(timezone.utc).replace(tzinfo=None)
        return start_utc, "hour", marks
    start_local = datetime.combine(start_day, datetime.min.time(), MSK)
    marks = [start_local + timedelta(days=i) for i in range(count)]
    start_utc = marks[0].astimezone(timezone.utc).replace(tzinfo=None)
    return start_utc, step, marks


async def stats(campaign: str = "", span: str = "today") -> dict:
    if span not in {"today", "7d", "30d"}:
        span = "today"
    now = utcnow()
    start, step, marks = _axis(span, now)
    async with Session() as session:
        stmt = select(RequestLogRow).where(RequestLogRow.timestamp >= start)
        if campaign:
            stmt = stmt.where(RequestLogRow.campaign == campaign)
        rows = (await session.execute(stmt)).scalars().all()
        names = {
            row.slug: row.name
            for row in (await session.execute(select(CampaignRow))).scalars().all()
        }
    buckets = { _bucket_key(mark, step): {"grey": 0, "white": 0} for mark in marks }
    reasons: dict[str, int] = {}
    grey = white = 0
    by_day: dict[tuple[str, str], dict] = {}
    pay_ips: set[str] = set()
    for row in rows:
        if not row.timestamp or row.verdict == "payment":
            if row.timestamp and row.verdict == "payment" and row.ip:
                day = _as_msk(row.timestamp).strftime("%Y-%m-%d")
                slug = row.campaign or "—"
                cell = by_day.setdefault((day, slug), {
                    "date": day,
                    "slug": slug,
                    "offer": names.get(slug, slug),
                    "total": 0,
                    "grey": 0,
                    "white": 0,
                    "payIps": set(),
                })
                cell["payIps"].add(row.ip)
                pay_ips.add(row.ip)
            continue
        key = _bucket_key(row.timestamp, step)
        if key in buckets:
            if row.verdict == "grey":
                buckets[key]["grey"] += 1
                grey += 1
            elif row.verdict == "white":
                buckets[key]["white"] += 1
                white += 1
                if row.reason:
                    reasons[row.reason] = reasons.get(row.reason, 0) + 1
        day = _as_msk(row.timestamp).strftime("%Y-%m-%d")
        slug = row.campaign or "—"
        cell = by_day.setdefault( (day, slug), {
            "date": day,
            "slug": slug,
            "offer": names.get(slug, slug),
            "total": 0,
            "grey": 0,
            "white": 0,
            "payIps": set(),
        })
        if row.verdict == "grey":
            cell["grey"] += 1
            cell["total"] += 1
        elif row.verdict == "white":
            cell["white"] += 1
            cell["total"] += 1
    total = grey + white
    series = []
    for mark in marks:
        key = _bucket_key(mark, step)
        label = mark.strftime("%H:00") if step == "hour" else mark.strftime("%d.%m")
        series.append({"label": label, "grey": buckets[key]["grey"], "white": buckets[key]["white"]})
    days = []
    for cell in by_day.values():
        offer_count = cell["grey"]
        days.append({
            "date": cell["date"],
            "day": datetime.strptime(cell["date"], "%Y-%m-%d").strftime("%d.%m"),
            "slug": cell["slug"],
            "offer": cell["offer"],
            "total": cell["total"],
            "uniqueOffer": len(cell.get("payIps") or []),
            "grey": offer_count,
            "white": cell["white"],
            "offerPct": round(100 * offer_count / cell["total"], 1) if cell["total"] else 0,
        })
    days.sort(key=lambda item: (item["date"], item["offer"]), reverse=True)
    return {
        "range": span,
        "campaign": campaign,
        "campaignName": names.get(campaign, "Все офферы") if campaign else "Все офферы",
        "total": total,
        "grey": grey,
        "white": white,
        "grey_pct": round(100 * grey / total, 1) if total else 0,
        "uniqueOffer": len(pay_ips),
        "reasons": sorted(reasons.items(), key=lambda item: -item[1])[:8],
        "series": series,
        "days": days,
        "offers": [{"slug": slug, "name": name} for slug, name in sorted(names.items(), key=lambda item: item[1])],
    }
