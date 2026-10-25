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
  return findCategory(id)?.name ?? "Da classificare";
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

const dayFmt = new Intl.DateTimeFormat("it-IT", { weekday: "long", day: "numeric", month: "long" });

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

async function load() {
  const main = document.getElementById("main");
  main.classList.add("loading");
  try {
    state.data = await call("get_dashboard", state.date);
    if (state.category !== "all" && !state.data.categories.some((c) => c.id === state.category)) {
      state.category = "all";
    }
    render();
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
    text: `Alcune app erano in uso insieme: sommate fanno ${fmtDur(stack.rawSum)}, quindi la barra mostra la quota di ciascuna.`,
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
  document.getElementById("day-title").textContent = capitalize(dayFmt.format(d));
  const rel = { today: "Oggi", past: "Storico", future: "Previsione" }[data.relation];
  document.getElementById("day-relation").textContent = rel;
  document.getElementById("go-today").disabled = data.relation === "today";
  document.getElementById("mock-badge").hidden = !data.mock;
}

function renderFilters(data) {
  const box = document.getElementById("filters");
  const items = [{ id: "all", name: "Tutte" }, ...data.categories];
  box.replaceChildren(
    ...items.map((c) => {
      const chip = el("button", {
        class: "chip",
        role: "radio",
        "aria-checked": String(state.category === c.id),
      });
      if (c.id !== "all") chip.append(swatch(c.id));
      chip.append(document.createTextNode(c.name));
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
  const t = data.totals[state.category];
  const filtered = state.category !== "all";
  const suffix = filtered ? ` · ${catName(state.category)}` : "";
  const past = data.relation === "past";

  const label = {
    today: "Uso previsto oggi",
    past: "Utilizzo del giorno",
    future: "Uso previsto",
  }[data.relation];
  document.getElementById("hero-label").textContent = label + suffix;

  const value = document.getElementById("hero-value");
  const sub = document.getElementById("hero-sub");
  const progress = document.getElementById("hero-progress");
  sub.replaceChildren();

  const range = `tra ${fmtDur(t.p10, true)} e ${fmtDur(t.p90, true)}`;
  if (past) {
    value.textContent = fmtDur(t.actual);
    sub.append(`Previsto ${fmtDur(t.p50, true)} (${range})`);
    progress.hidden = true;
  } else {
    value.textContent = `~${fmtDur(t.p50, true)}`;
    sub.append(`Probabilmente ${range}`);
    if (data.relation === "today") {
      sub.append(" · finora ", el("strong", { text: fmtDur(t.actual) }));
      progress.hidden = false;
      const pct = Math.min(100, (t.actual / t.p50) * 100 || 0);
      document.getElementById("hero-progress-fill").style.width = `${pct}%`;
    } else {
      progress.hidden = true;
    }
  }

  // le statistiche seguono il filtro; per un giorno passato si usano i dati reali
  const totals = data.hours.map((h) => stackOf(h, past ? "actual" : "forecast", ids).total);
  const first = totals.findIndex((v) => v >= (filtered ? 3 : 5));
  const peak = totals.indexOf(Math.max(...totals));
  document.getElementById("stat-first-label").textContent = past ? "Primo utilizzo" : "Inizio previsto";
  document.getElementById("stat-first").textContent = first >= 0 ? fmtHour(first) : "—";
  document.getElementById("stat-peak").textContent = totals[peak] > 0 ? fmtHour(peak) : "—";

  const top = document.getElementById("stat-top");
  top.replaceChildren();
  if (!filtered) {
    document.getElementById("stat-top-label").textContent = "Categoria principale";
    const key = past ? "actual" : "p50";
    const best = data.categories.reduce((a, c) => (data.totals[c.id][key] > data.totals[a.id][key] ? c : a));
    top.append(swatch(best.id), best.name);
  } else {
    document.getElementById("stat-top-label").textContent = "App principale";
    const app = data.apps.find((a) => a.category === state.category);
    top.append(app ? app.name : "—");
  }
}

// ---------- grafico orario ----------

function renderHourlyLegend(data) {
  const ids = selectedCats(data);
  document.getElementById("hourly-sub").textContent =
    state.category === "all"
      ? "Altezza: tempo di uso del PC · colori: quota di ogni categoria"
      : `Minuti di uso di «${catName(state.category)}» in ogni ora`;

  const box = document.getElementById("hourly-legend");
  const items = ids.map((id) => el("span", { class: "legend-item" }, [swatch(id), catName(id)]));
  const extra = [];
  if (data.relation !== "future") {
    extra.push(el("span", { class: "legend-item" }, [el("span", { class: "key-actual" }), "Reale"]));
  }
  if (data.relation !== "past") {
    extra.push(el("span", { class: "legend-item" }, [el("span", { class: "key-forecast" }), "Previsto"]));
    extra.push(el("span", { class: "legend-item" }, [el("span", { class: "key-range" }), "Intervallo probabile"]));
  }
  if (data.relation !== "future") {
    extra.push(el("span", { class: "legend-item" }, [el("span", { class: "key-tick" }), "Era previsto"]));
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

  const root = svg("svg", { viewBox: `0 0 ${W} ${H}`, height: H, role: "img", "aria-label": "Minuti di utilizzo ora per ora" });

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
      "aria-label": `${fmtHour(hr.hour)}: ${fmtDur(st.total)} ${isActual ? "reali" : "previsti"}`,
    }, hits);
    bindHover(hit, () => {
      const head = state.category === "all"
        ? `${isActual ? "PC in uso" : "PC in uso, previsto"}: ${fmtDur(st.total)}`
        : isActual ? "Utilizzo reale" : "Previsione";
      const foot = isActual
        ? `Era previsto ${fmtDur(fc)}`
        : `Probabilmente tra ${fmtDur(b.p10)} e ${fmtDur(b.p90)}`;
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
    svg("text", { class: "now-label accent", x, y: m.top - 9, "text-anchor": "middle", text: "adesso" }, root);
  }

  root.append(hits); // i bersagli stanno sopra a tutto
  box.replaceChildren(root);
}

function renderHourlyTable(data) {
  const ids = selectedCats(data);
  const all = state.category === "all";
  const head = el("tr", {}, [
    el("th", { text: "Ora" }),
    ...(all ? ids.map((id) => el("th", { text: catName(id) })) : []),
    el("th", { text: all ? "PC in uso" : catName(state.category) }),
    el("th", { text: "Intervallo previsto" }),
    el("th", { text: "Dato" }),
  ]);
  const rows = data.hours.map((hr) => {
    const st = stackOf(hr, hr.actual ? "actual" : "forecast", ids);
    const b = hr.band[state.category];
    return el("tr", {}, [
      el("td", { text: `${fmtHour(hr.hour)}–${fmtHour((hr.hour + 1) % 24)}` }),
      ...(all ? ids.map((id) => el("td", { text: fmtDur(st.raw[id]) })) : []),
      el("td", { text: fmtDur(st.total) }),
      el("td", { text: `${fmtDur(b.p10)} – ${fmtDur(b.p90)}` }),
      el("td", { class: "state", text: hr.actual ? "reale" : "previsto" }),
    ]);
  });
  const note = all
    ? el("p", { class: "card-sub", text: "Le categorie possono sovrapporsi, quindi la loro somma può superare il tempo di uso del PC." })
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
    "aria-label": `Categoria di ${appName}`,
  });
  sel.append(el("option", { value: "", text: "Da classificare" }));
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
    missing === 1 ? "1 app o sito da classificare" : `${missing} app e siti da classificare`;
}

function renderApps(data) {
  const title = { today: "App e siti di oggi", past: "App e siti usati", future: "App e siti previsti" }[data.relation];
  document.getElementById("apps-title").textContent = title;
  renderClassifyBanner();

  const list = document.getElementById("app-list");
  let apps = data.apps.filter((a) => state.category === "all" || a.category === state.category);
  if (data.relation === "past") apps = apps.slice().sort((a, b) => b.actual - a.actual);
  if (!apps.length) {
    list.replaceChildren(el("li", { class: "empty", text: "Nessuna app in questa categoria." }));
    return;
  }
  const max = Math.max(60, ...apps.map((a) => Math.max(a.p90, a.actual)));
  const pct = (v) => `${Math.min(100, (v / max) * 100)}%`;

  list.replaceChildren(
    ...apps.map((a) => {
      const color = catColor(a.category);
      let time;
      const meta = [];
      if (data.relation === "past") {
        time = fmtDur(a.actual);
        meta.push(`previsto ${fmtDur(a.p50, true)}`);
      } else {
        time = `~${fmtDur(a.p50, true)}`;
        if (data.relation === "today" && a.actual >= 1) meta.push(`finora ${fmtDur(a.actual)}`);
        meta.push(`tra ${fmtDur(a.p10, true)} e ${fmtDur(a.p90, true)}`);
        if (!(data.relation === "today" && a.actual >= 1)) meta.push(`apertura ${Math.round(a.probability * 100)}%`);
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
          el("span", { class: "kind", text: a.kind }),
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

  const root = svg("svg", { viewBox: `0 0 ${W} ${H}`, height: H, role: "img", "aria-label": "Ore di utilizzo per giorno della settimana" });
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
    svg("text", { class: cls, x: cx, y: H - 8, "text-anchor": "middle", text: d.label }, root);
    if (selected) svg("rect", { class: "sel-mark", x: cx - 8, y: H - 3, width: 16, height: 2, rx: 1 }, root);

    const hit = svg("rect", {
      class: "hit clickable",
      x: m.left + i * band,
      y: m.top,
      width: band,
      height: ph + m.bottom,
      tabindex: 0,
      role: "button",
      "aria-label": `${d.label}: ${fmtDur(x.total)} ${isActual ? "reali" : "previsti"}`,
    }, hits);
    bindHover(hit, () => {
      const note = isActual
        ? `Utilizzo reale: ${fmtDur(x.total)}`
        : d.partial
          ? `Finora ${fmtDur(x.st.total)}, il resto è previsto`
          : `Previsione: ~${fmtDur(x.total, true)}`;
      const foot = isActual
        ? `Era previsto ${fmtDur(x.fc, true)}`
        : `In totale ~${fmtDur(x.total, true)} · tra ${fmtDur(x.lo, true)} e ${fmtDur(x.hi, true)}`;
      return [
        el("div", { class: "tt-title", text: capitalize(dayFmt.format(parseIso(d.date))) }),
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

function showError(msg) {
  const box = document.getElementById("cat-error");
  box.textContent = msg || "";
  box.hidden = !msg;
}

function applySettings(res) {
  if (!res) return;
  if (res.ok === false) {
    showError(res.error);
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
      const input = el("input", { type: "text", maxlength: "40", "aria-label": "Nome categoria" });
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
      const del = el("button", { class: "icon-btn", type: "button", "aria-label": `Elimina ${c.name}`, title: "Elimina" });
      del.innerHTML = '<svg viewBox="0 0 16 16" aria-hidden="true"><path d="M3 4.5h10M6.5 4.5V3h3v1.5M4.5 4.5l.7 8.5h5.6l.7-8.5" fill="none" stroke="currentColor" stroke-width="1.4" stroke-linecap="round" stroke-linejoin="round"/></svg>';
      del.addEventListener("click", async () => {
        const n = counts[c.id] || 0;
        const msg = n
          ? `Eliminare «${c.name}»? Le sue ${n} app torneranno da classificare.`
          : `Eliminare «${c.name}»?`;
        if (!confirm(msg)) return;
        applySettings(await call("delete_category", c.id));
      });
      const n = counts[c.id] || 0;
      return el("li", { class: "cat-item" }, [
        swatch(c.id),
        input,
        el("span", { class: "cat-count", text: n === 1 ? "1 app" : `${n} app` }),
        del,
      ]);
    })
  );

  const full = s.categories.length >= s.max_categories;
  const addInput = document.getElementById("cat-add-name");
  addInput.disabled = full;
  addInput.placeholder = full ? `Massimo ${s.max_categories} categorie` : "Nuova categoria, es. Studio";
  document.getElementById("cat-add-btn").disabled = full;

  const apps = s.apps.slice().sort((a, b) => a.name.localeCompare(b.name, "it"));
  document.getElementById("assign-list").replaceChildren(
    ...apps.map((a) =>
      el("li", { class: "assign-item" }, [
        swatch(s.assignments[a.name] ?? "none"),
        el("span", { class: "n", text: a.name, title: a.name }),
        el("span", { class: "kind", text: a.kind }),
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
  if (dialog.open || e.target.closest?.("input, select, textarea, [role=button]")) return;
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

(async () => {
  try {
    state.settings = await call("get_settings");
  } catch (err) {
    console.error(err);
  }
  load();
})();
