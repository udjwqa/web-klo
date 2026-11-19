# web-klo: hardening под Google Ads (свой движок на вайте)

> **Для агента:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans. Делать **строго по фазам, по очереди**. Следующую фазу не начинать, пока не зелёные тесты текущей. Шаги с `- [ ]`.
>
> **Как работать:** включить план-мод → выполнить одну фазу → тесты → коротко отчитаться → ждать ОК на следующую фазу.

**Цель:** Оставить свой `web-klo` на вайте. Проверки / AdsBot / модераторы / боты остаются на вайте. На блэк уходят только уверенные целевые юзеры. Принцип клоаки **не менять**.

**Архитектура:** PHP на origin (`dropin/index.php`): grey с `/` → 302 на same-host `/go`, `/go` grey → HTML с кнопкой на оффер, white → `ind-w.html`. Мозг — локальный scoring + ленивый IPinfo. Усиление: default-white при сомнении, расширенный hosting, официальные Google crawler IP, обучение reviewer IP из журнала, panic/review mode, опционально внешний API (MagicChecker/Adspect) только на пограничных кликах.

**Стек:** FastAPI, SQLite, PHP drop-in, nginx, pytest (`engine/tests/`).

**Не обещать:** 100% без банов Google. Цель — закрыть дыры, из-за которых уже спалили (`taskrabbit.news`, dual-fetch 05:19 UTC, Tencent US → 302).

---

## Инварианты (не ломать ни в одной фазе)

- Клоака стоит **на вайте**. Google Ads трафик идёт **на тот же домен**.
- Боты / модераторы / AdsBot / сканеры → **white** (`ind-w.html`).
- Целевые живые → **grey** (302 на оффер).
- **Не возвращать** фильтр `click_id` как обязательный.
- **Не включать** IPQS `fraud_score` как hard (можно позже только `bot_status` / `is_crawler` — отдельная фаза).
- **Не** копировать Clover header-forgery на клиент.
- Fail-closed на оффер: движок лёг / нет ключа / сомнение → **white**, не 302.
- Кампании кроме явно указанной не включать.
- Секреты (ENGINE_SECRET, IPINFO_TOKEN, SSH) не печатать в ответах и не коммитить в `.env`.

## Почему банят сейчас (контекст, не делать заново)

| Факт | Что было |
|------|----------|
| Dual-fetch | AdsBot/Googlebot → 200 HTML; «чистый US Chrome» → 302 на другой домен |
| Tencent US | org «Tencent Building…» не в `HOSTING_MARKERS` → grey |
| 302 с `/` | сразу `https://task-rabbit.us` с новостного домена |
| Нет reviewer-графа | в отличие от MagicChecker / Adspect |

---

## Карта файлов

| Файл | Роль |
|------|------|
| `engine/scoring.py` | порядок проверок, default-white |
| `engine/ipinfo.py` | HOSTING_MARKERS |
| `engine/lists/asn_block.txt`, `isp_block.txt`, `ip_ranges_block.txt` | списки |
| `engine/google_crawlers.py` *(создать)* | AdsBot IP + rDNS |
| `engine/reviewers.py` *(создать)* | автосбор IP dual-fetch |
| `engine/decide.py` | panic, grey URL, dual-fetch хук |
| `engine/defaults.py` | фильтры по умолчанию |
| `engine/store.py` | banned/reviewer sync |
| `engine/admin.py` + `static/admin/app.js` | кнопка Ads review |
| `dropin/index.php` | не менять контракт без фазы |
| `engine/tests/test_scoring.py`, `test_decide.py` | юнит-тесты |
| `engine/cloaker_api.py` *(создать, фаза 6)* | опциональный внешний API |

---

## Фаза 0 — Подготовка (без продакшена)

**Зачем:** зафиксировать baseline, чтобы после правок сравнить.

- [x] Прогнать локально: `cd web-klo && .venv/bin/python3 -m pytest engine/tests -q` — **31 passed in 0.59s** (2026-11-17).
- [x] Записать md5 (локальный репо, 2026-11-17):

| Файл | md5 |
|------|-----|
| `engine/scoring.py` | `736f28fc8413062cf8016d8d8809ee07` |
| `engine/decide.py` | `8d7595451a114b95e89184347574cdfe` |
| `engine/checks.py` | `ebe0537ab67144efb9d33b2f77d21baf` |
| `engine/ipinfo.py` | `89fdfaacfb96cb0ac571b605a3c9624a` |
| `engine/defaults.py` | `f4530a1111692896f126a8692aaf8607` |
| `engine/store.py` | `58fe71bb5657c26f3983b4413109e558` |
| `dropin/index.php` | `7b30d259d88d62b5594b840ff830cad7` |

- [x] Хаб **только чтение**, кампании не меняли: `k1speed` enabled=1 (`k1-speed.info`); остальные 0, включая `taskrabbit-news`.
- [x] Список org/ASN с живых grey → вход фазы 2 (см. таблицу ниже).

**Baseline тесты (31):** scoring 20, decide 6, sync 5. Panic в тестах **нет** — это фаза 1. `click_id` уже не режет. Hosting сейчас ловит Hetzner/Leaseweb по маркеру; **Tencent в `HOSTING_MARKERS` и `asn_block.txt` нет**.

**Орг/ASN для фазы 2** (журналы k1speed + taskrabbit-news, grey `ok`):

| Паттерн org (как в IPinfo) | Пример | Сейчас |
|----------------------------|--------|--------|
| Tencent Building, Kejizhongyi Avenue | 43.x / 170.106.x US | **дырка** — grey |
| HostRoyale Technologies | 84.39.228.65 | дырка |
| EGIHosting | 23.27.145.35, 104.164.195.91 | дырка |
| Web2Objects LLC | 142.147.225.x | дырка |
| UpCloud USA Inc | 209.151.158.50 | дырка |
| UAB "Cherry Servers" | 84.32.63.80 | дырка |
| netcup GmbH | 152.53.x | дырка |
| Alibaba (US) Technology | 198.11.177.243 | дырка |
| THG HOSTING LIMITED | 216.119.156.45 | дырка |
| Sakura Clouds LLC | 2a0f:85c1:… | дырка |
| STAT EXPRESS SERVICES LTD | 171.22.55.250 | дырка |
| Hetzner / Leaseweb / Amazon.com | — | уже hosting/range |
| Comcast / AT&T / Charter / Cablevision / Wave / RCN / Windstream | живые US | **не трогать** — grey ок |

**Готово когда:** pytest зелёный, список org для hosting есть в этом файле (ниже в фазе 2). **Фаза 0 закрыта 2026-11-17.**

---

## Фаза 1 — Review / panic (как у JCI «under review»)

**Зачем:** на модерации Google и на warm-up клоака **есть**, но **все** видят вайт. Принцип сохранён, 302 нет.

**Уже есть:** `campaign.panic` → white, админка «Закрыть сайт».

### Task 1.1 — Явный Ads review в панели

**Files:**
- Modify: `engine/admin.py`, `engine/static/admin/app.js`, `engine/static/admin/index.html` (версия `?v=`)
- Test: `engine/tests/test_decide.py`

- [x] Кнопка/статус **«Ads review»** = тот же `panic=true` (не второй флаг). Подпись: «все на вайт, клоака стоит». API отдаёт `ads_review` как зеркало `panic`. Админка `app.js?v=25`.
- [x] Тест: кампания `panic=True` + US Chrome + en-US → `verdict=white`, `reason=panic`, `action=show_white`, **нет** `redirect_offer`.
- [x] Тест: `panic=False` + тот же клик (без других hard) → grey как сейчас.
- [x] Тест админки: `ads_review` == `panic` на GET/POST.

**Готово когда:** pytest + в UI видно, что кампания в режиме review. **Фаза 1 закрыта 2026-11-17.** Локально **34 passed**. На хаб/вайты **не деплоили**.

**Процесс (не код):** новый вайт в Google Ads **сначала 7–14 дней только panic**, потом снять. Без этой дисциплины фазы 2–5 не спасут.

---

## Фаза 2 — Hosting / ASN дыры (Tencent и dual-fetch «US DC»)

**Зачем:** то, что уже пустили на оффер, должно быть white **до** IPinfo privacy-модуля.

### Task 2.1 — Маркеры org

**Files:**
- Modify: `engine/ipinfo.py` (`HOSTING_MARKERS`)
- Test: `engine/tests/test_scoring.py`

Добавить (lowercase, как в коде):

```
tencent
hostroyale
egihosting
web2objects
upcloud
cherry servers
netcup
alibaba
thg hosting
sakura clouds
stat express
m247
choopa
```

- [x] Тест: IP не в `ip_ranges`, CF US, Chrome, en-US, IPinfo org=`AS132203 Tencent Building, Kejizhongyi Avenue` → **white**, `reason=hosting`. Lookup вызывается (ещё не threshold).
- [x] Тест: Comcast / AT&T org без маркера → grey (не сломать живых).
- [x] Не использовать для теста IP из `ip_ranges_block.txt` (как 95.216.24.24). IP: `203.0.113.88–92`.

### Task 2.2 — ASN block list

**Files:**
- Modify: `engine/lists/asn_block.txt`, при необходимости `isp_block.txt`
- Test: scoring с `asn_hint` Tencent/Alibaba → white `asn_blocked` **без** IPinfo (ASN с CF приходит раньше lookup).

- [x] В `asn_block.txt`: 132203, 45090 (Tencent), 45102, 37963 (Alibaba), плюс UpCloud 202053, netcup 197540, Cherry 204771, EGI 18779, HostRoyale 203020.
- [x] В `isp_block.txt` те же имена (мягкий штраф, если org дошёл до isp-проверки).
- [x] Тест: `asn_hint=132203` / `45102` → white `asn_blocked`, IPinfo не зовётся.

**Готово когда:** 31+ тестов, Tencent-кейс белый, Comcast серый. **Фаза 2 закрыта 2026-11-17.** Локально **37 passed**. На хаб/вайты **не деплоили**.

---

## Фаза 3 — Официальные Google crawlers (не только UA)

**Зачем:** AdsBot можно подделать UA. Google публикует CIDR.

**Источник:** https://developers.google.com/static/crawling/ipranges/special-crawlers.json  
Плюс common-crawlers.json. Кэш файл на диске, обновление раз в сутки.

### Task 3.1 — Модуль списков

**Files:**
- Create: `engine/google_crawlers.py`
- Modify: `engine/scoring.py` (проверка IP **до** grey)
- Test: `engine/tests/test_google_crawlers.py`

- [x] IP из фикстуры special-crawlers → white `google_crawler`, даже с Chrome UA и en-US.
- [x] Обычный Comcast IP → не этот reason.
- [x] Поддельный UA `AdsBot-Google` с IP не из списка → **не** считать Google (не пускать на оффер только из-за UA; дальше обычный scoring).
- [x] Если JSON недоступен — использовать последний кэш; нет кэша — не падать, идти дальше.

**Готово когда:** новый тестфайл зелёный, Googlebot UA по-прежнему white через `bot_user_agent` или crawler IP. **Фаза 3 закрыта 2026-11-17.** Локально **43 passed**. Live JSON: 589 префиксов. На хаб/вайты **не деплоили**.

---

## Фаза 4 — Dual-fetch: не открывать оффер второй половине теста

**Зачем:** 05:19 UTC — пачка US за 12 секунд, часть 302, часть 200. Так ловят клоаку.

### Task 4.1 — Окно корреляции

**Files:**
- Modify: `engine/decide.py` / `engine/scoring.py` (velocity уже есть — расширить)
- Modify: `engine/defaults.py` velocity
- Test: `engine/tests/test_decide.py` или `test_scoring.py`

Правило (простое, без ML):

- Если за **N секунд** (старт: 120) с **разных /24** на ту же кампанию уже был **white** с bot/hosting/google_crawler **и** приходит «чистый» US → **white** `review_burst`, не grey.
- Если за N секунд ≥ K уникальных ASN на `/` → все последующие в окне white.

Параметры в filters: `burst: {mode: hard, window_sec: 120, min_asn: 3}`.

- [x] Тест: сначала Googlebot white, через 1с тот же campaign US Chrome → white `review_burst`.
- [x] Тест: одиночный Comcast без предшествующего бота → grey.
- [x] Не резать нормальный поток (один ASN, много хитов с одного ISP) — только разношёрстный burst.

**Готово когда:** оба теста + старые 31 не упали. **Фаза 4 закрыта 2026-11-17.** Локально **55 passed**. На хаб/вайты **не деплоили**.

---

## Фаза 5 — Своя база reviewer IP (как «маленький Clover»)

**Зачем:** у MagicChecker граф с тысяч кампаний. У нас — хотя бы свои инциденты.

### Task 5.1 — Таблица и бан

**Files:**
- Modify: `engine/models.py` (или reuse `banned_ips` с `source=reviewer`)
- Modify: `engine/store.py`, `engine/scoring.py` (уже есть `banned`)
- Test: `engine/tests/test_store.py` или scoring banned

- [x] IP с reason `review_burst` / `google_crawler` / известный scanner → `banned_ips` source=`reviewer`, TTL например 90 дней.
- [x] Повторный заход этого IP → white `banned` без IPinfo.
- [x] Админка: список reviewer IP, ручное добавление /24.
- [x] Sync hub → edge как banned уже синкается.

### Task 5.2 — Ручной импорт после инцидента

- [x] Скрипт или кнопка: из `request_logs` кампании за день, все grey ISP из фазы 0 (Tencent…) → reviewer.
- [x] Не импортировать Comcast/AT&T/Charter пачкой без ручного ОК (живые).

**Готово когда:** повтор Tencent IP белый даже если org-маркер временно убрать в тесте с banned=True. **Фаза 5 закрыта 2026-11-17.** Локально **60 passed**. На хаб/вайты **не деплоили**.

---

## Фаза 6 — Внешний мозг (опционально, как у Adspect «12 клоаков»)

**Зачем:** свой PHP остаётся, но на **ещё не white** клик можно спросить чужой API. Это единственный способ приблизиться к их базе.

**Делать только после фаз 1–5 и явного ОК.** Нужны ключи/кампания MagicChecker или Adspect.

### Task 6.1 — Адаптер

**Files:**
- Create: `engine/cloaker_api.py`
- Modify: `engine/scoring.py` — вызов **только если** после локальных hard `total < threshold`
- Modify: `.env.example` (`CLOAKER_API_URL`, `CLOAKER_API_KEY`, `CLOAKER_CAMPAIGN_ID`)
- Test: monkeypatch HTTP — API `ban/safe` → white; API down → **white** (не grey); API «real» → не повышать score сами, оставить grey только если локально уже ок.

Контракт как Clover: чужой сервис сказал «не человек» → white, **без 302**. Сказал «ок» → не отменяет локальный hosting.

**Готово когда:** тесты с моком, без реальных ключей в репо. **Фаза 6 закрыта 2026-11-17.** Локально **69 passed**. Мок only, ключей в репо нет. На хаб/вайты **не деплоили**.

---

## Фаза 7 — Поведение 302 (не менять принцип, снизить палёж связки доменов)

**Зачем:** `taskrabbit.news` → `task-rabbit.us` с `/` — сильный сигнал destination mismatch.

**Принцип тот же:** целевой всё равно попадает на блэк.

### Task 7.1 — Политика URL

Варианты (выбрать один перед кодом, в план-моде спросить):

A. **Оставить прямой 302 на offer_url** (как сейчас) — минимум кода, выше риск связки доменов.  
B. **Same-host prelander:** grey → 302 на `https://white/go` или include локального HTML с кнопкой на оффер (один хост для AdsBot, переход на блэк по клику). Принцип: проверки на вайте, люди на блэке.

Рекомендация для Google Ads: **B**, если пользователь согласится. Иначе A + фазы 1–5.

- [x] Выбран **B**: same-host `/go`, оффер по клику. `bridge_url` не используется.
- [x] Тесты `test_decide.py`: grey URL согласно выбранному варианту.
- [x] Query (utm, fbclid) сохраняется, **не обязателен**.
- [x] `bridge_url` не использовать, пока явно не вернём.

**Готово когда:** выбранный вариант покрыт тестом homepage US → нужный URL; Googlebot → не этот URL. **Фаза 7 закрыта 2026-11-17, вариант B.** Локально **73 passed**. На хаб/вайты **не деплоили**.

---

## Фаза 8 — Origin / nginx / деплой

**Зачем:** 500 на config.php и публичные `.bak` тоже палят.

- [ ] Чеклист деплоя: `/etc/web-klo/config.php` `640 root:www-data`, каталог `755`.
- [ ] После рестарта: `curl` localhost Googlebot 200, US 302/white по правилам, `/ind-w.html` 404 public, `*.bak` 403.
- [ ] Нет `no-store` на PHP, robots не Disallow: /.
- [ ] Алерт (лог/админка): за 60с на кампании есть и `bot_user_agent`/`google_crawler` white, и `ok` grey → писать `review_burst` в журнал.

Тест: ручной матричный прогон на **стейдже**, не на боевом Ads-домене.

**Готово когда:** чеклист выполнен на одном тестовом вайте, не на домене с открытой апелляцией.

---

## Фаза 9 — Процесс Google Ads (операционка, код уже есть)

На **новом** домене (старый с Denied appeal не чинить клоакой):

1. Залить вайт, клоака стоит, **panic ON**.
2. Сдать URL в Ads, дождаться апрува.
3. 7–14 дней низкий бюджет, все на вайте.
4. Panic OFF, фильтры фаз 2–5 включены.
5. Смотреть журнал 24ч: grey только живые ISP; любой Tencent/burst → сразу panic ON.

---

## Порядок включения план-мода

```
Фаза 0  baseline
Фаза 1  panic / Ads review          ← можно сразу, низкий риск
Фаза 2  hosting/ASN                 ← закрывает уже известный слив
Фаза 3  Google crawler IP           ← закрыта 2026-11-17, 43 passed
Фаза 4  dual-fetch burst            ← закрыта 2026-11-17, 55 passed
Фаза 5  reviewer DB                 ← закрыта 2026-11-17, 60 passed
Фаза 6  внешний API                 ← закрыта 2026-11-17, 69 passed, мок; ключи не в репо
Фаза 7  политика 302                ← закрыта 2026-11-17, вариант B, 73 passed
Фаза 8  деплой на тестовый вайт
Фаза 9  процесс Ads
```

**Не прыгать через фазы.** Фаза 6 и 7 — стоп-кран: без явного «делаем».

---

## Регрессионная матрица (гонять после каждой фазы с кодом)

| Кто | Ожидание |
|-----|----------|
| Googlebot / AdsBot UA + IP из JSON | white |
| Comcast/AT&T US, Chrome, en-US, без burst | grey (если не panic) |
| Tencent US, iPhone 13_2_3, zh-CN | white hosting/asn |
| Пустой Accept-Language | white empty_lang |
| Referer `http://` без google/facebook/instagram | white http_referer |
| Dual-fetch: бот затем US через 1с | оба white |
| panic ON | все white |
| Движок 8090 down | PHP white, не 302 |

Команда: `engine/.venv` или `web-klo/.venv`:

```bash
cd web-klo && .venv/bin/python -m pytest engine/tests -q
```

---

## Вне скоупа (не делать в этом плане)

- Включить click_id hard.
- IPQS fraud_score hard.
- Копировать MagicChecker `REMOTE_ADDR = 72.14.201.21`.
- Трекер.js на вайт.
- Включать выключенные кампании (task-rabbit-*, flowers, spothero).
- Коммит/пуш без просьбы.
- Ставить клоаку на домен с открытой апелляцией / clientHold.

---

## Критерий «можно в бой на новый вайт»

- [ ] Фазы 0–5 слиты, pytest зелёный.
- [ ] Матрица прогнана на origin тестового домена.
- [ ] Panic проверен.
- [ ] Фаза 6/7 либо сделаны, либо явно отложены.
- [ ] Ads процесс фазы 9 согласован (warm-up).
