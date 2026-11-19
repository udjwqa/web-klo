const app = document.getElementById("app");

const NAV = [
  ["desk", "Сейчас"],
  ["campaigns", "Сайты"],
  ["logs", "Журнал"],
  ["more", "Списки"],
];

const MODES = [
  ["soft", "Мягко", 100, "На вайт только обязательное: боты, сети, Tor и чужая страна. Баллы человека не дотягивают."],
  ["normal", "Обычно", 70, "Баллы выкидывают, когда их набирается 70. Один VPN или хостинг сами не выкидывают."],
  ["strict", "Строго", 40, "Порог низкий: хостинг и грязный IP уже могут выкинуть. Живых будет меньше."],
];

const REASONS = {
  ok: "Живой, пускаем на оффер",
  below_threshold: "Подозрительно, но недостаточно, чтобы резать",
  bot_user_agent: "Бот или краулер",
  headless: "Это программа, не человек",
  geo_miss: "Не та страна",
  allowlist: "Ваш IP, всегда оффер",
  banned: "Этот IP запрещён",
  panic: "Ads review: все на вайт, клоака стоит",
  honeypot: "Сканер полез в ловушку",
  asn_blocked: "Сеть датацентра",
  ip_range_blocked: "Сеть Google или краулера",
  google_crawler: "IP Google AdsBot или crawler",
  review_burst: "Dual-fetch: бот уже был, чистый US тоже на вайт",
  cloaker_api: "Внешний клоак сказал не человек",
  vpn: "VPN",
  proxy: "Прокси",
  tor: "Tor",
  vpn: "VPN или сеть VPN",
  hosting: "Хостинг, не домашний интернет",
  language: "Язык браузера не из списка",
  ads_referer: "Открыто из рекламного кабинета",
  http_referer: "Сканер пришёл по http",
  velocity: "Слишком много заходов с одного IP",
  ipqs_fraud: "Грязный IP",
  desktop: "Компьютер, не телефон",
  city: "Город, где сидит модерация",
  isp: "Подозрительный провайдер",
  ipqs_high_fraud: "Очень грязный IP",
  ipqs_fraud: "Грязный IP",
  bot_detected: "Сервис пометил IP как бота",
  emulator_gpu: "Эмулятор",
  unknown_campaign: "Сайт не настроен",
  no_click_id: "Нет метки рекламного клика",
  empty_lang: "Нет языка браузера",
};

const PRESETS = {
  android: "Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36",
  facebook: "Mozilla/5.0 (iPhone; CPU iPhone OS 17_4 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148 [FBAN/FBIOS;FBAV/450.0.0.0]",
  bot: "Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)",
};

const CHECKS = [
  ["vpn", "VPN", "hard", 100, "off,points,hard", "VPN или прокси — сразу вайт. Так ревьюер с VPN не видит оффер."],
  ["ipqs", "Грязный IP", "off", 40, "off,points,hard", "Вторая база, IPQS. На Play резала живых. По умолчанию выключена."],
  ["hosting", "Хостинг", "hard", 100, "off,points,hard", "Датацентр вместо домашнего интернета. Сразу вайт."],
  ["language", "Язык", "off", 20, "off,points", "Список языков ниже. Пустой список — проверку не делаем."],
  ["empty_lang", "Нет языка", "hard", 100, "off,hard", "Пустой Accept-Language — сразу вайт. Так часто ходят сканеры."],
  ["referer", "Рекламный кабинет", "hard", 100, "off,hard", "Кабинет Google, Facebook или TikTok. Обычный клик с Facebook не трогаем."],
  ["http_referer", "Сканер по http", "hard", 100, "off,hard", "Реферер начинается с http:// и это не Google, Facebook или Instagram. Сразу вайт."],
  ["city", "Город", "points", 15, "off,points,hard", "Города вроде Mountain View. Баллы."],
  ["isp", "Провайдер", "points", 20, "off,points,hard", "Хостеры из списка. Баллы."],
  ["velocity", "Повторы с одного IP", "points", 40, "off,points,hard", "Сколько заходов за час терпим, потом баллы или вайт."],
  ["burst", "Dual-fetch пачка", "hard", 100, "off,hard", "Бот или хостинг уже были на вайте — следующий чистый US с другой сети тоже на вайт."],
  ["cloaker", "Внешний клоак", "hard", 100, "off,hard", "Спросить чужой API только если локально ещё серый. Бан/safe — вайт. API лёг — тоже вайт."],
];

const state = {
  view: "desk",
  me: false,
  error: "",
  stats: null,
  logs: [],
  feed: [],
  campaigns: [],
  lists: {},
  bans: [],
  allow: [],
  engine: null,
  editing: null,
  log: null,
  sim: null,
  advanced: false,
  range: "today",
  offer: "",
  logCampaign: "",
  logVerdict: "",
  logReason: "",
  logCountry: "",
  logQuery: "",
  logFrom: "",
  logTo: "",
  logTotal: 0,
  sheetTab: "summary",
};

function el(tag, attrs, ...kids) {
  const node = document.createElement(tag);
  if (attrs) {
    for (const [key, value] of Object.entries(attrs)) {
      if (value == null || value === false) continue;
      if (key === "class") node.className = value;
      else if (key.startsWith("on") && typeof value === "function") node.addEventListener(key.slice(2), value);
      else if (key === "checked" || key === "selected" || key === "value") node[key] = value;
      else node.setAttribute(key, value);
    }
  }
  for (const kid of kids.flat()) {
    if (kid == null || kid === false) continue;
    node.append(kid.nodeType ? kid : document.createTextNode(String(kid)));
  }
  return node;
}

async function api(path, options = {}) {
  const res = await fetch("/admin/api" + path, {
    credentials: "same-origin",
    headers: { "Content-Type": "application/json", ...(options.headers || {}) },
    ...options,
  });
  if (res.status === 401) {
    state.me = false;
    render();
    throw new Error("auth");
  }
  if (!res.ok) throw new Error("request failed");
  return res.json();
}

function readRule(raw, fallbackMode, fallbackPoints) {
  if (raw === false) return { mode: "off", points: fallbackPoints, langs: "", limit: 25, window_sec: 120, min_asn: 3 };
  if (raw && typeof raw === "object" && !Array.isArray(raw)) {
    return {
      mode: raw.mode || fallbackMode,
      points: raw.points == null ? fallbackPoints : raw.points,
      langs: (raw.langs || []).join(", "),
      limit: raw.limit || 25,
      window_sec: raw.window_sec || 120,
      min_asn: raw.min_asn || 3,
    };
  }
  return { mode: fallbackMode, points: fallbackPoints, langs: "", limit: 25, window_sec: 120, min_asn: 3 };
}

function modeOf(threshold) {
  if (threshold >= 95) return "soft";
  if (threshold >= 60) return "normal";
  return "strict";
}

function modeTitle(threshold) {
  const id = modeOf(threshold);
  return (MODES.find((item) => item[0] === id) || MODES[1])[1];
}

function reasonText(code) {
  return REASONS[code] || code || "—";
}

function saw(verdict) {
  if (verdict === "grey") return "Увидел оффер";
  if (verdict === "white") return "Увидел вайт";
  if (verdict === "challenge") return "Короткая проверка";
  if (verdict === "payment") return "Открыл оплату";
  return verdict || "—";
}

function pill(verdict) {
  return el("span", { class: "pill " + (verdict || "") }, saw(verdict));
}

async function boot() {
  try {
    await api("/me");
    state.me = true;
    await refresh();
  } catch (e) {
    if (!sessionStorage.getItem("klo_boot")) {
      sessionStorage.setItem("klo_boot", "1");
      location.replace(location.pathname);
      return;
    }
    sessionStorage.removeItem("klo_boot");
    document.body.textContent = "Не удалось открыть кабинет.";
    return;
  }
  sessionStorage.removeItem("klo_boot");
  render();
}

async function refresh() {
  const statsQuery = new URLSearchParams({ range: state.range || "today", campaign: state.offer || "" });
  const feedQuery = new URLSearchParams({ limit: "12", campaign: state.offer || "" });
  const logQuery = new URLSearchParams({
    limit: "150",
    count: "1",
    campaign: state.logCampaign || "",
    verdict: state.logVerdict || "",
    reason: state.logReason || "",
    country: state.logCountry || "",
    q: state.logQuery || "",
    date_from: state.logFrom || "",
    date_to: state.logTo || "",
  });
  const [stats, feed, logs, campaigns, lists, bans, allow, engine] = await Promise.all([
    api("/stats?" + statsQuery.toString()),
    api("/logs?" + feedQuery.toString()),
    api("/logs?" + logQuery.toString()),
    api("/campaigns"),
    api("/lists"),
    api("/bans"),
    api("/allow"),
    api("/engine"),
  ]);
  state.stats = stats;
  state.feed = feed;
  state.logs = Array.isArray(logs) ? logs : (logs.items || []);
  state.logTotal = Array.isArray(logs) ? logs.length : (logs.total || 0);
  state.campaigns = campaigns;
  state.lists = lists;
  state.bans = bans;
  state.allow = allow;
  state.engine = engine;
}

function shell(inner) {
  return el(
    "div",
    { class: "shell" },
    el(
      "aside",
      { class: "side" },
      el("div", { class: "mark" }, "Кабинет"),
      el("div", { class: "brand" }, "web-", el("span", null, "klo")),
      el("p", null, "Живой видит оффер. Бот и чужая страна видят вайт."),
      el("nav", null, NAV.map(([id, label]) =>
        el("button", {
          class: state.view === id ? "active" : "",
          onclick: () => { state.view = id; state.log = null; render(); },
        }, label)
      ))
    ),
    el("main", { class: "main" }, inner)
  );
}

function heading(title, text, extra) {
  return el("div", { class: "top" }, el("div", null, el("h1", null, title), text ? el("div", { class: "sub" }, text) : null), extra || null);
}

function metric(label, value, klass) {
  return el("div", { class: "card" }, el("div", { class: "k" }, label), el("div", { class: "v " + (klass || "") }, value));
}

function table(headers, rows, emptyText) {
  return el(
    "table",
    null,
    el("tr", null, headers.map((item) => el("th", null, item))),
    rows.length ? rows : el("tr", null, el("td", { colspan: String(headers.length) }, el("p", { class: "empty" }, emptyText || "Пока пусто.")))
  );
}

function field(label, input) {
  return el("label", { class: "field" }, el("span", null, label), input);
}

function offerSelect(value, onChange) {
  const select = el("select", null, el("option", { value: "", selected: value === "" }, "Все офферы"));
  (state.stats && state.stats.offers || state.campaigns || []).forEach((item) => {
    const slug = item.slug;
    const name = item.name || slug;
    if (!slug) return;
    select.append(el("option", { value: slug, selected: value === slug }, name));
  });
  select.addEventListener("change", () => onChange(select.value));
  return select;
}

function desk() {
  const stats = state.stats || { total: 0, grey: 0, white: 0, grey_pct: 0, reasons: [], series: [] };
  const offer = offerSelect(state.offer, async (value) => {
    state.offer = value;
    await refresh();
    render();
  });
  const range = el("select", null,
    el("option", { value: "today", selected: state.range === "today" }, "Сегодня"),
    el("option", { value: "7d", selected: state.range === "7d" }, "7 дней"),
    el("option", { value: "30d", selected: state.range === "30d" }, "30 дней")
  );
  range.addEventListener("change", async () => {
    state.range = range.value;
    await refresh();
    render();
  });
  return shell([
    heading("Сейчас", "Зелёная линия — оффер, охра — вайт. Срок и оффер переключаются сверху.", el("div", { class: "row" }, field("Оффер", offer), field("Срок", range))),
    el("div", { class: "metrics" },
      metric("Зашли", stats.total),
      metric("Увидели оффер", stats.grey, "g"),
      metric("Увидели вайт", stats.white, "a"),
      metric("Доля оффера", stats.grey_pct + "%", "g")
    ),
    el("div", { class: "grid2" },
      el("div", { class: "card" },
        el("div", { class: "k" }, state.range === "today" ? "По часам" : "По дням"),
        el("div", { class: "legend" }, el("span", null, el("i", { class: "swatch g" }), " Оффер"), el("span", null, el("i", { class: "swatch a" }), " Вайт")),
        lineChart(stats.series || [])
      ),
      el("div", { class: "card" },
        el("div", { class: "k" }, "Почему вайт"),
        stats.reasons && stats.reasons.length
          ? table(["Почему", "Сколько"], stats.reasons.map((item) => el("tr", null, el("td", null, reasonText(item[0])), el("td", null, item[1]))))
          : el("p", { class: "empty" }, "За этот срок на вайт никто не ушёл.")
      )
    ),
    el("div", { class: "card", style: "margin-top:14px" },
      el("div", { class: "k" }, "По дням, Москва"),
      el("p", { class: "empty" }, "Всего — заходы на рекламный домен. На оффер и на вайт — чем закончился каждый заход. Уникальные на оплату — разные IP, которые открыли страницу оплаты."),
      dayTable(stats)
    ),
    el("div", { class: "card", style: "margin-top:14px" },
      el("div", { class: "k" }, "Последние заходы"),
      state.feed.length
        ? table(["Когда", "Страна", "Что увидел", "Почему"], logRows(state.feed))
        : el("p", { class: "empty" }, "Кликов за этот срок нет.")
    ),
    probeCard(),
    sheet(),
  ]);
}

function dayTable(stats) {
  const days = stats.days || [];
  if (!days.length) return el("p", { class: "empty" }, "За эти дни заходов нет.");
  const rows = days.map((item) =>
    el("tr", null,
      el("td", null, item.day),
      el("td", { class: "offer-name" }, item.offer),
      el("td", { class: "num" }, item.total),
      el("td", { class: "num" }, item.uniqueOffer),
      el("td", { class: "num good" }, item.grey),
      el("td", { class: "num warn" }, item.white),
      el("td", { class: "num" }, item.offerPct + "%")
    )
  );
  rows.unshift(el("tr", { class: "total" },
    el("td", null, "Итого"),
    el("td", null, stats.campaignName || "Все офферы"),
    el("td", { class: "num" }, stats.total),
    el("td", { class: "num" }, stats.uniqueOffer || 0),
    el("td", { class: "num good" }, stats.grey),
    el("td", { class: "num warn" }, stats.white),
    el("td", { class: "num" }, (stats.grey_pct || 0) + "%")
  ));
  return el("div", { class: "day-scroll" }, table(
    ["День", "Оффер", "Всего", "Уникальные на оплату", "На оффер", "На вайт", "Доля оффера"],
    rows
  ));
}

function svgEl(name, attrs) {
  const node = document.createElementNS("http://www.w3.org/2000/svg", name);
  for (const [key, value] of Object.entries(attrs)) node.setAttribute(key, value);
  return node;
}

function lineChart(series) {
  if (!series.length) return el("p", { class: "empty" }, "Пока нечего рисовать.");
  const width = 640;
  const height = 240;
  const pad = 28;
  const max = Math.max(1, ...series.map((point) => Math.max(point.grey, point.white)));
  const xAt = (index) => pad + (index * (width - pad * 2)) / Math.max(1, series.length - 1);
  const yAt = (value) => height - pad - (value / max) * (height - pad * 2);
  const path = (key) => series.map((point, index) => xAt(index).toFixed(1) + "," + yAt(point[key]).toFixed(1)).join(" ");
  const svg = svgEl("svg", { viewBox: "0 0 640 240", class: "chart" });
  svg.append(
    svgEl("polyline", { points: path("grey"), fill: "none", stroke: "#1d5c3a", "stroke-width": "2.5", "pointer-events": "none" }),
    svgEl("polyline", { points: path("white"), fill: "none", stroke: "#8a5a12", "stroke-width": "2.5", "pointer-events": "none" })
  );
  series.forEach((point, index) => {
    svg.append(svgEl("circle", { cx: xAt(index), cy: yAt(point.grey), r: "3.5", fill: "#1d5c3a", "pointer-events": "none" }));
    svg.append(svgEl("circle", { cx: xAt(index), cy: yAt(point.white), r: "3.5", fill: "#8a5a12", "pointer-events": "none" }));
  });
  const step = series.length > 14 ? 5 : series.length > 8 ? 3 : 1;
  series.forEach((point, index) => {
    if (index % step !== 0 && index !== series.length - 1) return;
    const label = svgEl("text", { x: xAt(index), y: height - 8, "text-anchor": "middle", fill: "#6f675c", "font-size": "11" });
    label.textContent = point.label;
    svg.append(label);
  });
  const guide = svgEl("line", { y1: pad, y2: height - pad, stroke: "#1c1914", "stroke-opacity": "0.25", "pointer-events": "none" });
  guide.hidden = true;
  svg.append(guide);
  svg.append(svgEl("rect", { x: "0", y: "0", width: "640", height: "210", fill: "transparent" }));

  const tip = el("div", { class: "chart-tip" });
  tip.hidden = true;
  let pinned = -1;
  function nearest(event) {
    const box = svg.getBoundingClientRect();
    const x = ((event.clientX - box.left) / box.width) * width;
    let best = 0;
    let dist = Infinity;
    series.forEach((_, index) => {
      const gap = Math.abs(xAt(index) - x);
      if (gap < dist) {
        dist = gap;
        best = index;
      }
    });
    return best;
  }
  function show(index) {
    const point = series[index];
    tip.hidden = false;
    tip.replaceChildren(
      el("b", null, point.label),
      el("div", null, "Оффер  " + point.grey),
      el("div", null, "Вайт  " + point.white)
    );
    tip.style.left = (xAt(index) / width * 100) + "%";
    guide.setAttribute("x1", String(xAt(index)));
    guide.setAttribute("x2", String(xAt(index)));
    guide.hidden = false;
  }
  svg.addEventListener("mousemove", (event) => {
    if (pinned >= 0) return;
    show(nearest(event));
  });
  svg.addEventListener("mouseleave", () => {
    if (pinned >= 0) return;
    tip.hidden = true;
    guide.hidden = true;
  });
  svg.addEventListener("click", (event) => {
    const index = nearest(event);
    pinned = pinned === index ? -1 : index;
    if (pinned < 0) {
      tip.hidden = true;
      guide.hidden = true;
      return;
    }
    show(index);
  });
  return el("div", { class: "chart-wrap" }, svg, tip);
}

function campaigns() {
  const current = state.editing || state.campaigns[0] || null;
  if (!current) {
    return shell([
      heading("Сайты", "Здесь только то, что уже подключено. Новый сайт, оффер или вайт добавляю я."),
      el("div", { class: "card" }, el("p", { class: "empty" }, "Пока ничего не подключено.")),
    ]);
  }
  const picked = modeOf(current.threshold ?? 100);
  const geos = el("input", { value: (current.geos || []).join(", "), placeholder: "US" });
  let mode = picked;
  const modeBox = el("div", { class: "choice" });
  for (const [id, title, , text] of MODES) {
    modeBox.append(el("button", {
      type: "button",
      class: id === mode ? "on" : "",
      onclick: () => { mode = id; renderModes(); },
    }, el("b", null, title), el("small", null, text)));
  }
  function renderModes() {
    [...modeBox.children].forEach((node, index) => {
      node.className = MODES[index][0] === mode ? "on" : "";
    });
  }
  const rules = {};
  const checkRows = CHECKS.map(([key, title, fallbackMode, fallbackPoints, modes, hint]) => {
    const saved = readRule((current.filters || {})[key], fallbackMode, fallbackPoints);
    const allowed = modes.split(",");
    const select = el("select", null, ...allowed.map((item) =>
      el("option", { value: item, selected: saved.mode === item }, item === "off" ? "Выкл" : item === "points" ? "Баллы" : "Сразу вайт")
    ));
    const points = el("input", { type: "number", value: String(saved.points) });
    const extra = key === "language"
      ? el("input", { value: saved.langs, placeholder: "en, es" })
      : key === "velocity"
        ? el("input", { type: "number", value: String(saved.limit) })
        : key === "burst"
          ? el("input", { type: "number", value: String(saved.window_sec) })
          : null;
    rules[key] = { select, points, extra };
    return el("div", { class: "check" },
      el("div", null, el("b", null, title), el("small", null, hint)),
      select,
      points,
      extra
    );
  });
  const form = el("form", null,
    el("div", { class: "facts" },
      fact("Сайт", current.domain || "домен не задан"),
      fact("Оффер", current.offer_url || "—"),
      fact("Мост", "same-host /go, оффер по клику"),
      fact("Вайт", current.white_url || "страница ind-w.html"),
      fact("Платёжка", current.offer_url || "—"),
      fact("Ads review", current.panic ? "вкл — все на вайт, клоака стоит" : "выкл — живые на оффер")
    ),
    field("Страны, откуда пускаем на оффер", geos),
    el("div", { class: "section" }, "Порог баллов"),
    modeBox,
    el("p", { class: "empty" }, "Баллы выкидывают на вайт, только когда их сумма доходит до порога. «Сразу вайт» срабатывает само. Боты, сети Google, Tor и чужая страна режутся всегда."),
    el("div", { class: "section" }, "Проверки этого сайта"),
    el("div", { class: "checks" }, checkRows),
    el("div", { class: "row" },
      el("button", { class: "act", type: "submit" }, "Сохранить"),
      current.id ? el("button", { class: "ghost", type: "button", onclick: () => togglePanic(current) }, current.panic ? "Снять Ads review" : "Ads review: все на вайт, клоака стоит") : null
    )
  );
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const next = {};
    for (const [key] of CHECKS) {
      const row = rules[key];
      const item = { mode: row.select.value, points: Number(row.points.value || 0) };
      if (key === "language") item.langs = row.extra.value.split(/[,\s]+/).map((part) => part.trim()).filter(Boolean);
      if (key === "velocity") item.limit = Number(row.extra.value || 25);
      if (key === "burst") {
        item.window_sec = Number(row.extra.value || 120);
        item.min_asn = Number(((current.filters || {}).burst || {}).min_asn || 3);
      }
      next[key] = item;
    }
    const threshold = MODES.find((item) => item[0] === mode)[2];
    const body = {
      slug: current.slug,
      name: current.name,
      domain: current.domain,
      offer_url: current.offer_url,
      bridge_url: current.bridge_url || "",
      white_mode: current.white_mode || "local_html",
      white_url: current.white_url || "",
      geos: geos.value.split(/[,\s]+/).map((item) => item.trim()).filter(Boolean),
      threshold,
      challenge_enabled: false,
      enabled: current.enabled !== false,
      panic: !!current.panic,
      filters: next,
    };
    await api("/campaigns/" + current.id, { method: "PUT", body: JSON.stringify(body) });
    state.editing = null;
    await refresh();
    render();
  });
  const rows = state.campaigns.map((item) =>
    el("tr", { class: "clickable" + (item.id === current.id ? " on" : ""), onclick: () => { state.editing = item; render(); } },
      el("td", null, item.name),
      el("td", null, item.domain || "—"),
      el("td", null, item.offer_url || "—"),
      el("td", null, item.white_url || "ind-w.html"),
      el("td", null, item.panic ? "Ads review" : modeTitle(item.threshold))
    )
  );
  return shell([
    heading("Сайты", "Список того, что уже подключено. Новый сайт, оффер или вайт сюда не добавляются. Ниже крутятся фильтры, баллы и порог."),
    el("div", { class: "card", style: "margin-bottom:14px" },
      el("div", { class: "day-scroll" }, table(["Название", "Сайт", "Оффер / платёжка", "Вайт", "Порог"], rows))
    ),
    el("div", { class: "card" }, form),
    el("div", { class: "grid2", style: "margin-top:14px" },
      ipCard("Свои IP", "Эти адреса всегда видят оффер. Так ты сам открываешь сайт и не попадаешь на вайт.", state.allow, "note", "/allow", "Добавить"),
      ipCard("Запрет", "Эти адреса всегда видят вайт. Если адрес в обоих списках, побеждает запрет.", state.bans.filter((row) => row.source !== "reviewer"), "reason", "/bans", "Запретить")
    ),
    reviewerCard(),
  ]);
}

async function togglePanic(item) {
  await api("/campaigns/" + item.id + "/panic", { method: "POST", body: JSON.stringify({ panic: !item.panic }) });
  await refresh();
  state.editing = state.campaigns.find((row) => row.id === item.id) || null;
  render();
}

function logRows(rows) {
  return rows.map((row) =>
    el("tr", { class: "clickable", role: "button", onclick: () => { state.log = row; render(); } },
      el("td", null, (row.timestamp || "").replace("T", " ").slice(0, 16)),
      el("td", null, row.country || "—"),
      el("td", null, pill(row.verdict)),
      el("td", null, reasonText(row.reason))
    )
  );
}

function logs() {
  const search = el("input", { value: state.logQuery, placeholder: "IP, браузер, провайдер, адрес" });
  const offer = offerSelect(state.logCampaign, (value) => { state.logCampaign = value; });
  const verdict = el("select", null,
    el("option", { value: "", selected: !state.logVerdict }, "Все заходы"),
    el("option", { value: "grey", selected: state.logVerdict === "grey" }, "Только оффер"),
    el("option", { value: "white", selected: state.logVerdict === "white" }, "Только вайт")
  );
  const reasons = ["", "bot_user_agent", "headless", "geo_miss", "ads_referer", "http_referer", "no_click_id", "empty_lang", "vpn", "tor", "hosting", "language", "banned", "asn_blocked", "ip_range_blocked", "google_crawler", "review_burst", "cloaker_api", "ipqs_fraud", "velocity", "panic", "honeypot"];
  const reason = el("select", null, ...reasons.map((code) =>
    el("option", { value: code, selected: state.logReason === code }, code ? reasonText(code) : "Любая причина")
  ));
  const country = el("input", { value: state.logCountry, placeholder: "US", maxlength: "2" });
  const from = el("input", { type: "date", value: state.logFrom });
  const to = el("input", { type: "date", value: state.logTo });
  const apply = el("button", { class: "act", type: "button", onclick: async () => {
    state.logQuery = search.value.trim();
    state.logCampaign = offer.value;
    state.logVerdict = verdict.value;
    state.logReason = reason.value;
    state.logCountry = country.value.trim().toUpperCase();
    state.logFrom = from.value;
    state.logTo = to.value;
    await refresh();
    render();
  } }, "Показать");
  const reset = el("button", { class: "ghost", type: "button", onclick: async () => {
    state.logQuery = state.logCampaign = state.logVerdict = state.logReason = state.logCountry = state.logFrom = state.logTo = "";
    await refresh();
    render();
  } }, "Сбросить");
  return shell([
    heading("Журнал", "Каждый заход: кто это, сколько баллов и почему ушёл на оффер или на вайт. Время московское.", el("span", { class: "count" }, (state.logTotal || state.logs.length) + " записей")),
    el("div", { class: "card" },
      el("div", { class: "row" }, field("Поиск", search), field("Оффер", offer), field("Куда", verdict), field("Почему", reason)),
      el("div", { class: "row" }, field("Страна", country), field("С даты", from), field("По дату", to), el("div", { class: "row" }, apply, reset)),
      state.logs.length
        ? el("div", { class: "day-scroll" }, table(
          ["Время", "IP", "Страна", "Кто", "Оффер", "Система", "Браузер", "Баллы", "Куда", "Почему"],
          journalRows(state.logs)
        ))
        : el("p", { class: "empty" }, "По этому фильтру заходов нет.")
    ),
    sheet(),
  ]);
}

function journalRows(rows) {
  return rows.map((row) =>
    el("tr", { class: "clickable", role: "button", onclick: () => { state.log = row; state.sheetTab = "summary"; render(); } },
      el("td", null, row.timestamp || ""),
      el("td", null, row.ip || "—"),
      el("td", null, row.country || "—"),
      el("td", null, row.badge ? el("span", { class: "tag " + row.badge.toLowerCase() }, row.badge) : "—"),
      el("td", null, row.campaign || "—"),
      el("td", null, row.os || "—"),
      el("td", null, row.browser || "—"),
      el("td", { class: "num" }, row.score),
      el("td", null, pill(row.verdict)),
      el("td", null, reasonText(row.reason))
    )
  );
}

function sheet() {
  const row = state.log;
  if (!row) return null;
  const details = Array.isArray(row.details) ? row.details : [];
  const campaign = state.campaigns.find((item) => item.slug === row.campaign);
  const threshold = campaign ? campaign.threshold : 70;
  const tabs = [["summary", "Сводка"], ["headers", "Заголовки"], ["checks", "Что сработало"], ["json", "JSON"]];
  const body = state.sheetTab === "headers"
    ? el("div", { class: "meta" },
        meta("Браузер", row.user_agent || "—"),
        meta("Откуда пришёл", row.referer || "—"),
        meta("Язык", row.language || "—"),
        meta("Провайдер", row.isp || "—"),
        meta("Город", row.city || "—"),
        meta("Метки", Object.keys(row.query || {}).length ? JSON.stringify(row.query) : "—")
      )
    : state.sheetTab === "checks"
      ? (details.length
        ? table(["Проверка", "Баллы", "Почему"], details.map((item) => el("tr", null, el("td", null, item.check), el("td", { class: "num" }, "+" + item.points), el("td", null, item.reason))))
        : el("p", { class: "empty" }, "Штрафов нет. Заход прошёл без баллов."))
      : state.sheetTab === "json"
        ? el("pre", { class: "json" }, JSON.stringify(row, null, 2))
        : el("div", null,
            el("div", { class: "tiles" },
              el("div", { class: "tile" }, el("span", null, "Куда"), el("b", null, saw(row.verdict))),
              el("div", { class: "tile" }, el("span", null, "Баллы"), el("b", null, row.score + " / " + threshold)),
              el("div", { class: "tile" }, el("span", null, "Почему"), el("b", null, reasonText(row.reason))),
              el("div", { class: "tile" }, el("span", null, "Оффер"), el("b", null, row.campaign || "—"))
            ),
            el("div", { class: "bar" }, el("i", { style: "width:" + Math.min(100, row.score || 0) + "%" })),
            el("p", { class: "empty" }, details.length ? "Сработало проверок: " + details.length + "." : "Ни одна проверка не добавила баллов.")
          );
  return el("div", { class: "sheet-back", onclick: (event) => { if (event.target === event.currentTarget) { state.log = null; render(); } } },
    el("aside", { class: "sheet" },
      el("div", { class: "row" },
        el("h2", null, row.ip || "Заход"),
        pill(row.verdict),
        row.badge ? el("span", { class: "tag " + row.badge.toLowerCase() }, row.badge) : null,
        el("button", { class: "ghost", onclick: () => { state.log = null; render(); } }, "Закрыть")
      ),
      el("p", { class: "empty" }, [row.timestamp, row.country, row.city, row.isp].filter(Boolean).join(" · ") + " · " + reasonText(row.reason)),
      el("div", { class: "tabs" }, tabs.map(([id, label]) =>
        el("button", { class: state.sheetTab === id ? "act" : "ghost", type: "button", onclick: () => { state.sheetTab = id; render(); } }, label)
      )),
      body,
      el("div", { class: "row" },
        el("button", { class: "ghost", type: "button", onclick: () => navigator.clipboard.writeText(JSON.stringify(row, null, 2)) }, "Скопировать JSON"),
        row.ip ? el("button", { class: "danger", type: "button", onclick: async () => { await api("/bans", { method: "POST", body: JSON.stringify({ ip: row.ip, reason: row.reason || "из журнала", source: "reviewer" }) }); await refresh(); render(); } }, "Запретить IP") : null,
        row.ip ? el("button", { class: "ghost", type: "button", onclick: async () => { await api("/bans", { method: "POST", body: JSON.stringify({ ip: slash24(row.ip), reason: row.reason || "из журнала", source: "reviewer" }) }); await refresh(); render(); } }, "Запретить /24") : null,
        row.ip ? el("button", { class: "ghost", type: "button", onclick: async () => { await api("/allow", { method: "POST", body: JSON.stringify({ ip: row.ip, note: "из журнала" }) }); await refresh(); render(); } }, "В свои") : null
      )
    )
  );
}

function meta(label, value) {
  return el("div", null, el("span", null, label), el("b", null, value ?? "—"));
}

function probeCard() {
  const campaign = state.campaigns.find((item) => item.slug === state.offer) || state.campaigns[0];
  const geo = campaignGeo(campaign);
  return el("div", { class: "card", style: "margin-top:14px" },
    el("div", { class: "k" }, "Прогнать клик"),
    el("p", { class: "empty" }, "Разовая проверка выбранного оффера. Результат попадёт на график."),
    el("div", { class: "row" },
      sceneButton("Живой", "android", geo),
      sceneButton("Facebook", "facebook", geo),
      sceneButton("Бот", "bot", geo),
      sceneButton("Чужая страна", "android", "DE"),
      sceneButton("Кабинет Google", "android", geo, "https://ads.google.com/aw/overview")
    ),
    state.sim ? simResult(state.sim) : null
  );
}

function campaignGeo(campaign) {
  const geos = (campaign && campaign.geos) || [];
  return geos[0] || "US";
}

function sceneButton(title, preset, country, referer) {
  return el("button", { class: "ghost", type: "button", onclick: () => runScene(preset, country, referer || "") }, title);
}

async function runScene(preset, country, referer) {
  const campaign = state.campaigns.find((item) => item.slug === state.offer) || state.campaigns[0];
  state.sim = await api("/simulate", {
    method: "POST",
    body: JSON.stringify({
      campaign: campaign ? campaign.slug : "demo",
      ip: "203.0.113." + (20 + Math.floor(Math.random() * 70)),
      country,
      user_agent: PRESETS[preset],
      referer: referer || "",
      query: { utm_source: "check" },
    }),
  });
  await refresh();
  render();
}

function simResult(result) {
  return el("div", null,
    el("div", { class: "k" }, "Результат"),
    el("h2", { style: "font-family:Fraunces,serif;font-weight:460;font-size:42px;margin:8px 0" }, saw(result.verdict)),
    el("p", null, reasonText(result.reason)),
    result.url ? el("p", { class: "empty" }, result.url) : null
  );
}

function slash24(ip) {
  const parts = String(ip || "").split(".");
  if (parts.length === 4) return parts.slice(0, 3).join(".") + ".0/24";
  return ip;
}

function ipCard(title, text, rows, noteKey, path, button) {
  const ip = el("input", { placeholder: path === "/bans" ? "1.2.3.4 или 1.2.3.0/24" : "1.2.3.4" });
  const note = el("input", { placeholder: "зачем" });
  const form = el("form", { class: "row" }, field("IP", ip), field("Заметка", note), el("button", { class: "act", type: "submit" }, button));
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const body = path === "/bans"
      ? { ip: ip.value.trim(), reason: note.value.trim() || "запрет", source: "manual" }
      : { ip: ip.value.trim(), note: note.value.trim() || "свой" };
    await api(path, { method: "POST", body: JSON.stringify(body) });
    await refresh();
    render();
  });
  const withSource = path === "/bans";
  const list = rows.map((item) =>
    el("tr", null,
      el("td", null, item.ip),
      withSource ? el("td", null, item.source || "—") : null,
      el("td", null, item[noteKey] || "—"),
      el("td", null, el("button", { class: "danger", onclick: async () => {
        await api(path + "/" + encodeURIComponent(item.ip), { method: "DELETE" });
        await refresh();
        render();
      } }, "Убрать"))
    )
  );
  return el("div", { class: "card" },
    el("div", { class: "k" }, title),
    el("p", { class: "empty" }, text),
    form,
    rows.length ? table(withSource ? ["IP", "Откуда", "Заметка", ""] : ["IP", "Заметка", ""], list) : el("p", { class: "empty" }, "Список пуст.")
  );
}

function reviewerCard() {
  const rows = (state.bans || []).filter((row) => row.source === "reviewer");
  const ip = el("input", { placeholder: "1.2.3.4 или 1.2.3.0/24" });
  const note = el("input", { placeholder: "dual-fetch, AdsBot, Tencent" });
  const form = el("form", { class: "row" }, field("Reviewer IP", ip), field("Заметка", note), el("button", { class: "act", type: "submit" }, "В reviewer"));
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    await api("/bans", { method: "POST", body: JSON.stringify({ ip: ip.value.trim(), reason: note.value.trim() || "reviewer", source: "reviewer" }) });
    await refresh();
    render();
  });
  const campaign = offerSelect(state.logCampaign, (value) => { state.logCampaign = value; });
  const day = el("input", { type: "date", value: state.reviewerDay || "" });
  const importForm = el("form", { class: "row" }, campaign, day, el("button", { class: "ghost", type: "submit" }, "Импорт DC из журнала за день"));
  importForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    state.reviewerDay = day.value;
    await api("/reviewers/import", { method: "POST", body: JSON.stringify({ campaign: state.logCampaign || "", date: day.value }) });
    await refresh();
    render();
  });
  const list = rows.map((item) =>
    el("tr", null,
      el("td", null, item.ip),
      el("td", null, item.reason || "—"),
      el("td", null, (item.expires_at || "").replace("T", " ").slice(0, 16) || "—"),
      el("td", null, el("button", { class: "danger", onclick: async () => {
        await api("/bans/" + encodeURIComponent(item.ip), { method: "DELETE" });
        await refresh();
        render();
      } }, "Убрать"))
    )
  );
  return el("div", { class: "card", style: "margin-top:14px" },
    el("div", { class: "k" }, "Reviewer IP"),
    el("p", { class: "empty" }, "Свои инциденты: dual-fetch, Google crawler, хостинг. Повтор этого IP сразу на вайт, без IPinfo. Живых Comcast/AT&T/Charter импорт не берёт."),
    form,
    importForm,
    rows.length ? table(["IP / сеть", "Почему", "До", ""], list) : el("p", { class: "empty" }, "Пока пусто — появятся после dual-fetch или импорта.")
  );
}

function more() {
  const cards = Object.entries(state.lists).map(([name, pack]) => chipCard(name, pack));
  const data = state.engine || { ipqs: false, ipinfo: false };
  return shell([
    heading("Списки", "Сюда заходят редко. Одно значение на строку: боты, сети, города."),
    el("div", { class: "card", style: "margin-bottom:14px" },
      el("div", { class: "k" }, "Проверки IP"),
      keyLine("База грязных IP", data.ipqs),
      keyLine("База страны и хостинга", data.ipinfo),
      keyLine("Внешний клоак", data.cloaker),
      el("p", { class: "empty" }, "Ключи лежат в файле .env на этой машине. Без них страна берётся из Cloudflare, а боты ловятся по браузеру и сетям. Внешний API зовётся только если локально ещё серый.")
    ),
    el("div", { class: "grid2" }, cards),
  ]);
}

function chipCard(name, pack) {
  const items = (pack.items || []).slice();
  const box = el("div", { class: "chips" });
  const input = el("input", { placeholder: "Новое значение и Enter" });
  function paint() {
    box.replaceChildren(...items.map((item, index) =>
      el("button", { class: "chip", type: "button", onclick: () => { items.splice(index, 1); paint(); } }, item + "  ×")
    ));
  }
  paint();
  input.addEventListener("keydown", (event) => {
    if (event.key !== "Enter") return;
    event.preventDefault();
    const value = input.value.trim();
    if (value && !items.includes(value)) items.push(value);
    input.value = "";
    paint();
  });
  return el("div", { class: "card" },
    el("div", { class: "k" }, listTitle(name)),
    el("p", { class: "empty" }, pack.description || "Крестик убирает значение. Сохраните, когда список готов."),
    box,
    input,
    el("div", { class: "row" }, el("button", { class: "act", onclick: async () => {
      await api("/lists/" + name, { method: "PUT", body: JSON.stringify({ items }) });
      await refresh();
      render();
    } }, "Сохранить"))
  );
}

function listTitle(name) {
  return {
    user_agents_block: "Имена ботов",
    asn_block: "Сети датацентров",
    isp_block: "Провайдеры",
    cities_block: "Города",
    gpu_block: "Эмуляторы",
    vpn_asn: "Сети VPN",
  }[name] || name;
}

function keyLine(name, on) {
  return el("div", { class: "status", style: "margin-top:12px" },
    el("i", { class: on ? "dot on" : "dot" }),
    el("span", null, name + (on ? " подключена" : " не подключена"))
  );
}

function fact(label, value) {
  return el("div", null, el("span", null, label), el("b", null, value));
}

function login() {
  const password = el("input", { type: "password" });
  password.autofocus = true;
  const form = el("form", null,
    field("Пароль", password),
    el("div", { class: "row" }, el("button", { class: "act", type: "submit" }, "Войти")),
    el("div", { class: "err" }, state.error)
  );
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    try {
      await api("/login", { method: "POST", body: JSON.stringify({ password: password.value }) });
      state.me = true;
      state.error = "";
      await refresh();
      render();
    } catch (e) {
      state.error = "Пароль не подошёл.";
      render();
    }
  });
  return el("div", { class: "login" },
    el("div", { class: "box" },
      el("div", { class: "mark" }, "Кабинет"),
      el("h1", null, "web-klo"),
      el("p", { class: "sub" }, "Живой человек видит оффер. Бот и чужая страна видят вайт."),
      form
    )
  );
}

function render() {
  app.replaceChildren();
  if (!state.me) {
    app.append(login());
    return;
  }
  const views = { desk, campaigns, logs, more };
  app.append((views[state.view] || desk)());
}

boot();
