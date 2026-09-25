/* Fayy — shade-aware routing, fully client-side. */
const D = "data/";
const PRESETS = [
  { name: "Gate Towers → North Reem (Bilshu'oum St) · 08:00 · 2.9 km", a: [54.4098, 24.4923], b: [54.3999, 24.5078], slot: 4 },
  { name: "North Reem → Marina Square · 16:00 · 3.5 km", a: [54.4064, 24.5100], b: [54.3972, 24.4872], slot: 20 },
  { name: "East Reem → Al Maryah Island · 16:00 · 4.1 km", a: [54.4122, 24.5051], b: [54.3899, 24.5015], slot: 20 },
];
const I18N = {
  en: {},
  ar: { tagline: "الظل الذي يعود. مسارات مظللة في جزيرتي الريم والمارية، أبوظبي.", mode: "الوضع", moto: "دراجة نارية", walk: "مشي", date: "التاريخ",
    time: "الوقت", pref: "تفضيل الظل", fastest: "الأسرع", balanced: "متوازن", maxshade: "أقصى ظل", trips: "رحلات تجريبية",
    hint: "أو انقر على الخريطة لتحديد A ثم B.", shortest: "الأقصر", dose: "جرعة الحرارة: وردية من 10 توصيلات",
    banner: "لا يوجد ظل تقريبًا الآن: لهذا يوجد حظر العمل في الخارج وقت الظهيرة (12:30–15:00، 15 يونيو–15 سبتمبر).",
    wait: "◆ أماكن انتظار مظللة قرب B" },
  ur: { tagline: "واپس آنے والا سایہ۔ جزیرہ الریم اور المریہ، ابوظہبی کے لیے سایہ دار راستے۔", mode: "طریقہ", moto: "موٹر سائیکل", walk: "پیدل", date: "تاریخ",
    time: "وقت", pref: "سایہ کی ترجیح", fastest: "تیز ترین", balanced: "متوازن", maxshade: "زیادہ سایہ", trips: "ڈیمو سفر",
    hint: "یا نقشے پر کلک کر کے A پھر B منتخب کریں۔", shortest: "مختصر ترین", dose: "حرارت کی خوراک: 10 ڈیلیوریز کی شفٹ",
    banner: "اس وقت تقریباً کوئی سایہ نہیں: اسی لیے دوپہر میں باہر کام پر پابندی ہے (12:30–15:00، 15 جون–15 ستمبر)۔",
    wait: "◆ B کے قریب سایہ دار انتظار کی جگہیں" },
};

const S = { mode: "moto", date: 0, slot: 20, k: 3, A: null, B: null, lang: "en", playing: null, tab: "route" };
let meta, stats, fleet = null, graphs = {}, shadowCache = {}, map, heatNow = null;

const $ = (id) => document.getElementById(id);
const fmtSlot = (s) => `${s.slice(0, 2)}:${s.slice(2)}`;
const slotIndex = () => S.date * meta.slots.length + S.slot;
const t = (key, fallback) => (I18N[S.lang] && I18N[S.lang][key]) || fallback;

/* ---------- graph + routing ---------- */
async function loadGraph(mode) {
  if (graphs[mode]) return graphs[mode];
  const g = await (await fetch(`${D}graph_${mode}.json`)).json();
  const n = g.nodes.length;
  const adj = Array.from({ length: n }, () => []);
  g.edges.forEach((e, i) => {
    adj[e[0]].push([i, e[1], false]);
    if (g.bidirectional) adj[e[1]].push([i, e[0], true]);
  });
  const hasEdge = new Uint8Array(n);
  adj.forEach((a, i) => { if (a.length) hasEdge[i] = 1; });
  graphs[mode] = { ...g, adj, hasEdge };
  return graphs[mode];
}

function nearestNode(g, lon, lat) {
  let best = -1, bd = Infinity;
  const c = Math.cos((lat * Math.PI) / 180);
  for (const [i, x, y] of g.nodes) {
    if (!g.hasEdge[i]) continue;
    const d = ((x - lon) * c) ** 2 + (y - lat) ** 2;
    if (d < bd) { bd = d; best = i; }
  }
  return best;
}

class Heap {
  constructor() { this.a = []; }
  push(p, v) { const a = this.a; a.push([p, v]); let i = a.length - 1;
    while (i > 0) { const j = (i - 1) >> 1; if (a[j][0] <= a[i][0]) break; [a[i], a[j]] = [a[j], a[i]]; i = j; } }
  pop() { const a = this.a, top = a[0], last = a.pop();
    if (a.length) { a[0] = last; let i = 0;
      for (;;) { const l = 2 * i + 1, r = l + 1; let m = i;
        if (l < a.length && a[l][0] < a[m][0]) m = l; if (r < a.length && a[r][0] < a[m][0]) m = r;
        if (m === i) break; [a[i], a[m]] = [a[m], a[i]]; i = m; } }
    return top; }
  get size() { return this.a.length; }
}

function dijkstra(g, src, dst, k, si) {
  const n = g.nodes.length, dist = new Float64Array(n).fill(Infinity), prev = new Int32Array(n).fill(-1), prevRev = new Uint8Array(n);
  dist[src] = 0; const h = new Heap(); h.push(0, src);
  while (h.size) {
    const [d, u] = h.pop();
    if (u === dst) break;
    if (d > dist[u]) continue;
    for (const [ei, v, rev] of g.adj[u]) {
      const e = g.edges[ei], w = e[3] * (1 + k * e[5][si] / 100);
      if (d + w < dist[v]) { dist[v] = d + w; prev[v] = ei; prevRev[v] = rev ? 1 : 0; h.push(dist[v], v); }
    }
  }
  if (!isFinite(dist[dst])) return null;
  const path = []; let v = dst;
  while (v !== src) { const ei = prev[v], e = g.edges[ei], rev = prevRev[v]; path.push([ei, rev]); v = rev ? e[1] : e[0]; }
  path.reverse();
  let time = 0, sun = 0, len = 0; const coords = [];
  for (const [ei, rev] of path) {
    const e = g.edges[ei]; time += e[3]; len += e[2]; sun += e[3] * e[5][si] / 100;
    const c = rev ? [...e[4]].reverse() : e[4];
    coords.push(...(coords.length ? c.slice(1) : c));
  }
  return { time, sun, len, coords, key: path.map((p) => p[0]).join(",") };
}

/* ---------- map ---------- */
function initMap() {
  try { map = makeMap(); } catch (err) {
    document.getElementById("map").innerHTML = '<div class="nogl">This demo needs WebGL. Please enable hardware acceleration in your browser settings, or try Chrome/Edge/Firefox.</div>';
    console.error(err); return;
  }
  setupMap();
}

function makeMap() {
  return new maplibregl.Map({
    container: "map", style: "https://tiles.openfreemap.org/styles/positron",
    center: [54.399, 24.4955], zoom: 14.6, pitch: 55, bearing: -30, antialias: true,
    attributionControl: { customAttribution: "Map data © OpenStreetMap contributors, Overture Maps Foundation" },
  });
}

function setupMap() {
  map.addControl(new maplibregl.NavigationControl(), "top-right");
  map.on("load", async () => {
    const empty = { type: "FeatureCollection", features: [] };
    map.addSource("shadows", { type: "geojson", data: empty });
    map.addSource("buildings", { type: "geojson", data: `${D}buildings.geojson` });
    ["route-short", "route-fayy", "pts", "wait", "canopy"].forEach((s) => map.addSource(s, { type: "geojson", data: empty }));
    map.addLayer({ id: "shadows", type: "fill", source: "shadows", paint: { "fill-color": "#1e293b", "fill-opacity": 0.55 } });
    map.addLayer({ id: "bld", type: "fill-extrusion", source: "buildings", paint: {
      "fill-extrusion-color": ["interpolate", ["linear"], ["get", "height"], 0, "#f8fafc", 100, "#e2e8f0", 300, "#cbd5e1"],
      "fill-extrusion-height": ["get", "height"], "fill-extrusion-opacity": 0.9 } });
    map.addLayer({ id: "canopy-glow", type: "line", source: "canopy", layout: { visibility: "none", "line-cap": "round" },
      paint: { "line-color": "#ef4444", "line-width": 18, "line-opacity": 0.35, "line-blur": 8 } });
    map.addLayer({ id: "canopy", type: "line", source: "canopy", layout: { visibility: "none", "line-cap": "round" },
      paint: { "line-color": "#dc2626", "line-width": 6 } });
    map.addLayer({ id: "canopy-n", type: "symbol", source: "canopy", layout: { visibility: "none", "symbol-placement": "line-center",
      "text-field": ["to-string", ["get", "n"]], "text-size": 13, "text-font": ["Noto Sans Bold"], "text-allow-overlap": true },
      paint: { "text-color": "#fff", "text-halo-color": "#b91c1c", "text-halo-width": 3 } });
    map.addLayer({ id: "route-short", type: "line", source: "route-short", layout: { "line-cap": "round", "line-join": "round" },
      paint: { "line-color": "#ea580c", "line-width": 4, "line-dasharray": [1.5, 1.5] } });
    map.addLayer({ id: "route-fayy-glow", type: "line", source: "route-fayy", paint: { "line-color": "#06b6d4", "line-width": 12, "line-opacity": 0.3, "line-blur": 4 } });
    map.addLayer({ id: "route-fayy", type: "line", source: "route-fayy", layout: { "line-cap": "round", "line-join": "round" },
      paint: { "line-color": "#0891b2", "line-width": 5 } });
    map.addLayer({ id: "wait", type: "circle", source: "wait", paint: { "circle-radius": 7, "circle-color": "#10b981", "circle-stroke-color": "#fff", "circle-stroke-width": 2 } });
    map.addLayer({ id: "pts", type: "circle", source: "pts", paint: { "circle-radius": 9, "circle-color": ["match", ["get", "l"], "A", "#ea580c", "#0891b2"], "circle-stroke-color": "#fff", "circle-stroke-width": 2 } });
    map.addLayer({ id: "pts-l", type: "symbol", source: "pts", layout: { "text-field": ["get", "l"], "text-size": 12, "text-font": ["Noto Sans Bold"], "text-allow-overlap": true }, paint: { "text-color": "#fff" } });
    map.on("click", onMapClick);
    await refresh();
    runPreset(1);
  });
}

async function showShadows() {
  const key = `${meta.dates[S.date].key}_${meta.slots[S.slot]}`;
  if (!shadowCache[key]) shadowCache[key] = fetch(`${D}shadows_${key}.geojson`).then((r) => r.json());
  const data = await shadowCache[key];
  if (key === `${meta.dates[S.date].key}_${meta.slots[S.slot]}`) map.getSource("shadows").setData(data);
  // prefetch next
  const nk = `${meta.dates[S.date].key}_${meta.slots[(S.slot + 1) % meta.slots.length]}`;
  if (!shadowCache[nk]) shadowCache[nk] = fetch(`${D}shadows_${nk}.geojson`).then((r) => r.json());
}

function onMapClick(e) {
  const p = [e.lngLat.lng, e.lngLat.lat];
  if (!S.A || S.B) { S.A = p; S.B = null; } else S.B = p;
  route();
}

function runPreset(i, trip) {
  const p = trip || PRESETS[i];
  S.A = p.a; S.B = p.b;
  if (p.slot != null) { S.slot = p.slot; $("slider").value = S.slot; }
  const pad = window.innerWidth > 700 ? { top: 120, bottom: 120, left: 420, right: 120 } : 60;
  map.fitBounds([[Math.min(p.a[0], p.b[0]), Math.min(p.a[1], p.b[1])], [Math.max(p.a[0], p.b[0]), Math.max(p.a[1], p.b[1])]], { padding: pad, pitch: 55, bearing: -30, duration: 800 });
  refresh();
}

/* ---------- UI ---------- */
function setSeg(id, val) { document.querySelectorAll(`#${id} button`).forEach((b) => b.classList.toggle("on", b.dataset.v === String(val))); }

function updateLabels() {
  const info = meta.index[slotIndex()];
  $("timeLabel").textContent = fmtSlot(meta.slots[S.slot]);
  $("sunLabel").textContent = info.alt > 0 ? `☀ ${info.alt.toFixed(0)}° alt · ${info.az.toFixed(0)}° az` : "sun below horizon";
  const sunShare = S.mode === "moto" ? info.moto_sun : info.walk_sun;
  $("banner").classList.toggle("hidden", !(info.alt > 70 || sunShare > 0.88));
}

async function refresh() { updateLabels(); await showShadows(); await route(); }

function fmtMin(s) { return `${(s / 60).toFixed(1)} min`; }

async function route() {
  const g = await loadGraph(S.mode);
  const pts = [];
  if (S.A) pts.push({ type: "Feature", properties: { l: "A" }, geometry: { type: "Point", coordinates: S.A } });
  if (S.B) pts.push({ type: "Feature", properties: { l: "B" }, geometry: { type: "Point", coordinates: S.B } });
  map.getSource("pts").setData({ type: "FeatureCollection", features: pts });
  const empty = { type: "FeatureCollection", features: [] };
  if (!S.A || !S.B) {
    ["route-short", "route-fayy", "wait"].forEach((s) => map.getSource(s).setData(empty));
    $("result").classList.add("hidden");
    $("hint").textContent = S.A ? "Now click to set B." : t("hint", "Or click the map to set A, then B.");
    return;
  }
  $("hint").textContent = t("hint", "Or click the map to set A, then B.");
  const src = nearestNode(g, ...S.A), dst = nearestNode(g, ...S.B), si = slotIndex();
  const short = dijkstra(g, src, dst, 0, si), fayy = dijkstra(g, src, dst, S.k, si);
  if (!short || !fayy) { $("headline").textContent = "No route found between these points."; $("result").classList.remove("hidden"); return; }
  const line = (r) => ({ type: "Feature", properties: {}, geometry: { type: "LineString", coordinates: r.coords } });
  map.getSource("route-short").setData(line(short));
  map.getSource("route-fayy").setData(line(fayy));
  $("sTime").textContent = fmtMin(short.time);
  $("fTime").textContent = fmtMin(fayy.time);
  $("sSun").textContent = `☀ ${fmtMin(short.sun)} in direct sun`;
  $("fSun").textContent = `☀ ${fmtMin(fayy.sun)} in direct sun`;
  let head;
  if (meta.index[si].alt <= 2) head = "Sun is down: the whole area is in shade.";
  else if (short.key === fayy.key) head = "This is already the shadiest route.";
  else {
    const dMin = (fayy.time - short.time) / 60;
    const less = short.sun > 0 ? Math.round(100 * (1 - fayy.sun / short.sun)) : 0;
    head = `Fayy: ${dMin >= 0 ? "+" : "−"}${Math.abs(dMin).toFixed(1)} min, ${less}% less direct sun`;
  }
  $("headline").textContent = head;
  S.saved = Math.max(0, short.sun - fayy.sun);
  showHeat();
  $("result").classList.remove("hidden");
  showWaitingSpots(dst, si);
  heatDose(g);
}

/* ---------- tabs: rider shift + shade planner ---------- */
function setTab(tab) {
  S.tab = tab;
  setSeg("tabs", tab);
  ["route", "shift", "canopy"].forEach((k) => $(`tab-${k}`).classList.toggle("hidden", k !== tab));
  const vis = tab === "canopy" ? "visible" : "none";
  ["canopy-glow", "canopy", "canopy-n"].forEach((l) => map && map.getLayer(l) && map.setLayoutProperty(l, "visibility", vis));
  const routeVis = tab === "canopy" ? "none" : "visible";
  ["route-short", "route-fayy-glow", "route-fayy", "wait", "pts", "pts-l"].forEach((l) => map && map.getLayer(l) && map.setLayoutProperty(l, "visibility", routeVis));
  if (tab === "shift") renderShift();
  if (tab === "canopy") renderCanopy();
}

async function renderShift() {
  if (!fleet) return;
  const g = await loadGraph("moto");
  $("shiftDate").textContent = `Date: ${meta.dates[S.date].label}.`;
  const rows = fleet.shift.map((d) => {
    const si = S.date * meta.slots.length + meta.slots.indexOf(d.slot);
    const r = fleet.restaurants[d.r], tw = fleet.towers[d.t];
    const src = nearestNode(g, r[1], r[2]), dst = nearestNode(g, tw[1], tw[2]);
    const sh = dijkstra(g, src, dst, 0, si), fy = dijkstra(g, src, dst, fleet.k, si);
    return { d, r, tw, s: sh ? sh.sun / 60 : 0, f: fy ? fy.sun / 60 : 0 };
  });
  const ts = rows.reduce((a, x) => a + x.s, 0), tf = rows.reduce((a, x) => a + x.f, 0);
  const pct = ts > 0 ? Math.round(100 * (1 - tf / ts)) : 0;
  $("shiftHead").textContent = `This shift: ${(ts - tf).toFixed(1)} fewer minutes in direct sun (${pct}%)`;
  $("shiftNote").classList.toggle("hidden", pct >= 10);
  $("shiftS").textContent = `${ts.toFixed(1)} min`;
  $("shiftF").textContent = `${tf.toFixed(1)} min`;
  const W = 300, H = 150, L = 22, B = 18, T = 8, max = Math.max(1, ...rows.map((x) => x.s));
  const gw = (W - L - 4) / rows.length, bw = gw * 0.38, y = (v) => H - B - (v / max) * (H - B - T);
  let svg = "";
  for (let v = 0; v <= max; v += max > 4 ? 2 : 1) svg += `<line x1="${L}" x2="${W - 2}" y1="${y(v)}" y2="${y(v)}" stroke="#e2e8f0"/><text x="${L - 3}" y="${y(v) + 3}" text-anchor="end">${v}</text>`;
  rows.forEach((x, i) => {
    const x0 = L + i * gw + gw * 0.1;
    const tip = `#${i + 1} ${fmtSlot(x.d.slot)} ${x.r[0]} → ${x.tw[0]}: shortest ${x.s.toFixed(1)} min, Fayy ${x.f.toFixed(1)} min in sun`;
    svg += `<g class="bar" data-i="${i}"><title>${tip}</title><rect x="${x0}" y="${y(x.s)}" width="${bw}" height="${y(0) - y(x.s)}" fill="#ea580c"/>`
      + `<rect x="${x0 + bw}" y="${y(x.f)}" width="${bw}" height="${y(0) - y(x.f)}" fill="#0891b2"/><rect x="${x0}" y="${T}" width="${bw * 2}" height="${H - B - T}" fill="transparent"/></g>`;
    if (i % 2 === 0) svg += `<text x="${x0 + bw}" y="${H - 5}" text-anchor="middle">${fmtSlot(x.d.slot)}</text>`;
  });
  $("shiftChart").innerHTML = svg;
  $("shiftChart").onclick = (e) => {
    const b = e.target.closest(".bar"); if (!b) return;
    const x = rows[+b.dataset.i];
    S.mode = "moto"; setSeg("mode", "moto"); S.k = fleet.k; setSeg("pref", S.k);
    setTab("route");
    runPreset(-1, { a: [x.r[1], x.r[2]], b: [x.tw[1], x.tw[2]], slot: meta.slots.indexOf(x.d.slot) });
  };
}

function renderCanopy() {
  if (!fleet) return;
  const top = fleet.canopy[meta.dates[S.date].key] || [];
  $("canopyDate").textContent = meta.dates[S.date].label;
  map.getSource("canopy").setData({ type: "FeatureCollection", features: top.map((c, i) => ({ type: "Feature", properties: { n: i + 1 }, geometry: { type: "LineString", coordinates: c.coords } })) });
  $("canopyList").innerHTML = top.map((c) => `<li><b>${c.minutes.toFixed(1)} rider-min</b> in sun · ${c.name || "Unnamed street"}<div class="muted">${c.length_m} m segment · on ${c.trips} Fayy trips</div></li>`).join("");
  $("canopyList").onclick = (e) => {
    const li = e.target.closest("li"); if (!li) return;
    map.flyTo({ center: top[[...li.parentNode.children].indexOf(li)].mid, zoom: 16.5, duration: 900 });
  };
  if (top.length) {
    const xs = top.flatMap((c) => c.coords);
    const lo = xs.reduce((a, p) => [Math.min(a[0], p[0]), Math.min(a[1], p[1])], [180, 90]);
    const hi = xs.reduce((a, p) => [Math.max(a[0], p[0]), Math.max(a[1], p[1])], [-180, -90]);
    map.fitBounds([lo, hi], { padding: window.innerWidth > 700 ? { top: 80, bottom: 80, left: 400, right: 80 } : 40, duration: 800 });
  }
}

/* Live heat from Open-Meteo (no key); the line stays hidden if the fetch fails. */
async function fetchHeat() {
  try {
    const url = `https://api.open-meteo.com/v1/forecast?latitude=${((meta.bbox[1] + meta.bbox[3]) / 2).toFixed(4)}&longitude=${((meta.bbox[0] + meta.bbox[2]) / 2).toFixed(4)}&current=temperature_2m,apparent_temperature&timezone=Asia%2FDubai`;
    const c = (await (await fetch(url)).json()).current;
    if (typeof c.temperature_2m === "number" && typeof c.apparent_temperature === "number") heatNow = c;
  } catch (err) { heatNow = null; }
  showHeat();
}

function showHeat() {
  const el = $("heat");
  if (!heatNow || S.saved == null) { el.classList.add("hidden"); return; }
  el.textContent = `🌡 Now ${Math.round(heatNow.temperature_2m)}°C, feels like ${Math.round(heatNow.apparent_temperature)}°C. Fayy saves ${(S.saved / 60).toFixed(1)} min in direct sun.`;
  el.classList.remove("hidden");
}

/* Rider waiting spots: 3 nearest shaded street points within 150 m of B. */
function showWaitingSpots(dst, si) {
  const g = graphs[S.mode];
  const [, bx, by] = g.nodes[dst];
  const c = Math.cos((by * Math.PI) / 180), M = 111320;
  const dist = (p, q) => Math.hypot((p[0] - q[0]) * c * M, (p[1] - q[1]) * M);
  const spots = [];
  for (const e of g.edges) {
    if (e[5][si] > 10) continue;
    const mid = e[4][Math.floor(e[4].length / 2)];
    const d = dist(mid, [bx, by]);
    if (d <= 150) spots.push([d, mid]);
  }
  spots.sort((a, b) => a[0] - b[0]);
  const picked = [];
  for (const s of spots) {
    if (picked.every((p) => dist(p[1], s[1]) > 30)) picked.push(s);
    if (picked.length === 3) break;
  }
  const show = meta.index[si].alt > 2 ? picked : [];
  map.getSource("wait").setData({ type: "FeatureCollection", features: show.map((p) => ({ type: "Feature", properties: {}, geometry: { type: "Point", coordinates: p[1] } })) });
  $("waitNote").classList.toggle("hidden", !show.length);
}

/* Heat dose: 10 deliveries alternating A->B / B->A across consecutive half-hour slots. */
function heatDose(g) {
  if (S.mode !== "moto") { $("doseOut").textContent = "Switch to Motorcycle to estimate a rider shift."; return; }
  const src = nearestNode(g, ...S.A), dst = nearestNode(g, ...S.B);
  let ss = 0, fs = 0;
  for (let j = 0; j < 10; j++) {
    const slot = Math.min(S.slot + j, meta.slots.length - 1), si = S.date * meta.slots.length + slot;
    const a = j % 2 ? dst : src, b = j % 2 ? src : dst;
    ss += dijkstra(g, a, b, 0, si)?.sun || 0;
    fs += dijkstra(g, a, b, S.k, si)?.sun || 0;
  }
  const saved = ss > 0 ? Math.round(100 * (1 - fs / ss)) : 0;
  $("doseOut").innerHTML = `Shortest: <b style="color:#ea580c">${(ss / 60).toFixed(0)} min</b> in sun · Fayy: <b style="color:#0891b2">${(fs / 60).toFixed(0)} min</b> (−${saved}%)`;
}

function applyLang() {
  document.documentElement.dir = S.lang === "en" ? "ltr" : "rtl";
  document.querySelectorAll("[data-i18n]").forEach((el) => {
    if (!el.dataset.en) el.dataset.en = el.textContent;
    el.textContent = t(el.dataset.i18n, el.dataset.en);
  });
  document.querySelectorAll("#lang button").forEach((b) => b.classList.toggle("on", b.dataset.lang === S.lang));
}

function togglePlay() {
  if (S.playing) { clearInterval(S.playing); S.playing = null; $("play").textContent = "▶"; $("play").classList.remove("on"); return; }
  $("play").textContent = "❚❚"; $("play").classList.add("on");
  S.playing = setInterval(() => { S.slot = (S.slot + 1) % meta.slots.length; $("slider").value = S.slot; refresh(); }, 600);
}

async function main() {
  [meta, stats] = await Promise.all([fetch(`${D}meta.json`).then((r) => r.json()), fetch(`${D}stats.json`).then((r) => r.json())]);
  fetch(`${D}fleet.json`).then((r) => r.json()).then((f) => { fleet = f; })
    .catch(() => document.querySelectorAll("#tabs [data-v=shift], #tabs [data-v=canopy]").forEach((b) => b.remove()));
  $("date").innerHTML = meta.dates.map((d, i) => `<button data-v="${i}" class="${i === 0 ? "on" : ""}">${d.label}</button>`).join("");
  $("slider").max = meta.slots.length - 1;
  $("slider").value = S.slot;
  $("presets").innerHTML = PRESETS.map((p, i) => `<button data-i="${i}">${p.name}</button>`).join("");
  $("stats").textContent = `Building heights (${stats.buildings}): ${stats.real} real (${stats.real_pct}%: ${stats.from_override} tower overrides, ${stats.with_height} measured, ${stats.from_floors} from floors) / ${stats.estimated} estimated from footprint / ${stats.defaulted} default 12 m.`;
  const seg = (id, fn) => { $(id).onclick = (e) => { const b = e.target.closest("button"); if (b) fn(b); }; };
  seg("mode", (b) => { S.mode = b.dataset.v; setSeg("mode", S.mode); refresh(); });
  seg("date", (b) => { S.date = +b.dataset.v; setSeg("date", S.date); refresh(); if (S.tab !== "route") setTab(S.tab); });
  seg("tabs", (b) => setTab(b.dataset.v));
  seg("pref", (b) => { S.k = +b.dataset.v; setSeg("pref", S.k); route(); });
  seg("presets", (b) => runPreset(+b.dataset.i));
  seg("lang", (b) => { S.lang = b.dataset.lang; applyLang(); });
  $("slider").oninput = (e) => { S.slot = +e.target.value; refresh(); };
  $("play").onclick = togglePlay;
  initMap();
  fetchHeat();
}
main();
