# web-klo — web offer cloak

Date: 2026-10-30  
Status: approved

## Problem

Clover on live offer domains passes 0.6–3.4% to black. The engine is a black box and deny-by-default. We already have scoring, lists, IPQS/IPinfo, JS tracker, CF worker, and a panel — all built for Play APK, not ads landers.

## Product

Own web cloak for offer sites. Same contract as Clover:

- **grey / black** → 302 to offer (append inbound query/UTM)
- **white** → local `ind-w.html` or redirect to safe URL
- **challenge** → short JS probe, then decide

Cut bots, datacenters, crawlers, headless, out-of-geo. Pass residential humans and in-app browsers (Facebook / Instagram / TikTok).

## What we reuse vs drop

Reuse: scoring idea, IPQS/IPinfo clients, IP ranges, JS tracker, honeypot paths, CF worker skeleton, panel information architecture.

Drop: Play Integrity, `X-Client-Secret`, mandatory Android UA, Pixel/codename lists, `ANGLE` in GPU list (kills real Chrome), western `countries_block.txt` from APK klo, hard-ban on VPN, hard-ban on New York/London.

## Topology

```
ad click → offer domain
  ├─ CF Worker (if orange-cloud): panic, honeypot, obvious bots → else /v1/decide
  └─ origin index.php (Clover replacement): POST /v1/decide
       grey      → 302 offer
       white     → include ind-w.html
       challenge → HTML + tracker → POST /v1/collect → 302
```

Engine + admin run on one VPS. Each offer origin only gets `index.php` + existing white page.

## Decision API

`POST /v1/decide`  
Auth: `X-Klo-Key`  
Body: campaign/host, ip, ua, language, headers, query, optional js_metrics.

Response:

```json
{
  "request_id": "…",
  "verdict": "grey|white|challenge",
  "action": "redirect_offer|show_white|redirect_white|challenge",
  "url": "https://…",
  "score": 12,
  "reason": "ok",
  "campaign": "nars-cosmetics.us"
}
```

Engine down → white (keep offer off bots). IPQS/IPinfo down → fail-open (do not kill the click).

## Scoring (pass-first)

Score starts at 0. White if `score >= campaign.threshold` (default 70). `AUTOBAN = 100`.

Hard (100): honeypot, banned IP, bot UA, headless, DC ASN, IP in crawler CIDR, IPQS `bot_status`, campaign geo miss, honeyfield filled.

Soft (stack): VPN 20, proxy 25, Tor 80, hosting 35, IPQS fraud 40–60, city 12, timezone drift 15, desktop UA 15, mouse-without-touch 20.

In-app UA (`FBAN`, `FB_IAB`, `Instagram`, `TikTok`) never matches bot list.

Mid-band `[threshold - 20, threshold)` without JS → challenge, not white.

## Campaign

slug, domain, offer_url, white_mode (`local_html` | `redirect`), white_url, geos[], threshold, challenge_enabled, panic, enabled, filter toggles.

Empty geos = all countries allowed (except explicit global blocks).

## Admin

Same desk as the old panel, wired to this engine: live stats, campaigns CRUD, logs with reason, lists, bans, per-campaign panic.

## Rollout

Ship engine + PHP + worker. First live swap: one domain, Clover kept as rollback (`index.php.clover`). Then loosen one filter at a time against logs.
