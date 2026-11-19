from __future__ import annotations

import re

from checks import AUTOBAN, bad_referer, browser_langs, insecure_referer, rule
from cloaker_api import WHITE as CLOAKER_WHITE, cloaker_client
from defaults import weight
from google_crawlers import google_crawlers
from ip_ranges import ip_range_checker
from ipinfo import ipinfo_client
from ipqs import ipqs_client
from lists import lists
from models import ScoringDetail, ScoringResult
from timezone_utils import compare_timezones

IN_APP = (
    "fban",
    "fbav",
    "fb_iab",
    "fb4a",
    "fbios",
    "instagram",
    "tiktok",
    "bytedance",
    "musical_ly",
    "snapchat",
    "pinterest",
)

HEADLESS = (
    "headlesschrome",
    "phantomjs",
    "selenium",
    "puppeteer",
    "playwright",
    "scrapy",
    "httpclient",
    "curl/",
    "wget/",
    "python-requests",
    "go-http-client",
    "libwww-perl",
)

def _in_app(ua: str) -> bool:
    low = ua.lower()
    return any(token in low for token in IN_APP)


class WebScoring:
    async def score(
        self,
        *,
        ip: str,
        user_agent: str,
        accept_language: str = "",
        country_hint: str = "",
        asn_hint: str = "",
        geos: list[str] | None = None,
        threshold: int = 70,
        filters: dict | None = None,
        js_metrics: dict | None = None,
        banned: bool = False,
        allowed: bool = False,
        referer: str = "",
        recent_hits: int = 0,
        query: dict | None = None,
    ) -> ScoringResult:
        filters = filters or {}
        details: list[ScoringDetail] = []
        total = 0
        reason = ""
        country = (country_hint or "").upper()
        city = ""
        ua = user_agent or ""
        ua_low = ua.lower()

        def add(check: str, pts: int, why: str, code: str | None = None) -> None:
            nonlocal total, reason
            total += pts
            details.append(ScoringDetail(check=check, points=pts, reason=why))
            if code and not reason:
                reason = code

        if banned:
            add("banned_ip", AUTOBAN, "IP в бан-листе", "banned")
        elif allowed:
            return ScoringResult(
                score=0,
                verdict="grey",
                reason="allowlist",
                details=[ScoringDetail(check="allowlist", points=0, reason="IP в белом списке")],
                country=(country_hint or "").upper(),
                city="",
            )

        def punish(key: str, triggered: bool, why: str, code: str) -> None:
            if not triggered or any(item.check == key for item in details):
                return
            current = rule(filters, key)
            if current["mode"] == "off":
                return
            add(key, current["points"], why, code)

        def mark_tor() -> None:
            if any(item.check == "tor" for item in details):
                return
            add("tor", AUTOBAN, "Tor", "tor")

        if not _in_app(ua):
            for token in HEADLESS:
                if token in ua_low:
                    add("headless", AUTOBAN, f"Автоматизация в UA: {token}", "headless")
                    break
            for bot in lists.get("user_agents_block"):
                if bot.lower() in ua_low:
                    add("bot_ua", AUTOBAN, f"Бот в UA: {bot}", "bot_user_agent")
                    break

        if ip and google_crawlers.is_crawler(ip):
            add("google_crawler", AUTOBAN, "IP Google AdsBot или crawler", "google_crawler")
        elif ip and ip_range_checker.is_blocked(ip):
            add("ip_range", AUTOBAN, "IP в диапазоне краулера или датацентра", "ip_range_blocked")

        geos = [g.upper() for g in (geos or []) if g]
        ipinfo = None

        def apply_asn(value: str) -> None:
            asn = re.sub(r"\D", "", str(value or ""))
            if not asn:
                return
            if asn in {item.strip() for item in lists.get("vpn_asn")}:
                punish("vpn", True, f"Сеть VPN {asn}", "vpn")
            if asn in {item.strip() for item in lists.get("asn_block")} and not any(item.check == "asn_block" for item in details):
                add("asn_block", AUTOBAN, f"ASN {asn} — датацентр", "asn_blocked")

        def apply_geo() -> None:
            if geos and country and country not in geos and not any(item.check == "geo" for item in details):
                add("geo", AUTOBAN, f"Страна {country} вне гео кампании", "geo_miss")

        def finish() -> ScoringResult:
            verdict = "white" if total >= threshold else "grey"
            final_reason = reason
            if verdict == "grey":
                final_reason = reason if total == 0 else (reason or "below_threshold")
                if total == 0:
                    final_reason = "ok"
            return ScoringResult(
                score=total,
                verdict=verdict,
                reason=final_reason or "ok",
                details=details,
                country=country,
                city=city,
                isp=ipinfo.isp if ipinfo else "",
            )

        apply_asn(asn_hint)
        apply_geo()

        langs = rule(filters, "language")["langs"]
        seen = browser_langs(accept_language)
        punish(
            "language",
            bool(langs and seen and not any(item in langs for item in seen)),
            f"Язык {', '.join(seen)} не из списка",
            "language",
        )
        punish("referer", bad_referer(referer), "Открыто из рекламного кабинета", "ads_referer")
        punish("http_referer", insecure_referer(referer), "Сканер пришёл по http", "http_referer")
        punish("empty_lang", not seen, "Нет языка браузера", "empty_lang")
        punish(
            "velocity",
            recent_hits >= rule(filters, "velocity")["limit"],
            f"С этого IP уже {recent_hits} заходов",
            "velocity",
        )

        if total < threshold:
            ipinfo = await ipinfo_client.lookup(ip)
            if ipinfo:
                country = ipinfo.country or country
                city = ipinfo.city or city
                if ipinfo.tor:
                    mark_tor()
                punish("vpn", bool(ipinfo.vpn or ipinfo.proxy), "VPN или прокси", "vpn")
                punish("hosting", bool(ipinfo.hosting), f"Хостинг ({ipinfo.org})", "hosting")
                apply_asn(ipinfo.asn or asn_hint)

            ipqs = await ipqs_client.lookup(ip)
            if ipqs and ipqs.success:
                country = ipqs.country_code or country
                city = ipqs.city or city
                if ipqs.tor:
                    mark_tor()
                punish("vpn", bool(ipqs.vpn or ipqs.proxy), "VPN или прокси", "vpn")
                dirty = bool(ipqs.bot_status or ipqs.is_crawler or ipqs.fraud_score >= 80)
                punish("ipqs", dirty, f"Грязный IP, fraud {ipqs.fraud_score}", "ipqs_fraud")

            apply_geo()

            city_hit = False
            if city:
                for item in lists.get("cities_block"):
                    if item.lower() == city.lower():
                        city_hit = True
                        break
            punish("city", city_hit, f"Город модерации: {city}", "city")

            isp_hit = False
            if ipinfo and ipinfo.isp:
                isp_low = ipinfo.isp.lower()
                for provider in lists.get("isp_block"):
                    if provider.lower() in isp_low:
                        isp_hit = True
                        break
            punish("isp", isp_hit, f"Провайдер {ipinfo.isp if ipinfo else ''}", "isp")

            if js_metrics:
                self._js_points(js_metrics, ipinfo, add, filters)

        if total < threshold and rule(filters, "cloaker")["mode"] != "off":
            try:
                remote = await cloaker_client.check(
                    ip=ip,
                    user_agent=ua,
                    accept_language=accept_language,
                    referer=referer,
                    country=country,
                    asn=asn_hint,
                )
            except Exception:
                remote = CLOAKER_WHITE
            if remote == CLOAKER_WHITE:
                add("cloaker_api", AUTOBAN, "Внешний клоак сказал не человек", "cloaker_api")

        return finish()

    def _js_points(self, data: dict, ipinfo, add, filters: dict) -> None:
        webgl = data.get("webgl") or {}
        renderer = f"{webgl.get('vendor', '')} {webgl.get('renderer', '')}".lower()
        if filters.get("gpu", True) and renderer.strip():
            for gpu in lists.get("gpu_block"):
                if gpu.lower() in renderer:
                    add("webgl", AUTOBAN, f"Видеокарта эмулятора: {gpu}", "emulator_gpu")
                    break

        honey = data.get("honeyfield") or {}
        if honey.get("filled"):
            add("honeyfield", AUTOBAN, "Заполнено скрытое поле", "honeypot")

        accel = data.get("accelerometer") or {}
        samples = int(accel.get("samples") or 0)
        deviation = float(accel.get("averageDeviation") or -1)
        if samples > 4 and 0 <= deviation < 0.08:
            add("static_device", weight(filters, "static"), f"Устройство неподвижно ({samples} замеров)", "static")

        inp = data.get("input") or {}
        if int(inp.get("mouseClicks") or 0) > 0 and int(inp.get("touchEvents") or 0) == 0:
            add("mouse_no_touch", weight(filters, "mouse"), "Мышь без касания", "mouse")

        battery = data.get("battery") or {}
        if battery.get("level") == 1.0 and battery.get("chargingTime") == 0:
            add("fake_battery", weight(filters, "battery"), "Батарея как у эмулятора", "battery")

        js_tz = data.get("timezone") or ""
        ip_tz = ipinfo.timezone if ipinfo else ""
        if js_tz and ip_tz and compare_timezones(js_tz, ip_tz) > 2:
            add("timezone", weight(filters, "timezone"), f"Часовой пояс {js_tz} против {ip_tz}", "timezone")
        elif js_tz in {"Etc/UTC", "UTC", "Etc/GMT"}:
            add("timezone", weight(filters, "timezone"), f"Подозрительный пояс {js_tz}", "timezone")


scoring = WebScoring()
