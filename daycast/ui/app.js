"use strict";

// I nomi di app, siti e categorie arrivano da titoli di finestre e da quello
// che scrive l'utente: entrano nel DOM solo tramite textContent, mai innerHTML.

const NS = "http://www.w3.org/2000/svg";
const GAP = 2; // spazio color superficie tra segmenti impilati
const FORECAST_OPACITY = 0.42;

const state = {
  date: null, // null = oggi
  category: "all",
  view: "chart",
  data: null,
  settings: null,
};

// ---------- utilità ----------

function el(tag, attrs = {}, children = []) {
  const node = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (k === "text") node.textContent = v;
    else if (k === "class") node.className = v;
    else if (k === "style") Object.assign(node.style, v);
    else node.setAttribute(k, v);
  }
  for (const c of [].concat(children)) if (c !== null && c !== undefined) node.append(c);
  return node;
}

function svg(tag, attrs = {}, parent = null) {
  const node = document.createElementNS(NS, tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (k === "text") node.textContent = v;
    else node.setAttribute(k, v);
  }
  if (parent) parent.append(node);
  return node;
}

function allCategories() {
  return state.data?.categories ?? state.settings?.categories ?? [];
}

function findCategory(id) {
  return allCategories().find((c) => c.id === id) ?? state.settings?.categories.find((c) => c.id === id);
}

function catColor(id) {
  const slot = findCategory(id)?.slot;
  return slot ? `var(--slot-${slot})` : "var(--slot-none)";
}

function catName(id) {
  if (id === "none") return t("cat.none");
  return findCategory(id)?.name ?? t("cat.none");
}

function swatch(id) {
  return el("span", { class: id === "none" ? "swatch none" : "swatch", style: { background: catColor(id) } });
}

function fmtDur(min, approx = false) {
  let m = approx ? Math.round(min / 5) * 5 : Math.round(min);
  if (approx && m === 0 && min > 0.5) return "<5m";
  const h = Math.floor(m / 60);
  const r = m % 60;
  if (!h) return `${r}m`;
  return r ? `${h}h ${r}m` : `${h}h`;
}

function fmtMin(m) {
  return `${new Intl.NumberFormat(locale(), { minimumFractionDigits: 1, maximumFractionDigits: 1 }).format(m)} min`;
}

function fmtHour(h) {
  return `${h}:00`;
}

function parseIso(iso) {
  const [y, m, d] = iso.split("-").map(Number);
  return new Date(y, m - 1, d);
}

function toIso(d) {
  const p = (n) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}`;
}

function capitalize(s) {
  return s.charAt(0).toUpperCase() + s.slice(1);
}

// le date seguono la lingua scelta
function dayFmt(d) {
  return capitalize(new Intl.DateTimeFormat(locale(), { weekday: "long", day: "numeric", month: "long" }).format(d));
}

function shortDay(d) {
  const wd = new Intl.DateTimeFormat(locale(), { weekday: "short" }).format(d).replace(".", "");
  return `${wd} ${d.getDate()}`;
}

function selectedCats(data) {
  return state.category === "all" ? data.categories.map((c) => c.id) : [state.category];
}

function sum(obj, ids) {
  return ids.reduce((s, id) => s + (obj[id] || 0), 0);
}

// Valori da impilare per un'ora o un giorno. Più app possono essere in uso
// insieme (musica mentre lavori), quindi la somma delle categorie può superare
// il tempo reale. Con «Tutte» l'altezza è il tempo di uso del PC e ogni
// categoria ne occupa una quota proporzionale al suo uso.
function stackOf(entry, kind, ids) {
  const raw = entry[kind];
  if (state.category !== "all") {
    const v = raw[state.category] || 0;
    return { values: { [state.category]: v }, raw, total: v, rawSum: v };
  }
  const active = entry[`${kind}_active`];
  const rawSum = sum(raw, ids);
  const k = rawSum > 0 ? active / rawSum : 0;
  const values = Object.fromEntries(ids.map((id) => [id, (raw[id] || 0) * k]));
  return { values, raw, total: active, rawSum };
}

// ---------- backend ----------

function waitForPywebview(timeoutMs = 5000) {
  return new Promise((resolve, reject) => {
    if (window.pywebview?.api) return resolve();
    const timer = setTimeout(() => reject(new Error("API non disponibile")), timeoutMs);
    window.addEventListener("pywebviewready", () => {
      clearTimeout(timer);
      resolve();
    }, { once: true });
  });
}

// Nella finestra nativa si usa window.pywebview.api; con --browser il server
// locale risponde a POST /api/<metodo>. pywebview serve anche lui la pagina
// via http, quindi si prova il server e, se non risponde, si aspetta l'API.
async function call(method, ...args) {
  if (window.pywebview?.api) return window.pywebview.api[method](...args);
  try {
    const res = await fetch(`/api/${method}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(args),
    });
    if (res.ok) return await res.json();
  } catch {
    // nessun server: siamo nella finestra nativa
  }
  await waitForPywebview();
  return window.pywebview.api[method](...args);
}

let pendingReload = 0;

async function load() {
  const main = document.getElementById("main");
  main.classList.add("loading");
  try {
    state.data = await call("get_dashboard", state.date);
    if (state.category !== "all" && !state.data.categories.some((c) => c.id === state.category)) {
      state.category = "all";
    }
    render();
    // Timestral calcola in un processo a parte: quando ha finito, la pagina si aggiorna da sola
    if (state.data.forecast_pending && !pendingReload) {
      pendingReload = setTimeout(() => {
        pendingReload = 0;
        load();
      }, 8000);
    }
  } catch (err) {
    console.error(err);
  } finally {
    main.classList.remove("loading");
  }
}

// ---------- tooltip ----------

const tooltip = document.getElementById("tooltip");

function showTooltip(content, evt, anchor) {
  tooltip.replaceChildren(...content);
  tooltip.hidden = false;
  const tw = tooltip.offsetWidth;
  const th = tooltip.offsetHeight;
  let x, y;
  if (evt && evt.clientX !== undefined) {
    x = evt.clientX + 14;
    y = evt.clientY + 14;
  } else {
    const r = anchor.getBoundingClientRect();
    x = r.right + 8;
    y = r.top;
  }
  if (x + tw > innerWidth - 8) x = Math.max(8, x - tw - 28);
  if (y + th > innerHeight - 8) y = Math.max(8, innerHeight - th - 8);
  tooltip.style.left = `${x}px`;
  tooltip.style.top = `${y}px`;
}

function hideTooltip() {
  tooltip.hidden = true;
}

// righe del tooltip: minuti reali di ogni categoria e, con «Tutte», la quota
function ttRows(stack, ids) {
  const showPct = state.category === "all" && stack.rawSum > 0;
  return ids
    .slice()
    .reverse() // dall'alto verso il basso, come nella pila
    .filter((id) => stack.raw[id] >= 0.5)
    .map((id) =>
      el("div", { class: "tt-row" }, [
        el("span", { class: "tt-key", style: { background: catColor(id) } }),
        el("span", { class: "tt-val", text: fmtDur(stack.raw[id]) }),
        el("span", { class: "tt-name", text: catName(id) }),
        showPct ? el("span", { class: "tt-pct", text: `${Math.round((stack.raw[id] / stack.rawSum) * 100)}%` }) : null,
      ])
    );
}

function ttOverlap(stack) {
  if (state.category !== "all" || stack.rawSum - stack.total < 1) return null;
  return el("div", {
    class: "tt-explain",
    text: t("tt.overlap", { t: fmtDur(stack.rawSum) }),
  });
}

function bindHover(node, build) {
  node.addEventListener("pointermove", (e) => showTooltip(build(), e));
  node.addEventListener("pointerleave", hideTooltip);
  node.addEventListener("focus", () => showTooltip(build(), null, node));
  node.addEventListener("blur", hideTooltip);
}

// ---------- barre impilate ----------

function roundedTop(x, yTop, w, yBottom, r) {
  r = Math.min(r, w / 2, yBottom - yTop);
  return (
    `M${x},${yBottom}V${yTop + r}Q${x},${yTop} ${x + r},${yTop}` +
    `H${x + w - r}Q${x + w},${yTop} ${x + w},${yTop + r}V${yBottom}Z`
  );
}

function drawStack(g, x, w, baseY, scale, values, ids, opacity) {
  let y = baseY;
  const segs = ids.filter((id) => values[id] * scale >= 0.75);
  segs.forEach((id, i) => {
    const h = values[id] * scale;
    const top = y - h;
    const bottom = i > 0 ? y - GAP : y;
    if (bottom - top < 0.75) {
      y = top;
      return;
    }
    const last = i === segs.length - 1;
    const attrs = { fill: catColor(id), "fill-opacity": opacity };
    if (last) svg("path", { ...attrs, d: roundedTop(x, top, w, bottom, 4) }, g);
    else svg("rect", { ...attrs, x, y: top, width: w, height: bottom - top }, g);
    y = top;
  });
  return y;
}

// ---------- intestazione e riepilogo ----------

function renderHeader(data) {
  const d = parseIso(data.date);
  document.getElementById("day-title").textContent = dayFmt(d);
  document.getElementById("day-relation").textContent = t(`relation.${data.relation}`);
  document.getElementById("go-today").disabled = data.relation === "today";

  const badge = document.getElementById("mock-badge");
  if (data.mock) {
    badge.textContent = t("badge.mock");
    badge.title = t("badge.mock.title");
  } else if (data.forecast_model === "timestral") {
    const ev = data.forecast_eval;
    badge.textContent = t("badge.timestral");
    badge.title = t("badge.timestral.title", { days: ev.backtest_days, mae_t: fmtMin(ev.mae_timestral), mae_b: fmtMin(ev.mae_base) });
  } else {
    const n = data.history_days;
    const ev = data.forecast_eval;
    badge.textContent = n ? (n === 1 ? t("badge.day") : t("badge.days", { n })) : t("badge.fewData");
    let title = n ? t("badge.base.title") : t("badge.noData.title");
    if (data.forecast_pending) title += t("badge.pending");
    else if (ev?.mae_timestral != null) {
      title += t("badge.baseWins", { days: ev.backtest_days, mae_t: fmtMin(ev.mae_timestral), mae_b: fmtMin(ev.mae_base) });
    } else if (n) title += t("badge.waitWeek");
    badge.title = title;
  }
  badge.hidden = false;
}

// dati veri ma ancora nessun giorno completo su cui basare la previsione
function noForecast(data) {
  return !data.mock && data.history_days === 0;
}

function renderFilters(data) {
  const box = document.getElementById("filters");
  const items = [{ id: "all", name: t("filters.all") }, ...data.categories];
  box.replaceChildren(
    ...items.map((c) => {
      const chip = el("button", {
        class: "chip",
        role: "radio",
        "aria-checked": String(state.category === c.id),
      });
      if (c.id !== "all") chip.append(swatch(c.id));
      chip.append(document.createTextNode(c.id === "all" ? c.name : catName(c.id)));
      chip.addEventListener("click", () => {
        state.category = c.id;
        render();
      });
      return chip;
    })
  );
}

function renderSummary(data) {
  const ids = selectedCats(data);
  const tot = data.totals[state.category];
  const filtered = state.category !== "all";
  const suffix = filtered ? ` · ${catName(state.category)}` : "";
  const past = data.relation === "past";

  const label = t(`hero.${data.relation}`);
  document.getElementById("hero-label").textContent = label + suffix;

  const value = document.getElementById("hero-value");
  const sub = document.getElementById("hero-sub");
  const progress = document.getElementById("hero-progress");
  sub.replaceChildren();

  const range = t("hero.range", { lo: fmtDur(tot.p10, true), hi: fmtDur(tot.p90, true) });
  const blind = noForecast(data);
  if (past) {
    value.textContent = fmtDur(tot.actual);
    sub.append(blind ? t("hero.noForecastPast") : t("hero.predicted", { p50: fmtDur(tot.p50, true), range }));
    progress.hidden = true;
  } else if (blind) {
    document.getElementById("hero-label").textContent =
      (data.relation === "today" ? t("hero.todayActual") : t("hero.future")) + suffix;
    value.textContent = data.relation === "today" ? fmtDur(tot.actual) : "—";
    sub.append(t("hero.startsAfter"));
    progress.hidden = true;
  } else {
    value.textContent = `~${fmtDur(tot.p50, true)}`;
    sub.append(t("hero.likely", { range }));
    if (data.relation === "today") {
      sub.append(t("hero.soFar"), el("strong", { text: fmtDur(tot.actual) }));
      progress.hidden = false;
      const pct = Math.min(100, (tot.actual / tot.p50) * 100 || 0);
      document.getElementById("hero-progress-fill").style.width = `${pct}%`;
    } else {
      progress.hidden = true;
    }
  }

  // le statistiche seguono il filtro; per un giorno passato (o senza previsione) si usano i dati reali
  const useActual = past || (blind && data.relation === "today");
  const totals = data.hours.map((h) => (useActual && !h.actual ? 0 : stackOf(h, useActual ? "actual" : "forecast", ids).total));
  // sui dati reali basta un minuto; sulle previsioni (medie) serve qualcosa di più deciso
  const first = totals.findIndex((v) => v >= (useActual ? 1 : filtered ? 3 : 5));
  const peak = totals.indexOf(Math.max(...totals));
  document.getElementById("stat-first-label").textContent = useActual ? t("stat.firstActual") : t("stat.firstPredicted");
  document.getElementById("stat-first").textContent = first >= 0 ? fmtHour(first) : "—";
  document.getElementById("stat-peak").textContent = totals[peak] > 0 ? fmtHour(peak) : "—";

  const top = document.getElementById("stat-top");
  top.replaceChildren();
  if (!filtered) {
    document.getElementById("stat-top-label").textContent = t("stat.topCategory");
    const key = useActual ? "actual" : "p50";
    const best = data.categories.reduce((a, c) => (data.totals[c.id][key] > data.totals[a.id][key] ? c : a));
    top.append(swatch(best.id), catName(best.id));
  } else {
    document.getElementById("stat-top-label").textContent = t("stat.topApp");
    const app = data.apps.find((a) => a.category === state.category);
    top.append(app ? app.name : "—");
  }
}

// ---------- grafico orario ----------

function renderHourlyLegend(data) {
  const ids = selectedCats(data);
  document.getElementById("hourly-sub").textContent =
    state.category === "all"
      ? t("hourly.subAll")
      : t("hourly.subCat", { cat: catName(state.category) });

  const box = document.getElementById("hourly-legend");
  const items = ids.map((id) => el("span", { class: "legend-item" }, [swatch(id), catName(id)]));
  const extra = [];
  if (data.relation !== "future") {
    extra.push(el("span", { class: "legend-item" }, [el("span", { class: "key-actual" }), t("legend.actual")]));
  }
  const blind = noForecast(data);
  if (data.relation !== "past" && !blind) {
    extra.push(el("span", { class: "legend-item" }, [el("span", { class: "key-forecast" }), t("legend.forecast")]));
    extra.push(el("span", { class: "legend-item" }, [el("span", { class: "key-range" }), t("legend.range")]));
  }
  if (data.relation !== "future" && !blind) {
    extra.push(el("span", { class: "legend-item" }, [el("span", { class: "key-tick" }), t("legend.tick")]));
  }
  box.replaceChildren(...items, el("span", { class: "legend-sep" }), ...extra);
}

function renderHourlyChart(data) {
  const box = document.getElementById("hourly-chart");
  const ids = selectedCats(data);
  const W = Math.max(320, box.clientWidth);
  const H = 290;
  const m = { top: 22, right: 6, bottom: 24, left: 40 };
  const pw = W - m.left - m.right;
  const ph = H - m.top - m.bottom;
  const base = m.top + ph;
  const scale = ph / 60;
  const band = pw / 24;
  const bw = Math.min(24, band * 0.68);

  const root = svg("svg", { viewBox: `0 0 ${W} ${H}`, height: H, role: "img", "aria-label": t("hourly.aria") });

  const grid = svg("g", { class: "grid" }, root);
  for (const v of [15, 30, 45, 60]) {
    const y = base - v * scale;
    svg("line", { x1: m.left, x2: W - m.right, y1: y, y2: y }, grid);
  }
  for (const v of [0, 15, 30, 45, 60]) {
    svg("text", { x: m.left - 8, y: base - v * scale + 4, "text-anchor": "end", text: v === 60 ? "60 min" : v }, root);
  }

  const step = band < 22 ? 6 : 3;
  for (let h = 0; h < 24; h += step) {
    svg("text", { x: m.left + h * band + band / 2, y: H - 6, "text-anchor": "middle", text: fmtHour(h) }, root);
  }

  const bars = svg("g", {}, root);
  const marks = svg("g", {}, root);
  const hits = svg("g", {}, root);

  data.hours.forEach((hr) => {
    const cx = m.left + hr.hour * band + band / 2;
    const x = cx - bw / 2;
    const isActual = !!hr.actual;
    const st = stackOf(hr, isActual ? "actual" : "forecast", ids);
    drawStack(bars, x, bw, base, scale, st.values, ids, isActual ? 1 : FORECAST_OPACITY);

    const fc = stackOf(hr, "forecast", ids).total;
    const b = hr.band[state.category];
    if (isActual) {
      if (fc >= 0.5) {
        const y = base - fc * scale;
        svg("line", { class: "tick-forecast", x1: x - 3, x2: x + bw + 3, y1: y, y2: y }, marks);
      }
    } else if (b.p90 >= 1) {
      const y1 = base - b.p10 * scale;
      const y2 = base - b.p90 * scale;
      svg("line", { class: "whisker", x1: cx, x2: cx, y1, y2 }, marks);
      svg("line", { class: "whisker", x1: cx - 3, x2: cx + 3, y1: y2, y2: y2 }, marks);
    }

    const hit = svg("rect", {
      class: "hit",
      x: m.left + hr.hour * band,
      y: m.top,
      width: band,
      height: ph,
      tabindex: 0,
      "aria-label": `${fmtHour(hr.hour)}: ${fmtDur(st.total)} ${isActual ? t("chart.actual") : t("chart.predicted")}`,
    }, hits);
    bindHover(hit, () => {
      const head = state.category === "all"
        ? t(isActual ? "tt.pcInUse" : "tt.pcInUsePredicted", { t: fmtDur(st.total) })
        : isActual ? t("tt.actualUse") : t("tt.forecast");
      const foot = isActual
        ? t("tt.wasPredicted", { t: fmtDur(fc) })
        : t("tt.likely", { lo: fmtDur(b.p10), hi: fmtDur(b.p90) });
      return [
        el("div", { class: "tt-title", text: `${fmtHour(hr.hour)} – ${fmtHour((hr.hour + 1) % 24)}` }),
        el("div", { class: "tt-note", text: head }),
        ...ttRows(st, ids),
        el("div", { class: "tt-total", text: foot }),
        ttOverlap(st),
      ].filter(Boolean);
    });
  });

  svg("line", { class: "baseline", x1: m.left, x2: W - m.right, y1: base + 0.5, y2: base + 0.5 }, root);

  if (data.now_hour !== null && data.now_hour !== undefined) {
    const x = m.left + (data.now_hour + new Date().getMinutes() / 60) * band;
    svg("line", { class: "now-line", x1: x, x2: x, y1: m.top - 4, y2: base }, root);
    svg("text", { class: "now-label accent", x, y: m.top - 9, "text-anchor": "middle", text: t("chart.now") }, root);
  }

  root.append(hits); // i bersagli stanno sopra a tutto
  box.replaceChildren(root);
}

function renderHourlyTable(data) {
  const ids = selectedCats(data);
  const all = state.category === "all";
  const head = el("tr", {}, [
    el("th", { text: t("table.hour") }),
    ...(all ? ids.map((id) => el("th", { text: catName(id) })) : []),
    el("th", { text: all ? t("table.pcInUse") : catName(state.category) }),
    el("th", { text: t("table.range") }),
    el("th", { text: t("table.kind") }),
  ]);
  const rows = data.hours.map((hr) => {
    const st = stackOf(hr, hr.actual ? "actual" : "forecast", ids);
    const b = hr.band[state.category];
    return el("tr", {}, [
      el("td", { text: `${fmtHour(hr.hour)}–${fmtHour((hr.hour + 1) % 24)}` }),
      ...(all ? ids.map((id) => el("td", { text: fmtDur(st.raw[id]) })) : []),
      el("td", { text: fmtDur(st.total) }),
      el("td", { text: `${fmtDur(b.p10)} – ${fmtDur(b.p90)}` }),
      el("td", { class: "state", text: hr.actual ? t("legend.actual") : t("legend.forecast") }),
    ]);
  });
  const note = all
    ? el("p", { class: "card-sub", text: t("table.note") })
    : null;
  document.getElementById("hourly-table").replaceChildren(
    ...[note, el("table", {}, [el("thead", {}, head), el("tbody", {}, rows)])].filter(Boolean)
  );
}

// ---------- lista app ----------

function categorySelect(appName, current) {
  const cats = state.settings?.categories ?? [];
  const sel = el("select", {
    class: current && current !== "none" ? "cat-select" : "cat-select unset",
    "aria-label": t("cats.of", { app: appName }),
  });
  sel.append(el("option", { value: "", text: t("cat.none") }));
  for (const c of cats) {
    const opt = el("option", { value: c.id, text: c.name });
    if (c.id === current) opt.selected = true;
    sel.append(opt);
  }
  sel.addEventListener("change", async () => {
    applySettings(await call("assign_app", appName, sel.value || null));
  });
  return sel;
}

function renderClassifyBanner() {
  const s = state.settings;
  const banner = document.getElementById("classify-banner");
  if (!s) return;
  const ids = new Set(s.categories.map((c) => c.id));
  const missing = s.apps.filter((a) => !ids.has(s.assignments[a.name])).length;
  banner.hidden = missing === 0;
  document.getElementById("classify-text").textContent =
    missing === 1 ? t("apps.classifyOne") : t("apps.classifyMany", { n: missing });
}

function renderApps(data) {
  const title = t(`apps.${data.relation}`);
  document.getElementById("apps-title").textContent = title;
  document.getElementById("apps-sub").textContent =
    noForecast(data) || data.relation === "past" ? t("apps.subRecorded") : t("apps.subForecast");
  renderClassifyBanner();

  const list = document.getElementById("app-list");
  let apps = data.apps.filter((a) => state.category === "all" || a.category === state.category);
  if (data.relation === "past") apps = apps.slice().sort((a, b) => b.actual - a.actual);
  if (!apps.length) {
    const msg = state.category !== "all"
      ? t("apps.noneInCategory")
      : data.relation === "future" ? t("apps.noForecastYet") : t("apps.noneRecorded");
    list.replaceChildren(el("li", { class: "empty", text: msg }));
    return;
  }
  const max = Math.max(60, ...apps.map((a) => Math.max(a.p90, a.actual)));
  const pct = (v) => `${Math.min(100, (v / max) * 100)}%`;

  list.replaceChildren(
    ...apps.map((a) => {
      const color = catColor(a.category);
      let time;
      const meta = [];
      const hasForecast = a.p90 >= 0.5 || a.p50 >= 0.5;
      if (data.relation === "past") {
        time = fmtDur(a.actual);
        if (hasForecast) meta.push(t("apps.predicted", { t: fmtDur(a.p50, true) }));
      } else if (!hasForecast) {
        // app mai vista nei giorni usati per la previsione
        time = fmtDur(a.actual);
        meta.push(data.relation === "today" ? t("apps.soFarNoForecast") : t("apps.noForecast"));
      } else {
        time = `~${fmtDur(a.p50, true)}`;
        if (data.relation === "today" && a.actual >= 1) meta.push(t("apps.soFar", { t: fmtDur(a.actual) }));
        meta.push(t("apps.between", { lo: fmtDur(a.p10, true), hi: fmtDur(a.p90, true) }));
        if (!(data.relation === "today" && a.actual >= 1)) meta.push(t("apps.chance", { p: Math.round(a.probability * 100) }));
      }
      const bar = el("div", { class: "app-bar", "aria-hidden": "true" }, [
        el("div", { class: "track" }),
        el("div", { class: "range", style: { left: pct(a.p10), width: `calc(${pct(a.p90)} - ${pct(a.p10)})`, background: color } }),
        a.actual >= 0.5 && data.relation !== "future"
          ? el("div", { class: "done", style: { width: pct(a.actual), background: color } })
          : null,
        el("div", { class: "median", style: { left: pct(a.p50), background: color } }),
      ]);
      return el("li", { class: "app-row" }, [
        el("div", { class: "app-name" }, [
          swatch(a.category),
          el("span", { class: "n", text: a.name, title: a.name }),
          el("span", { class: "kind", text: t(`kind.${a.kind}`) }),
        ]),
        el("div", { class: "app-time", text: time }),
        el("div", { class: "app-meta", text: meta.join(" · ") }),
        el("div", { class: "app-prob" }, categorySelect(a.name, a.category)),
        bar,
      ]);
    })
  );
}

// ---------- settimana ----------

function niceHourStep(maxH) {
  if (maxH <= 4) return 1;
  if (maxH <= 10) return 2;
  return 4;
}

function renderWeek(data) {
  const box = document.getElementById("week-chart");
  const ids = selectedCats(data);
  const W = Math.max(320, box.clientWidth);
  const H = 220;
  const m = { top: 22, right: 6, bottom: 26, left: 40 };
  const pw = W - m.left - m.right;
  const ph = H - m.top - m.bottom;
  const base = m.top + ph;

  const days = data.week.map((d) => {
    const fc = stackOf(d, "forecast", ids).total;
    const lo = fc * (d.total.p10 / d.total.p50 || 0);
    const hi = fc * (d.total.p90 / d.total.p50 || 0);
    const out = { d, fc, lo, hi, rest: null };
    if (d.partial) {
      // giornata in corso: uso reale finora + quanto resta secondo la previsione
      out.st = stackOf(d, "actual", ids);
      const restEntry = {
        forecast: Object.fromEntries(ids.map((id) => [id, Math.max(0, (d.forecast[id] || 0) - (d.actual[id] || 0))])),
        forecast_active: Math.max(0, d.forecast_active - d.actual_active),
      };
      out.rest = stackOf(restEntry, "forecast", ids);
      out.total = out.st.total + out.rest.total;
    } else {
      out.st = stackOf(d, d.actual ? "actual" : "forecast", ids);
      out.total = out.st.total;
    }
    return out;
  });
  const maxMin = Math.max(60, ...days.map((x) => Math.max(x.total, x.d.actual && !x.d.partial ? 0 : x.hi)));
  const stepH = niceHourStep(maxMin / 60);
  const topH = Math.ceil(maxMin / 60 / stepH) * stepH;
  const scale = ph / (topH * 60);
  const band = pw / 7;
  const bw = Math.min(24, band * 0.5);

  const root = svg("svg", { viewBox: `0 0 ${W} ${H}`, height: H, role: "img", "aria-label": t("week.aria") });
  const grid = svg("g", { class: "grid" }, root);
  for (let v = 0; v <= topH; v += stepH) {
    const y = base - v * 60 * scale;
    if (v > 0) svg("line", { x1: m.left, x2: W - m.right, y1: y, y2: y }, grid);
    svg("text", { x: m.left - 8, y: y + 4, "text-anchor": "end", text: `${v}h` }, root);
  }

  const bars = svg("g", {}, root);
  const marks = svg("g", {}, root);
  const hits = svg("g", {}, root);

  days.forEach((x, i) => {
    const { d } = x;
    const cx = m.left + i * band + band / 2;
    const bx = cx - bw / 2;
    const isActual = !!d.actual && !d.partial;
    const selected = d.date === data.date;
    let topY = drawStack(bars, bx, bw, base, scale, x.st.values, ids, d.actual ? 1 : FORECAST_OPACITY);
    if (x.rest && x.rest.total * scale >= 1) {
      topY = drawStack(bars, bx, bw, topY - GAP, scale, x.rest.values, ids, FORECAST_OPACITY);
    }

    if (isActual) {
      const y = base - x.fc * scale;
      svg("line", { class: "tick-forecast", x1: bx - 3, x2: bx + bw + 3, y1: y, y2: y }, marks);
    } else {
      const y1 = base - x.lo * scale;
      const y2 = base - x.hi * scale;
      svg("line", { class: "whisker", x1: cx, x2: cx, y1, y2 }, marks);
      svg("line", { class: "whisker", x1: cx - 3, x2: cx + 3, y1: y2, y2: y2 }, marks);
    }

    if (selected) {
      const labelY = Math.min(topY, isActual ? base - x.fc * scale : base - x.hi * scale) - 6;
      svg("text", { class: "now-label", x: cx, y: labelY, "text-anchor": "middle", text: (isActual ? "" : "~") + fmtDur(x.total, !isActual) }, root);
    }

    const cls = ["day-label", d.is_today ? "today" : "", selected ? "selected" : ""].join(" ");
    const label = shortDay(parseIso(d.date));
    svg("text", { class: cls, x: cx, y: H - 8, "text-anchor": "middle", text: label }, root);
    if (selected) svg("rect", { class: "sel-mark", x: cx - 8, y: H - 3, width: 16, height: 2, rx: 1 }, root);

    const hit = svg("rect", {
      class: "hit clickable",
      x: m.left + i * band,
      y: m.top,
      width: band,
      height: ph + m.bottom,
      tabindex: 0,
      role: "button",
      "aria-label": `${label}: ${fmtDur(x.total)} ${isActual ? t("chart.actual") : t("chart.predicted")}`,
    }, hits);
    bindHover(hit, () => {
      const note = isActual
        ? t("week.actual", { t: fmtDur(x.total) })
        : d.partial
          ? t("week.partial", { t: fmtDur(x.st.total) })
          : t("week.forecast", { t: fmtDur(x.total, true) });
      const foot = isActual
        ? t("week.wasPredicted", { t: fmtDur(x.fc, true) })
        : t("week.total", { t: fmtDur(x.total, true), lo: fmtDur(x.lo, true), hi: fmtDur(x.hi, true) });
      return [
        el("div", { class: "tt-title", text: dayFmt(parseIso(d.date)) }),
        el("div", { class: "tt-note", text: note }),
        ...ttRows(x.st, ids),
        el("div", { class: "tt-total", text: foot }),
        ttOverlap(x.st),
      ].filter(Boolean);
    });
    const open = () => {
      hideTooltip();
      goTo(d.date);
    };
    hit.addEventListener("click", open);
    hit.addEventListener("keydown", (e) => {
      if (e.key === "Enter" || e.key === " ") {
        e.preventDefault();
        open();
      }
    });
  });

  svg("line", { class: "baseline", x1: m.left, x2: W - m.right, y1: base + 0.5, y2: base + 0.5 }, root);
  root.append(hits);
  box.replaceChildren(root);
}

// ---------- finestra categorie ----------

const dialog = document.getElementById("categories-dialog");

// gli errori arrivano come codice dal backend e si traducono qui
function errorText(res) {
  return res.code ? t(`err.${res.code}`, res.params ?? {}) : res.error;
}

function showError(msg) {
  const box = document.getElementById("cat-error");
  box.textContent = msg || "";
  box.hidden = !msg;
}

function applySettings(res) {
  if (!res) return;
  if (res.ok === false) {
    showError(errorText(res));
    renderDialog(); // ripristina i campi modificati
    return;
  }
  showError("");
  state.settings = res;
  if (dialog.open) renderDialog();
  load();
}

function renderDialog() {
  const s = state.settings;
  if (!s) return;
  const counts = {};
  for (const cid of Object.values(s.assignments)) counts[cid] = (counts[cid] || 0) + 1;

  document.getElementById("cat-list").replaceChildren(
    ...s.categories.map((c) => {
      const input = el("input", { type: "text", maxlength: "40", "aria-label": t("cats.nameLabel") });
      input.value = c.name;
      input.addEventListener("keydown", (e) => {
        if (e.key === "Enter") input.blur();
        if (e.key === "Escape") {
          e.stopPropagation();
          input.value = c.name;
          input.blur();
        }
      });
      input.addEventListener("change", async () => {
        if (input.value.trim() === c.name) return;
        applySettings(await call("rename_category", c.id, input.value));
      });
      const del = el("button", { class: "icon-btn", type: "button", "aria-label": t("cats.delete", { name: c.name }), title: t("common.delete") });
      del.innerHTML = '<svg viewBox="0 0 16 16" aria-hidden="true"><path d="M3 4.5h10M6.5 4.5V3h3v1.5M4.5 4.5l.7 8.5h5.6l.7-8.5" fill="none" stroke="currentColor" stroke-width="1.4" stroke-linecap="round" stroke-linejoin="round"/></svg>';
      del.addEventListener("click", async () => {
        const n = counts[c.id] || 0;
        const msg = n ? t("cats.confirmDeleteApps", { name: c.name, n }) : t("cats.confirmDelete", { name: c.name });
        if (!confirm(msg)) return;
        applySettings(await call("delete_category", c.id));
      });
      const n = counts[c.id] || 0;
      return el("li", { class: "cat-item" }, [
        swatch(c.id),
        input,
        el("span", { class: "cat-count", text: n === 1 ? t("cats.count1") : t("cats.countN", { n }) }),
        del,
      ]);
    })
  );

  const full = s.categories.length >= s.max_categories;
  const addInput = document.getElementById("cat-add-name");
  addInput.disabled = full;
  addInput.placeholder = full ? t("cats.max", { n: s.max_categories }) : t("cats.namePlaceholder");
  document.getElementById("cat-add-btn").disabled = full;

  const apps = s.apps.slice().sort((a, b) => a.name.localeCompare(b.name, locale()));
  document.getElementById("assign-list").replaceChildren(
    ...apps.map((a) =>
      el("li", { class: "assign-item" }, [
        swatch(s.assignments[a.name] ?? "none"),
        el("span", { class: "n", text: a.name, title: a.name }),
        el("span", { class: "kind", text: t(`kind.${a.kind}`) }),
        categorySelect(a.name, s.assignments[a.name] ?? null),
      ])
    )
  );
}

function openDialog() {
  showError("");
  renderDialog();
  dialog.showModal();
}

document.getElementById("open-categories").addEventListener("click", openDialog);
document.getElementById("classify-open").addEventListener("click", openDialog);
document.getElementById("close-categories").addEventListener("click", () => dialog.close());
dialog.addEventListener("click", (e) => {
  if (e.target === dialog) dialog.close(); // clic sullo sfondo
});
document.getElementById("cat-add").addEventListener("submit", async (e) => {
  e.preventDefault();
  const input = document.getElementById("cat-add-name");
  const res = await call("add_category", input.value);
  if (res?.ok) input.value = "";
  applySettings(res);
});

// ---------- impostazioni: registrazione e avvio con Windows ----------

const settingsDialog = document.getElementById("settings-dialog");

function loggerText(status) {
  const key = ["running", "paused", "stopped"].includes(status) ? status : "stopped";
  return { chip: t(`status.${key}`), help: t(`status.${key}.help`), button: t(`status.${key}.button`) };
}

function renderStatus() {
  const s = state.status;
  if (!s) return;
  const txt = loggerText(s.logger);
  const chip = document.getElementById("logger-chip");
  chip.hidden = false;
  chip.title = t("status.chipTitle", { status: txt.chip });
  chip.querySelector(".status-dot").className = `status-dot ${s.logger}`;
  document.getElementById("logger-chip-text").textContent = txt.chip;

  document.getElementById("settings-dot").className = `status-dot ${s.logger}`;
  document.getElementById("settings-status").textContent = txt.chip;
  document.getElementById("settings-status-help").textContent = txt.help;
  document.getElementById("settings-logger-btn").textContent = txt.button;
  document.getElementById("autostart-switch").setAttribute("aria-checked", String(Boolean(s.autostart)));
  document.getElementById("data-dir").textContent = s.data_dir;
}

async function refreshStatus() {
  try {
    state.status = await call("get_status");
    renderStatus();
  } catch (err) {
    console.error(err);
  }
}

async function settingsAction(run) {
  const error = document.getElementById("settings-error");
  const buttons = settingsDialog.querySelectorAll(".dialog-body button");
  error.hidden = true;
  buttons.forEach((b) => (b.disabled = true));
  try {
    state.status = await run();
    renderStatus();
  } catch (err) {
    error.textContent = t("settings.failed", { msg: err?.message ?? err });
    error.hidden = false;
  } finally {
    buttons.forEach((b) => (b.disabled = false));
  }
}

document.getElementById("settings-logger-btn").addEventListener("click", () => {
  const current = state.status?.logger;
  settingsAction(() => (current === "stopped" ? call("start_logger") : call("set_paused", current === "running")));
});
document.getElementById("autostart-switch").addEventListener("click", () => {
  settingsAction(() => call("set_autostart", !state.status?.autostart));
});
document.getElementById("open-data-folder").addEventListener("click", () => {
  settingsAction(() => call("open_data_folder"));
});

function openSettings() {
  document.getElementById("settings-error").hidden = true;
  refreshStatus();
  settingsDialog.showModal();
}

document.getElementById("open-settings").addEventListener("click", openSettings);
document.getElementById("logger-chip").addEventListener("click", openSettings);
document.getElementById("close-settings").addEventListener("click", () => settingsDialog.close());
settingsDialog.addEventListener("click", (e) => {
  if (e.target === settingsDialog) settingsDialog.close(); // clic sullo sfondo
});

// lo stato può cambiare anche dall'icona vicino all'orologio o da Impostazioni di Windows
setInterval(refreshStatus, 10000);
document.addEventListener("visibilitychange", () => {
  if (!document.hidden) refreshStatus();
});

// ---------- render ----------

function renderCharts() {
  const data = state.data;
  if (!data) return;
  const showTable = state.view === "table";
  document.getElementById("hourly-chart").hidden = showTable;
  document.getElementById("hourly-table").hidden = !showTable;
  if (showTable) renderHourlyTable(data);
  else renderHourlyChart(data);
  renderWeek(data);
}

function render() {
  const data = state.data;
  if (!data) return;
  hideTooltip();
  renderHeader(data);
  renderFilters(data);
  renderSummary(data);
  renderHourlyLegend(data);
  renderApps(data);
  renderCharts();
}

// ---------- navigazione ----------

function goTo(iso) {
  const today = toIso(new Date());
  state.date = iso === today ? null : iso;
  load();
}

function shiftDay(delta) {
  const cur = state.data ? parseIso(state.data.date) : new Date();
  cur.setDate(cur.getDate() + delta);
  goTo(toIso(cur));
}

document.getElementById("prev-day").addEventListener("click", () => shiftDay(-1));
document.getElementById("next-day").addEventListener("click", () => shiftDay(1));
document.getElementById("go-today").addEventListener("click", () => goTo(toIso(new Date())));

document.addEventListener("keydown", (e) => {
  if (dialog.open || settingsDialog.open || e.target.closest?.("input, select, textarea, [role=button]")) return;
  if (e.key === "ArrowLeft") shiftDay(-1);
  if (e.key === "ArrowRight") shiftDay(1);
});

document.querySelectorAll(".seg button").forEach((btn) => {
  btn.addEventListener("click", () => {
    state.view = btn.dataset.view;
    document.querySelectorAll(".seg button").forEach((b) => b.setAttribute("aria-selected", String(b === btn)));
    renderCharts();
  });
});

let resizeFrame = 0;
new ResizeObserver(() => {
  cancelAnimationFrame(resizeFrame);
  resizeFrame = requestAnimationFrame(renderCharts);
}).observe(document.getElementById("main"));

// ---------- lingua ----------

function renderLanguagePicker() {
  const select = document.getElementById("language-select");
  select.replaceChildren(
    ...LANGUAGES.map((l) => {
      const opt = el("option", { value: l.id, text: l.name });
      if (l.id === currentLang) opt.selected = true;
      return opt;
    })
  );
}

document.getElementById("language-select").addEventListener("change", async (e) => {
  const res = await call("set_language", e.target.value);
  if (res?.ok === false) return;
  state.settings = res;
  setLanguage(res.language);
  renderLanguagePicker();
  renderStatus();
  if (dialog.open) renderDialog();
  render();
});

(async () => {
  try {
    state.settings = await call("get_settings");
  } catch (err) {
    console.error(err);
  }
  setLanguage(state.settings?.language ?? "en");
  renderLanguagePicker();
  load();
  refreshStatus();
})();
