# web-klo

Своя клоака для оффер-сайтов. Режет ботов, датацентры, краулеры и out-of-geo. Пускает живых и in-app браузеры (Facebook / Instagram / TikTok).

Контракт как у Clover:

- **grey** с `/` → 302 на same-host `/go` (UTM/fbclid сохраняются, не обязательны); на `/go` — HTML с кнопкой на оффер
- **white** → `ind-w.html` или редирект на safe URL
- **challenge** → короткий JS-пробник, потом решение

Clover на тех же доменах пропускал 0.6–3% на блек. Здесь скоринг пропускной: белый только если score ≥ порога кампании (по умолчанию 70). VPN сам по себе не банит.

## Состав

```
engine/    FastAPI: /v1/decide, /v1/collect, админка /admin
dropin/    index.php вместо Clover + tracker.js
worker/    Cloudflare Worker на зоне оффера
```

Взято из ваших реп: IPQS/IPinfo, CIDR Google-краулеров, js-tracker, honeypot-пути, идея панели. Выкинуто: Play Integrity, обязательный Android, `X-Client-Secret`, стоп-лист западных стран из APK-кло.

## Быстрый старт

```bash
cd web-klo
cp .env.example .env
# пропиши ENGINE_SECRET, ADMIN_PASSWORD, ключи IPQS/IPinfo
python3 -m venv .venv && source .venv/bin/activate
pip install -r engine/requirements.txt
WEBKLO_DATA="$PWD/data" uvicorn --app-dir engine app:app --host 0.0.0.0 --port 8088
```

Админка: `http://127.0.0.1:8088/admin`

Создай кампанию: slug, домен (`nars-cosmetics.us`), оффер URL, гео `US`, вайт = `ind-w.html`.

## Замена Clover на origin

1. `index.php` Clover переименовать в `index.php.clover`
2. Залить `dropin/index.php` и `dropin/tracker.js` рядом с `ind-w.html`
3. В PHP или в env origin:

```
KLO_ENGINE=https://твой-движок
KLO_KEY=тот-же-ENGINE_SECRET
KLO_CAMPAIGN=           # пусто = домен из Host
```

Если движок недоступен — показываем вайт, оффер не светим.

## Cloudflare Worker

На зоне оффера (оранжевое облако):

```bash
cd worker
wrangler secret put ENGINE_SECRET
# wrangler.toml: ENGINE_URL, при необходимости ORIGIN_URL для вайта
wrangler deploy
```

Worker сам ходит в `/v1/decide`. PHP на origin тогда не обязателен.

## Как крутить, чтобы не повторить Clover

1. Первая кампания — один домен, Clover лежит рядом как откат.
2. Порог 70, challenge включён.
3. Смотри «Почему вайт» на пульте. Если режет живых — ослабь один фильтр, не все сразу.
4. Panic на кампании = 100% вайт без разбора.

Жёсткий бан (100): honeypot, бан-лист, bot UA, headless, DC ASN, CIDR краулеров, IPQS bot, чужое гео.

Мягкие баллы: VPN 20, proxy 25, hosting 35, fraud 40–60, desktop UA 15.

## API

`POST /v1/decide`  
Заголовок `X-Klo-Key`.

```json
{
  "host": "nars-cosmetics.us",
  "ip": "1.2.3.4",
  "user_agent": "Mozilla/5.0 ...",
  "query": { "utm_source": "fb" }
}
```

Ответ: `verdict` / `action` / `url` / `score` / `reason`.
