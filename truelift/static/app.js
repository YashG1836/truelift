// TrueLift prototype UI: the owner's partner-app screens, the "Inside Zomato" panel, a guided
// demo, and the How it works / Evidence / Money pages. Plain JS; talks to the FastAPI service,
// or replays precomputed answers when hosted as a static site.

// ---------------- formatting ----------------
const $ = (s, root = document) => root.querySelector(s);
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const inr = (x, sign = false) => {
  if (x === null || x === undefined || Number.isNaN(x)) return "–";
  const v = Math.round(x);
  return (v < 0 ? "−₹" : sign && v > 0 ? "+₹" : "₹") + Math.abs(v).toLocaleString("en-IN");
};
const inr2 = (x, sign = false) => { // with paise when needed (₹91.70), for per-order maths
  const v = Math.round(x * 100) / 100;
  const s = Math.abs(v).toLocaleString("en-IN", { minimumFractionDigits: Number.isInteger(v) ? 0 : 2, maximumFractionDigits: 2 });
  return (v < 0 ? "−₹" : sign && v > 0 ? "+₹" : "₹") + s;
};
const lakh = (x) => (x === null || x === undefined ? "–" : (x < 0 ? "−" : "") + "₹" + (Math.abs(x) / 1e5).toFixed(2) + " lakh");
const n0 = (x) => (x === null || x === undefined ? "–" : Math.round(x).toLocaleString("en-IN"));
const pct = (x) => (x === null || x === undefined ? "–" : Math.round(x * 100) + "%");
const cls = (x) => (x > 0 ? "pos" : x < 0 ? "neg" : "");
const cap = (s) => s.charAt(0).toUpperCase() + s.slice(1);
const when = (iso) => { // "14 Nov, 4:05 pm" from an ISO 8601 time with its zone
  if (!iso) return "";
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? String(iso) : d.toLocaleString("en-IN", { day: "numeric", month: "short", hour: "numeric", minute: "2-digit" });
};

// ---------------- data layer ----------------
// On GitHub Pages there is no server: STATIC points to precomputed answers from the real service
// (scripts/export_static.py), and offers are replayed week by week in the browser.
const STATIC = window.TRUELIFT_STATIC || null;
// Deep links: #tab=evidence, #r=233 (restaurant), #names=generic (no real restaurant names), or the
// older #evidence. Read once at start; the tab part is kept up to date as the visitor moves.
const LINK = (() => {
  const h = (location.hash || "").replace(/^#/, "");
  const q = new URLSearchParams(h.includes("=") ? h : h ? `tab=${h}` : "");
  return { tab: q.get("tab"), r: q.get("r") === null ? null : +q.get("r"), generic: q.get("names") === "generic", lang: q.get("lang") };
})();
// Owner texts in Hindi, Kannada and Gujarati are drafts: the switch appears only when the service
// enables them (TRUELIFT_LANGUAGES=1, after a native speaker's review: decision D4) or when a
// reviewer opens the page with #lang=hi, #lang=kn or #lang=gu. The words come from the service
// (config.i18n, the WhatsApp text and the offer's label), so page and service never disagree.
const LANG = { code: "en" };
const langOn = () => CFG.i18n && (CFG.languages_enabled || (LINK.lang && LINK.lang in CFG.i18n));
const T = (key, vars = {}) => {
  const src = (CFG.i18n?.[LANG.code] || CFG.i18n?.en)?.otp?.[key];
  return src === undefined ? null : src.replace(/\{(\w+)\}/g, (_, k) => vars[k]);
};
const TABS = ["overview", "demo", "how", "evidence", "money", "ops"];
// The service's constants, read once at start (GET /api/v1/config; data/config.json when static)
const CFG = { holdout_share: 0.1, consent_weeks: 4 };
const oneIn = () => Math.round(1 / CFG.holdout_share);
// With #names=generic the page shows "Burger place in Jayanagar" instead of the real listing name.
const shownName = (r) => (LINK.generic ? `${String(r.cuisines || r.name).split(",")[0].trim()} place #${r.restaurant_id}` : r.name);
const LOCAL = { offers: {}, next: 1 };
// One file per design. With no discount, minimum order, audience and time make no difference, so
// those designs share one key (the export writes exactly these keys; scripts/export_static.py key()).
// A percentage offer's key starts with its cap and percentage, e.g. "60p30-0-all-0-0".
const dkey = (d) => (d.discount > 0
  ? `${Math.round(d.discount)}${d.pct > 0 ? `p${Math.round(d.pct * 100)}` : ""}-${Math.round(d.min_order)}-${d.audience}-${d.offpeak_only ? 1 : 0}-${Math.round(d.reward)}`
  : `0-0-all-0-${Math.round(d.reward)}`);

// Offline bundle opened from disk (file://): browsers refuse fetch() there, so each data file is
// also shipped as a script that registers its JSON in window.TL_FILES (scripts/build_offline.py).
const FILE_MODE = location.protocol === "file:";
function fileGet(file) {
  const reg = (window.TL_FILES = window.TL_FILES || {});
  if (file in reg) return Promise.resolve(reg[file]);
  return new Promise((resolve, reject) => {
    const tag = document.createElement("script");
    tag.src = STATIC + file.replace(/\.json$/, ".js");
    tag.onload = () => (file in reg ? resolve(reg[file]) : reject(new Error("This offline file is damaged; unzip the bundle again.")));
    tag.onerror = () => reject(new Error("This combination isn't in the offline demo; the live version answers any design."));
    document.head.appendChild(tag);
  });
}

async function sget(file) {
  if (FILE_MODE) return fileGet(file);
  // one retry: a freshly published site can briefly miss files while the CDN catches up
  for (let attempt = 0; attempt < 2; attempt++) {
    try {
      const r = await fetch(STATIC + file);
      if (r.ok) return r.json();
      if (r.status !== 404 || attempt) break;
    } catch (e) { if (attempt) throw new Error("Couldn't load the demo data. Check your connection and try again."); }
    await new Promise((res) => setTimeout(res, 1200));
  }
  throw new Error("This combination isn't in the static demo; the live version answers any design.");
}

function localView(id) {
  const o = LOCAL.offers[id];
  if (!o) throw new Error("There is no such offer in this demo session.");
  // the consent record carries the moment this visitor approved, not the moment the demo was built (TL-022)
  const renewal = o.renewal_of ? { renewal_of: o.renewal_of, evidence_shown: o.evidence } : {};
  const consent = o.status === "awaiting_otp" ? null : { ...o.full.consent, approved_at: o.approvedAt, ...renewal };
  return { ...o.full, offer_id: +id, status: o.status, consent, weeks: o.full.weeks.slice(0, o.shown),
    renewal_of: o.renewal_of || null, renewed_by: o.renewed_by || null, evidence: o.evidence || null };
}

// What an approval period measured (the same fields as the service's evidence_of in api.py)
function evidenceOf(view) {
  const w = view.weeks[view.weeks.length - 1], m = w.measurement;
  return { offer_id: view.offer_id, weeks: w.week, extra_orders: m.orders.total, extra_orders_low: m.orders.low, extra_orders_high: m.orders.high,
    extra_profit: m.profit.total, extra_profit_low: m.profit.low, extra_profit_high: m.profit.high, chance_making_money: m.profit.prob_positive,
    verdict_code: m.verdict_code, verdict: m.verdict, forecast_at_approval: view.quote.profit_change * w.week };
}

async function staticApi(path, body) {
  let m;
  if (path === "/api/v1/restaurants") return sget("restaurants.json");
  if ((m = path.match(/^\/api\/v1\/restaurants\/(\d+)$/))) return sget(`${m[1]}/card.json`);
  if (path === "/api/v1/quote") return (await sget(`${body.restaurant_id}/${dkey(body.design)}.json`)).quote;
  if (path === "/api/v1/customers") return (await sget(`${body.restaurant_id}/${dkey(body.design)}.json`)).customers;
  if (path === "/api/v1/offers") {
    const f = await sget(`${body.restaurant_id}/${dkey(body.design)}.json`);
    if (!f.offer) throw new Error("Nothing to approve: this design has no discount.");
    const id = LOCAL.next++;
    LOCAL.offers[id] = { full: f.offer, otp: String(1000 + Math.floor(Math.random() * 9000)), shown: 0, status: "awaiting_otp", attempts: 0 };
    return { offer_id: id, demo_otp: LOCAL.offers[id].otp };
  }
  if ((m = path.match(/^\/api\/v1\/offers\/(\d+)$/))) return localView(m[1]);
  if ((m = path.match(/^\/api\/v1\/offers\/(\d+)\/renew$/))) {
    const o = LOCAL.offers[m[1]];
    if (!o || o.status !== "consent_expired") throw new Error("Only an offer whose approval period ended can be renewed.");
    if (o.renewed_by) throw new Error(`This offer was already renewed as offer ${o.renewed_by}.`);
    const id = LOCAL.next++;
    LOCAL.offers[id] = { full: o.full, otp: String(1000 + Math.floor(Math.random() * 9000)), shown: 0, status: "awaiting_otp", attempts: 0,
      renewal_of: +m[1], evidence: evidenceOf(localView(m[1])) };
    return { offer_id: id, demo_otp: LOCAL.offers[id].otp, renewal_of: +m[1], evidence: LOCAL.offers[id].evidence };
  }
  if ((m = path.match(/^\/api\/v1\/offers\/(\d+)\/approve$/))) {
    const o = LOCAL.offers[m[1]];
    if (o.status !== "awaiting_otp") throw new Error("This offer can't be approved again.");
    if (o.attempts >= 5) throw new Error("Too many wrong codes. Create the offer again to get a new OTP.");
    if (String(body.otp).trim() !== o.otp) {
      o.attempts += 1;
      const left = 5 - o.attempts;
      throw new Error(left > 0 ? `Wrong OTP. Check the code and try again (${left} attempt${left === 1 ? "" : "s"} left).`
        : "Too many wrong codes. Create the offer again to get a new OTP.");
    }
    o.status = "active";
    o.approvedAt = new Date().toISOString();
    if (o.renewal_of && LOCAL.offers[o.renewal_of]) LOCAL.offers[o.renewal_of].renewed_by = +m[1];
    return localView(m[1]);
  }
  if ((m = path.match(/^\/api\/v1\/offers\/(\d+)\/run_week$/))) {
    const o = LOCAL.offers[m[1]];
    if (o.status !== "active") throw new Error("This offer is not running.");
    o.shown = Math.min(o.shown + 1, o.full.weeks.length);
    if (o.shown >= o.full.weeks.length) o.status = o.full.status === "active" ? "consent_expired" : o.full.status;
    return localView(m[1]);
  }
  if ((m = path.match(/^\/api\/v1\/offers\/(\d+)\/decision$/))) { // honour keep and stop, like the service
    const o = LOCAL.offers[m[1]];
    if (body.action === "stop") {
      if (["stopped", "replaced"].includes(o.status)) throw new Error("This offer has already ended.");
      o.status = "stopped";
    } else if (o.status !== "active") throw new Error("Renewing a paused or expired offer needs a fresh quote and a new OTP.");
    return localView(m[1]);
  }
  if (path === "/api/v1/calls") return sget("calls.json");
  if (path === "/api/v1/evidence") return sget("evidence.json");
  if (path.startsWith("/api/v1/example")) { // the Money page's switches: six precomputed variants
    const q = new URLSearchParams(path.split("?")[1] || "");
    if (!q.toString()) return sget("example.json");
    return sget(`example-${q.get("commission_on") || "post_discount"}-${Math.round(100 * +(q.get("food_cost_share") || 0.37))}.json`);
  }
  if (path === "/api/v1/reset") { LOCAL.offers = {}; return { ok: true }; }
  throw new Error("Not available in the static demo: " + path);
}

// Each browser tab is its own demo session, so one visitor can never reset another's offers.
const SESSION = (() => {
  try {
    let id = sessionStorage.getItem("truelift-session");
    if (!id) { id = Math.random().toString(36).slice(2, 12) + Date.now().toString(36); sessionStorage.setItem("truelift-session", id); }
    return id;
  } catch (e) { return Math.random().toString(36).slice(2, 14); }
})();

async function api(path, body) {
  if (STATIC) return staticApi(path, body);
  const headers = { "X-Session": SESSION };
  const opt = body === undefined ? { headers } : { method: "POST", headers: { ...headers, "Content-Type": "application/json" }, body: JSON.stringify(body) };
  const r = await fetch(path, opt);
  const j = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(typeof j.detail === "string" && j.detail ? j.detail : `The service answered ${r.status}. Please try again.`);
  return j;
}

const cache = {};
const once = (key, fn) => (cache[key] ??= fn().catch((e) => { delete cache[key]; throw e; }));

// ---------------- state ----------------
const S = { rid: null, card: null, design: null, quote: null, offer: null, otp: null, screen: "home", busy: false, err: "",
  original: null, alt: {}, whatIf: {} };
const AUDIENCES = [["all", "Everyone"], ["new_to_restaurant", "New to you"], ["lapsed", "Stopped ordering"], ["targeted", "Let TrueLift choose"]];
const STATUS = {
  awaiting_otp: ["Waiting for your OTP", ""], active: ["Running", "good"], paused: ["Paused: it was losing money", "bad"],
  stopped: ["Stopped", ""], consent_expired: ["Approval period over", "red"],
};

// The create screen offers exactly the options the server lists on the restaurant's card, so the
// page can never ask for a design the static export did not write (audit TL-002).
function defaultDesign(card) {
  return { discount: card.design_options.default_depth, min_order: 0, audience: "all", offpeak_only: false, reward: 0, zomato_share: 0, pct: 0 };
}
function designOptions(card) {
  const o = card.design_options;
  return { depths: o.depths, mov: o.min_order, reward: o.reward, pcts: o.pct_offers || [] };
}
// Switching between "₹ off" and "% off up to ₹" keeps the amount: the cap of a percentage offer is
// the flat amount it replaces, and each cap has one percentage (engine.pct_for).
function withFormat(d, card, format) {
  const pcts = designOptions(card).pcts;
  if (format === "flat") return { ...d, pct: 0 };
  const p = pcts.find((x) => x.cap === d.discount) || pcts.find((x) => x.cap === card.design_options.default_depth) || pcts[0];
  return p ? { ...d, discount: p.cap, pct: p.pct } : d;
}

// ---------------- boot and navigation ----------------
async function boot() {
  document.querySelectorAll("nav button").forEach((b) => b.addEventListener("click", () => showTab(b.dataset.tab)));
  $("#tourBtn").addEventListener("click", () => Tour.start());
  $("#tourNext").addEventListener("click", () => Tour.next());
  $("#tourPrev").addEventListener("click", () => Tour.restart());
  $("#tourBack").addEventListener("click", () => Tour.back());
  $("#who").innerHTML = skeleton(4);
  $("#tourExit").addEventListener("click", () => Tour.stop());
  document.addEventListener("keydown", (e) => { // presenter keys while the guided demo is open
    if (!$("#tour").classList.contains("on") || e.target.matches("input, select, textarea") || e.ctrlKey || e.metaKey || e.altKey) return;
    const k = e.key;
    if (k === "ArrowRight" || k === "Enter") { e.preventDefault(); Tour.next(); }
    else if (k === "ArrowLeft") { e.preventDefault(); Tour.back(); }
    else if (k === "Escape") Tour.stop();
    else if (/^[1-9]$/.test(k)) Tour.jump(+k - 1);
    else if (k === "r" || k === "R") Tour.restart();
    else if (k === "f" || k === "F") Tour.jump(99);
    else if (k === "h" || k === "H") { Tour.stop(); showTab("how"); }
  });
  const now = new Date();
  $("#clock").textContent = now.toLocaleTimeString("en-IN", { hour: "2-digit", minute: "2-digit" });
  $("#screen").innerHTML = skeleton(5);
  firstVisitHint();
  try { Object.assign(CFG, await api("/api/v1/config")); } catch (e) { /* keep the defaults */ }
  // the Overview opens first; a link such as #tab=demo opens another tab
  showTab(TABS.includes(LINK.tab) ? LINK.tab : "overview");
  const data = await api("/api/v1/restaurants");
  const sel = $("#rest");
  const list = data.restaurants.filter((r) => r.menu_visits_per_week > 0)
    .sort((a, b) => (b.restaurant_id === data.demo_restaurant) - (a.restaurant_id === data.demo_restaurant) || a.name.localeCompare(b.name));
  sel.innerHTML = list.map((r) => `<option value="${r.restaurant_id}">${esc(shownName(r))} · ${esc(r.locality)}</option>`).join("");
  const first = list.some((r) => r.restaurant_id === LINK.r) ? LINK.r : data.demo_restaurant;
  sel.value = first;
  sel.addEventListener("change", () => openRestaurant(+sel.value).catch((e) => { $("#screen").innerHTML = errorCard(e, "this restaurant"); }));
  await openRestaurant(first);
  window.addEventListener("hashchange", () => { // a link to #tab=evidence on the page itself
    const h = location.hash.replace(/^#/, ""), q = new URLSearchParams(h.includes("=") ? h : `tab=${h}`);
    const t = q.get("tab") || "overview";
    if (TABS.includes(t) && !$(`#tab-${t}`).classList.contains("on")) showTab(t);
  });
}

function showTab(t) {
  document.querySelectorAll("nav button").forEach((b) => b.classList.toggle("on", b.dataset.tab === t));
  document.querySelectorAll(".tab").forEach((s) => s.classList.toggle("on", s.id === "tab-" + t));
  // the restaurant picker only matters on the Demo tab; elsewhere it takes no room in the header
  $(".pick label").style.display = $(".pick select").style.display = t === "demo" ? "" : "none";
  const keep = LINK.generic ? "names=generic" : "";
  const hash = [t === "overview" ? "" : `tab=${t}`, keep].filter(Boolean).join("&");
  history.replaceState(null, "", hash ? `#${hash}` : location.pathname + location.search);
  if (t === "overview") renderOverview();
  if (t === "how") renderHow();
  if (t === "evidence") renderEvidence();
  if (t === "money") renderMoney();
  if (t === "ops") renderOps();
  window.scrollTo(0, 0);
}

async function openRestaurant(rid) {
  // nothing on the old restaurant's screen stays clickable while the new one loads (a slow network
  // otherwise lets a click on the old screen be overwritten by the new restaurant's home)
  $("#screen").innerHTML = skeleton(5);
  await api("/api/v1/reset", {});
  Object.assign(S, { rid, offer: null, quote: null, err: "", original: null, alt: {}, whatIf: {} });
  S.card = await api(`/api/v1/restaurants/${rid}`);
  S.design = defaultDesign(S.card);
  $("#rest").value = rid;
  go("home");
  refreshInside();
}

function go(screen) { S.screen = screen; render(); }

function render() {
  const c = S.card;
  $("#phead").innerHTML = `<div class="row1"><h1>${esc(shownName(c))}</h1><span class="online">Online</span></div>
    <div class="sub">${esc(c.locality)} · ${esc(c.cuisines)} · <span class="rating">${c.rating} ★</span> · <span class="tag sim">simulated data</span></div>
    ${langOn() ? `<div class="langs" role="group" aria-label="Language">${Object.entries(CFG.i18n).map(([k, v]) => `<button class="chip ${LANG.code === k ? "on" : ""}" data-lang="${k}" aria-pressed="${LANG.code === k}">${esc(v._meta.language)}</button>`).join("")}
      ${LANG.code !== "en" ? `<span class="tag" title="${esc(CFG.i18n[LANG.code]._meta.status)}">draft translation</span>` : ""}</div>` : ""}`;
  document.querySelectorAll("#phead [data-lang]").forEach((b) => b.addEventListener("click", () => { LANG.code = b.dataset.lang; render(); }));
  const el = $("#screen");
  el.innerHTML = { home: homeHTML, create: createHTML, otp: otpHTML, live: liveHTML }[S.screen]();
  el.scrollTop = 0;
  bind();
}

// ---------------- phone screens ----------------
function homeHTML() {
  const c = S.card, off = S.offer;
  const st = off ? STATUS[off.status] : null;
  return `<div class="stats">
      <div class="stat"><div class="v">${n0(c.orders_per_week)}</div><div class="l">orders a week</div></div>
      <div class="stat"><div class="v">${inr(c.aov)}</div><div class="l">average order</div></div>
      <div class="stat"><div class="v">${pct(c.regulars_share_of_orders)}</div><div class="l">of orders from ${c.regular_customers} regulars</div></div>
    </div>
    ${off ? `<div class="card"><div class="eyebrow">Your offer</div><h4>${esc(off.label)}</h4>
      <span class="tag ${st[1]}">${st[0]}</span> <span class="note">${off.weeks.length} week${off.weeks.length === 1 ? "" : "s"} measured</span>
      <button class="btn small" data-go="live">See results</button></div>` : ""}
    <div class="card hero-card"><div class="eyebrow">New · TrueLift</div><h4>Discounts that pay for themselves</h4>
      <p class="note">Before you approve an offer, see how many <b>extra</b> orders and how much profit it will bring, not just how many orders will use it. While it runs, see what it really added.</p>
      <button class="btn" data-go="create">${off ? "Create another offer" : "Create an offer"}</button></div>
    <div class="card"><h4>How it works</h4>
      <div class="row"><span class="k">1. Forecast before you approve</span><span class="v">✓</span></div>
      <div class="row"><span class="k">2. Shown to customers it brings in</span><span class="v">✓</span></div>
      <div class="row"><span class="k">3. 1 in ${oneIn()} don't see it, so it's measured</span><span class="v">✓</span></div>
      <div class="row"><span class="k">4. Weekly result on WhatsApp</span><span class="v">✓</span></div></div>`;
}

function createHTML() {
  const d = S.design, o = designOptions(S.card);
  const chip = (field, val, label) => `<button class="chip ${d[field] === val ? "on" : ""}" data-set="${field}" data-val='${JSON.stringify(val)}'>${label}</button>`;
  const isPct = (d.pct || 0) > 0;
  const fmt = (val, label, on) => `<button class="chip ${on ? "on" : ""}" data-format="${val}" aria-pressed="${on}">${label}</button>`;
  const amounts = isPct
    ? o.pcts.map((p) => `<button class="chip ${d.discount === p.cap && d.pct === p.pct ? "on" : ""}" data-pct='${JSON.stringify(p)}'>${Math.round(p.pct * 100)}% off up to ₹${p.cap}</button>`).join("")
    : o.depths.map((v) => chip("discount", v, "₹" + v + " off")).join("");
  return `<button class="back" data-go="home">← Back</button>
  ${o.pcts.length ? `<div class="field"><span class="lab">Offer type</span><div class="chips" role="group" aria-label="Offer type">${fmt("flat", "Flat ₹ off", !isPct)}${fmt("pct", "% off up to ₹", isPct)}</div></div>` : ""}
  <div class="field"><span class="lab">Discount</span><div class="chips">${amounts}</div>${isPct ? `<p class="note">The percentage applies to small orders only: from ₹${Math.round(d.discount / d.pct)} up, every order gets ₹${d.discount} off.</p>` : ""}</div>
  <div class="field"><span class="lab">Minimum order</span><div class="chips">${chip("min_order", 0, "None")}${chip("min_order", o.mov, "Above ₹" + o.mov)}</div></div>
  <div class="field"><span class="lab">Who sees it</span><div class="chips">${AUDIENCES.map(([v, l]) => chip("audience", v, l)).join("")}</div></div>
  <div class="field"><span class="lab">When</span><div class="chips">${chip("offpeak_only", false, "All day")}${chip("offpeak_only", true, "3–6 pm only")}</div></div>
  <div class="field"><span class="lab">Reward regulars (Brand Pack)</span><div class="chips">${chip("reward", 0, "No")}${chip("reward", o.reward, "₹" + o.reward + " off per order for regulars")}</div></div>
  <div id="forecast">${S.quote && sameDesign(S.quote.owner.design, d) ? forecastHTML(S.quote) : `<div class="card empty">Calculating the forecast…</div>`}</div>
  <div class="sticky-cta">${d.discount > 0 ? `<button class="btn" data-act="toOtp">Continue to approve</button>` :
    `<p class="note">No discount to approve. Brand Pack rewards are set up in Zomato's Brand Packs screen.</p>`}</div>`;
}

const sameDesign = (a, b) => a && b && dkey(a) === dkey(b);

function rangeHTML(lo, hi, mid) {
  const a = Math.min(lo, hi, mid, 0), b = Math.max(lo, hi, mid, 0), pad = (b - a) * 0.08 || 1;
  const x = (v) => ((v - (a - pad)) / (b - a + 2 * pad)) * 100;
  return `<div class="range" aria-hidden="true"><div class="track"></div>
    <div class="bar" style="left:${x(lo)}%;width:${Math.max(x(hi) - x(lo), 1)}%"></div>
    <div class="zero" style="left:${x(0)}%"></div><div class="zl" style="left:${x(0)}%">₹0</div>
    <div class="mid" style="left:${x(mid)}%"></div></div>`;
}

// Forecasts are shown to two significant figures: "about ₹1,200", not "₹1,234", which would claim
// a precision the model does not have.
const sig2 = (v) => { if (!v) return 0; const k = Math.pow(10, Math.max(0, Math.floor(Math.log10(Math.abs(v))) - 1)); return Math.round(v / k) * k; };
const approx = (v, sign = true) => inr(sig2(v), sign);
const chanceWords = (p) => (p === undefined || p === null ? "" : p >= 0.9 ? "very likely" : p >= 0.7 ? "likely" : p >= 0.5 ? "slightly more likely than not" : p >= 0.3 ? "unlikely" : "very unlikely");

function forecastBlock(x) {
  const pp = x.prob_profit_positive;
  return `<div class="big ${cls(x.profit_change)}">about ${approx(x.profit_change)}<span class="note" style="font-weight:400"> extra profit a week</span></div>
    <div class="note">likely between ${approx(x.profit_low)} and ${approx(x.profit_high)}${pp === undefined ? "" : `; ${chanceWords(pp)} to make you money (${pct(pp)} chance)`}</div>
    ${rangeHTML(x.profit_low, x.profit_high, x.profit_change)}
    <div class="mini">
      <div><div class="v">${n0(x.redemptions)}</div><div class="l">orders would use it</div></div>
      <div><div class="v">${n0(x.extra_orders)}</div><div class="l">of them are extra orders</div></div>
      <div><div class="v">${x.anyway_share === null ? "–" : pct(x.anyway_share)}</div><div class="l">would come anyway</div></div>
    </div>
    <div class="row"><span class="k">Discount you give per extra order</span><span class="v">${x.discount_per_extra_order ? inr(x.discount_per_extra_order) : "–"}</span></div>
    <div class="row"><span class="k">Average order with the offer</span><span class="v">${inr(x.order_value_with_offer)}</span></div>
    <div class="row"><span class="k">Zomato's extra commission</span><span class="v">${inr(x.zomato_commission_change, true)}</span></div>
    ${x.detectable_effect_4w ? `<p class="note">In four weeks your own control group can confirm an effect of about ${approx(x.detectable_effect_4w, false)} a week or more; smaller effects rest more on the model learned from all restaurants.</p>` : ""}`;
}

function forecastHTML(q) {
  const o = q.owner, b = q.better;
  const why = o.redemptions > 0 && o.anyway_share !== null
    ? `${Math.round(o.anyway_share * 10)} in 10 orders using this offer would have come anyway, so that part of the discount buys nothing.`
    : "Forecast from customers who visited your menu in the last two weeks.";
  return `<div class="card ${o.profit_change < 0 ? "warn" : ""}" id="ownerCard"><div class="eyebrow">Forecast for your offer · one week</div>
      ${forecastBlock(o)}<p class="note">${why}</p></div>
    ${b ? `<div class="card better" id="betterCard"><div class="eyebrow">TrueLift suggests</div><h4>${esc(b.label)}</h4>
      <p class="note"><b class="pos">about ${approx(b.profit_change - o.profit_change)} more a week</b> than your version, same discount size. Best of ${q.designs_compared} versions compared, so the gain may be smaller in practice (<a href="#tab=evidence">how much smaller</a>). TrueLift picks the version that earns <i>you</i> the most; it does not weigh Zomato's commission.</p>
      ${forecastBlock(b)}<button class="btn small" data-act="useBetter">Use this version</button></div>`
      : `<div class="card"><p class="note">This is already the best of the ${q.designs_compared} versions compared (who sees it, minimum order, time, Brand Pack). The discount size is yours to choose.</p></div>`}`;
}

function evidenceHTML(ev) {
  return `<div class="card" id="evidenceCard"><div class="eyebrow">Renew on what was measured</div><h4>What this offer did in its ${ev.weeks} weeks</h4>
    <div class="row"><span class="k">Extra orders it created</span><span class="v">${n0(Math.max(ev.extra_orders, 0))} (likely ${n0(Math.max(ev.extra_orders_low, 0))}–${n0(Math.max(ev.extra_orders_high, 0))})</span></div>
    <div class="row"><span class="k">Extra profit</span><span class="v ${cls(ev.extra_profit)}">${inr(ev.extra_profit, true)}</span></div>
    <div class="row"><span class="k">Likely range</span><span class="v">${inr(ev.extra_profit_low, true)} to ${inr(ev.extra_profit_high, true)}</span></div>
    <div class="row"><span class="k">Chance it made you money</span><span class="v">${pct(ev.chance_making_money)}</span></div>
    <div class="row"><span class="k">Forecast when you approved it</span><span class="v">${inr(ev.forecast_at_approval, true)}</span></div>
    <p class="note">${esc(cap(ev.verdict))}. Measured with your own control group and the model learned from all restaurants, not a forecast. The same customers stay in the control group, so the measurement carries on.</p></div>`;
}

function otpHTML() {
  const off = S.offer, q = off.quote, ev = off.evidence;
  if (ev) {
    return `<button class="back" data-go="live">← Back</button>
  ${evidenceHTML(ev)}
  <div class="card"><div class="eyebrow">Renew this offer</div><h4>${esc(off.label)}</h4>
    <div class="row"><span class="k">Runs for</span><span class="v">${CFG.consent_weeks} more weeks, then needs a new OTP</span></div>
    <p class="note">${esc(off.who_pays)}</p>
    <p class="note">Your approval record will store the result above, so you can always see what you renewed on.</p></div>
  ${otpBoxesHTML("Renew with OTP")}`;
  }
  if (LANG.code !== "en" && T("approve_title")) {
    const share = off.design.zomato_share > 0 ? Math.round(off.design.zomato_share * 100) : 0;
    return `<button class="back" data-go="create">← Change offer</button>
  <div class="card" lang="${LANG.code}"><div class="eyebrow">${esc(T("approve_title"))}</div><h4>${esc(off.label_i18n?.[LANG.code] || off.label)}</h4>
    <div class="row"><span class="k">${esc(T("extra_orders"))}</span><span class="v">${n0(q.extra_orders)}</span></div>
    <div class="row"><span class="k">${esc(T("extra_profit"))}</span><span class="v ${cls(q.profit_change)}">${inr(q.profit_change, true)}</span></div>
    <div class="row"><span class="k">${esc(T("range"))}</span><span class="v">${inr(q.profit_low, true)} – ${inr(q.profit_high, true)}</span></div>
    <div class="row"><span class="k">${esc(T("runs_for"))}</span><span class="v">${esc(T("runs_weeks", { weeks: CFG.consent_weeks }))}</span></div>
    <p class="note">${esc(share ? T("who_pays_shared", { share }) : T("who_pays"))}</p>
    <p class="note">${esc(T("weekly"))}</p></div>
  ${otpBoxesHTML(T("button"), T("enter"))}`;
  }
  return `<button class="back" data-go="create">← Change offer</button>
  <div class="card"><div class="eyebrow">Approve this offer</div><h4>${esc(off.label)}</h4>
    <div class="row"><span class="k">Expected extra orders a week</span><span class="v">${n0(q.extra_orders)}</span></div>
    <div class="row"><span class="k">Expected extra profit a week</span><span class="v ${cls(q.profit_change)}">${inr(q.profit_change, true)}</span></div>
    <div class="row"><span class="k">Likely range</span><span class="v">${inr(q.profit_low, true)} to ${inr(q.profit_high, true)}</span></div>
    <div class="row"><span class="k">Runs for</span><span class="v">${CFG.consent_weeks} weeks, then needs a new OTP</span></div>
    <p class="note">${esc(off.who_pays)}</p>
    <p class="note">A weekly summary comes on WhatsApp. If the offer is clearly losing money it pauses by itself.</p></div>
  ${otpBoxesHTML("Approve with OTP")}`;
}

function otpBoxesHTML(label, prompt = "Enter the OTP sent to your registered phone") {
  return `<div class="card" id="otpCard"><div class="note" style="text-align:center">${esc(prompt)}</div>
    <div class="otp-boxes">${[0, 1, 2, 3].map((i) => `<input inputmode="numeric" maxlength="1" aria-label="OTP digit ${i + 1}" data-otp="${i}">`).join("")}</div>
    <div class="note" style="text-align:center">Demo OTP: <b>${esc(S.otp)}</b></div>
    <div id="otperr" class="neg note" style="text-align:center;min-height:18px">${esc(S.err)}</div>
    <button class="btn" data-act="approve">${label}</button></div>`;
}

function liveHTML() {
  const off = S.offer, st = STATUS[off.status];
  const w = off.weeks[off.weeks.length - 1];
  const canRun = off.status === "active";
  return `<button class="back" data-go="home">← Offers</button>
  <div class="card"><div class="eyebrow">Your offer</div><h4>${esc(off.label)}</h4>
    <span class="tag ${st[1]}">${st[0]}</span>
    <div class="row" style="margin-top:6px"><span class="k">Approved by OTP</span><span class="v">${esc(when(off.consent?.approved_at))}</span></div>
    <div class="row"><span class="k">Forecast at approval</span><span class="v">${inr(off.quote.profit_change, true)} a week</span></div></div>
  ${canRun ? `<button class="btn" id="runBtn" data-act="runWeek" ${S.busy ? "disabled" : ""}>${S.busy ? "Simulating…" : off.weeks.length ? `Simulate week ${off.weeks.length + 1}` : "Simulate the first week"}</button>
    <p class="note" style="text-align:center">${off.weeks.length ? `${CFG.consent_weeks - off.weeks.length} of ${CFG.consent_weeks} approved weeks left` : "Runs a week of simulated customers through the offer."}</p>` : ""}
  ${w ? weekHTML(w, off) : `<div class="card empty">No results yet. Simulate a week to see what the offer really adds.</div>`}
  ${off.weeks.length > 1 ? `<div class="card weeks-list"><h4>Week by week</h4>${off.weeks.map((x) => `<div class="wk"><span>Week ${x.week}</span>
     <span>${inr(x.measurement.profit.total, true)} so far</span><span class="tag ${verdictTag(x)}">${shortVerdict(x)}</span></div>`).join("")}</div>` : ""}
  ${off.renewal_of ? `<p class="note">Renewal of offer ${off.renewal_of}, approved on its measured result.${STATIC ? " In this static demo the renewed weeks replay the first period's simulated customers; the live service runs new weeks." : ""}</p>` : ""}
  ${off.status === "consent_expired" && !off.renewed_by ? `<button class="btn" data-act="renew">Renew for ${CFG.consent_weeks} weeks</button>` : ""}
  ${off.status !== "active" && off.weeks.length && S.alt[off.offer_id] ? `<div id="whatIf">${S.whatIf[off.offer_id] ? whatIfHTML(off, S.alt[off.offer_id], S.whatIf[off.offer_id]) : `<div class="card empty">Running the other version on the same customers…</div>`}</div>` : ""}
  ${off.status !== "active" && off.status !== "stopped" ? `<button class="btn ghost" data-go="create">Change and re-approve</button>` : ""}
  ${off.weeks.length && canRun ? `<button class="btn ghost" data-act="stop">Stop offer</button>` : ""}`;
}

// What if the owner had run the other version: their original one (when they took TrueLift's
// suggestion) or TrueLift's suggestion (when they kept theirs), on the same simulated customers
// for the same weeks (A09 D4). The static demo has both versions' weeks in its files; the live
// service runs the other version in a separate session so this visitor's offers are untouched.
async function whatIfWeeks(design, n) {
  if (!(design.discount > 0)) return [];
  if (STATIC) {
    const f = await sget(`${S.rid}/${dkey(design)}.json`);
    return f.offer ? f.offer.weeks.slice(0, n) : [];
  }
  const h = { "X-Session": `${SESSION}-whatif`, "Content-Type": "application/json" };
  const post = async (p, b) => {
    const r = await fetch(p, { method: "POST", headers: h, body: JSON.stringify(b || {}) });
    const j = await r.json().catch(() => ({}));
    if (!r.ok) throw new Error(typeof j.detail === "string" ? j.detail : `The service answered ${r.status}.`);
    return j;
  };
  const c = await post("/api/v1/offers", { restaurant_id: S.rid, design });
  let v = await post(`/api/v1/offers/${c.offer_id}/approve`, { otp: c.demo_otp });
  for (let w = 1; w <= n && v.status === "active"; w++) v = await post(`/api/v1/offers/${c.offer_id}/run_week?week=${w}`, {});
  return v.weeks;
}

async function loadWhatIf() {
  const off = S.offer, alt = off && S.alt[off.offer_id];
  if (!alt || off.status === "active" || !off.weeks.length || S.whatIf[off.offer_id]) return;
  try { S.whatIf[off.offer_id] = { weeks: await whatIfWeeks(alt.design, off.weeks.length) }; }
  catch (e) { S.whatIf[off.offer_id] = { error: e.message }; }
  if (S.screen === "live" && S.offer?.offer_id === off.offer_id) $("#whatIf").innerHTML = whatIfHTML(off, alt, S.whatIf[off.offer_id]);
}

function whatIfHTML(off, alt, r) {
  if (r.error) return `<div class="card"><p class="note">The comparison could not run: ${esc(r.error)}</p></div>`;
  const n = off.weeks.length, mine = off.weeks[n - 1];
  const other = r.weeks.length ? r.weeks[Math.min(n, r.weeks.length) - 1] : null;
  const row = (label, w, none) => `<tr><td>${esc(label)}</td><td>${w ? inr(w.measurement.profit.total, true) : none}</td><td>${w ? inr(w.simulator_truth.extra_profit, true) : none}</td></tr>`;
  const better = other ? other.simulator_truth.extra_profit - mine.simulator_truth.extra_profit : -mine.simulator_truth.extra_profit;
  return `<div class="card" id="whatIfCard"><div class="eyebrow">What if</div><h4>What if you had run ${esc(alt.name)}?</h4>
    <div class="tablewrap"><table class="t"><tr><th>Version, ${n} week${n === 1 ? "" : "s"}</th><th>Measured extra profit</th><th>True extra profit</th></tr>
      ${row(`What you ran: ${off.label}`, mine)}${row(`${cap(alt.name)}: ${alt.label}`, other, "₹0, no offer")}
      ${other && r.weeks.length < n ? `<tr><td colspan="3" class="note">The other version paused after ${r.weeks.length} week${r.weeks.length === 1 ? "" : "s"}.</td></tr>` : ""}</table></div>
    <p class="note">Same simulated customers, same weeks. ${better > 0 ? `${cap(alt.name)} would truly have made ${inr(better)} more.` : `What you ran truly made ${inr(-better)} more.`} The true figures are known only because this is a simulation; in real life the measured column is all anyone sees.</p></div>`;
}

const verdictTag = (w) => ({ keep: "good", pause: "bad", probably_losing: "warn" }[w.measurement.verdict_code] || "");
const shortVerdict = (w) => ({ keep: "Making money", pause: "Losing money", probably_losing: "Probably losing",
  check_failed: "Check failed" }[w.measurement.verdict_code] || "Too early");

// The Brand Pack reward has its own control group among regulars, so it gets its own line (TL-016)
function brandPackHTML(bp) {
  const p = bp.profit;
  const range = p ? `${inr(p.low, true)} to ${inr(p.high, true)} for you (best estimate ${inr(p.total, true)}). ` : "";
  return `<div class="note" id="brandPackLine"><b>Brand Pack reward, measured on its own:</b> ${range}${esc(bp.verdict)}
    ${n0(bp.control_visits)} visits by regulars were held out of the reward to measure it.</div>`;
}

function weekHTML(w, off) {
  const m = w.measurement, p = m.profit, o = m.orders, r = m.report_today, pay = w.payout;
  const n = w.week;
  const e = w.experiment || {};
  const rate = (o2, v) => (v ? (100 * o2 / v).toFixed(1) + "%" : "–");
  const today = new Date().toLocaleDateString("en-IN", { day: "numeric", month: "short" });
  return `<div class="card" id="weekCard"><div class="eyebrow">After ${n} week${n === 1 ? "" : "s"}</div>
    <span class="tag ${verdictTag(w)}">${cap(m.verdict)}</span> <span class="note">advice as of ${esc(today)}</span>
    <div class="mini" style="grid-template-columns:1fr 1fr">
      <div><div class="v">${n0(Math.max(o.total, 0))}</div><div class="l">extra orders the offer created so far (likely ${n0(Math.max(o.low, 0))}–${n0(Math.max(o.high, 0))})</div></div>
      <div><div class="v ${cls(p.total)}">${inr(p.total, true)}</div><div class="l">your extra profit so far</div></div>
    </div>
    <div class="note">Extra profit, likely between ${inr(p.low, true)} and ${inr(p.high, true)}</div>
    ${rangeHTML(p.low, p.high, p.total)}
    ${w.brand_pack ? brandPackHTML(w.brand_pack) : ""}
    <div class="card" style="background:var(--bg);box-shadow:none;margin:10px 0 4px;padding:10px 12px">
      <div class="note"><b>Today's offer report would show ${n0(r.orders_with_offer)} orders</b> using the offer (${inr(r.sales_from_offer)} of sales). TrueLift's measurement says about ${n0(Math.max(o.total, 0))} of them would not have happened without it.</div></div>
    <details id="howKnow"><summary>Show me how you know</summary>
      <p class="note">Customers who could get the offer were split at random: most saw it, about 1 in ${oneIn()} did not. The difference in how often each group ordered is what the offer added.</p>
      ${e.suppressed ? `<p class="note">One group has fewer than ${e.min_group_customers} customers so far (${n0(e.shown_customers)} saw the offer, ${n0(e.control_customers)} were held out), so its order counts stay hidden to protect them. The estimate above still uses every visit.</p>` : `
      <div class="row"><span class="k">Saw the offer</span><span class="v">${n0(e.shown_orders)} orders from ${n0(e.shown_visits)} visits (${rate(e.shown_orders, e.shown_visits)})</span></div>
      <div class="row"><span class="k">Held out (control group)</span><span class="v">${n0(e.control_orders)} orders from ${n0(e.control_visits)} visits (${rate(e.control_orders, e.control_visits)})</span></div>`}
      <p class="note">With few held-out visits the comparison is noisy, so the estimate also leans on the model learned from all restaurants (${pct(p.weight_on_own_data)} of the weight is on your own control group now).</p></details>
    ${(() => { const draft = LANG.code !== "en" && !!w.whatsapp_i18n?.[LANG.code];
      let wa = draft ? w.whatsapp_i18n[LANG.code] : w.whatsapp;
      if (LINK.generic && S.card) wa = wa.split(S.card.name).join(shownName(S.card)); // #names=generic: no real name anywhere
      return `<details><summary>WhatsApp summary sent to the owner${draft ? " (draft translation)" : ""}</summary><div class="wa" lang="${draft ? LANG.code : "en"}">${esc(wa)}</div>
      <a class="btn small ghost" href="https://wa.me/?text=${encodeURIComponent(wa)}" target="_blank" rel="noopener noreferrer">Send to my WhatsApp</a></details>`; })()}
    <details><summary>Itemised payout for week ${n}</summary>
      <div class="row"><span class="k">Orders</span><span class="v">${pay.orders}</span></div>
      <div class="row"><span class="k">Food sales</span><span class="v">${inr(pay.gross_sales)}</span></div>
      <div class="row"><span class="k">Discount paid by you</span><span class="v">−${inr(pay.discount_paid_by_you)}</span></div>
      <div class="row"><span class="k">Brand Pack rewards paid by you</span><span class="v">−${inr(pay.brand_pack_rewards_paid_by_you)}</span></div>
      <div class="row"><span class="k">Discount paid by Zomato</span><span class="v">${inr(pay.discount_paid_by_zomato)}</span></div>
      <div class="row"><span class="k">Commission (${pct(pay.commission_rate)})</span><span class="v">−${inr(pay.commission)}</span></div>
      <div class="row"><span class="k">GST on commission (${pct(pay.gst_rate)})</span><span class="v">−${inr(pay.gst_on_commission)}</span></div>
      <div class="row"><span class="k"><b>Net payout</b></span><span class="v">${inr(pay.net_payout)}</span></div></details></div>`;
}

// ---------------- actions ----------------
function bind() {
  document.querySelectorAll("#screen [data-go]").forEach((b) => b.addEventListener("click", () => { S.err = ""; go(b.dataset.go); }));
  document.querySelectorAll("#screen [data-set]").forEach((b) => b.addEventListener("click", () => {
    S.design = { ...S.design, [b.dataset.set]: JSON.parse(b.dataset.val) };
    render();
  }));
  document.querySelectorAll("#screen [data-format]").forEach((b) => b.addEventListener("click", () => {
    S.design = withFormat(S.design, S.card, b.dataset.format);
    render();
  }));
  document.querySelectorAll("#screen [data-pct]").forEach((b) => b.addEventListener("click", () => {
    const p = JSON.parse(b.dataset.pct);
    S.design = { ...S.design, discount: p.cap, pct: p.pct };
    render();
  }));
  document.querySelectorAll("#screen [data-act]").forEach((b) => b.addEventListener("click", () => ACT[b.dataset.act]()));
  const boxes = [...document.querySelectorAll("[data-otp]")];
  boxes.forEach((inp, i) => {
    inp.addEventListener("input", () => { inp.value = inp.value.replace(/\D/g, "").slice(-1); if (inp.value && boxes[i + 1]) boxes[i + 1].focus(); });
    inp.addEventListener("keydown", (e) => { if (e.key === "Backspace" && !inp.value && boxes[i - 1]) boxes[i - 1].focus(); if (e.key === "Enter") ACT.approve(); });
    inp.addEventListener("paste", (e) => { const t = (e.clipboardData.getData("text") || "").replace(/\D/g, ""); if (t.length >= 4) { e.preventDefault(); boxes.forEach((b, k) => (b.value = t[k] || "")); } });
  });
  if (boxes[0]) boxes[0].focus();
  if (S.screen === "create" && !(S.quote && sameDesign(S.quote.owner.design, S.design))) requestQuote();
}

let quoteSeq = 0;
function requestQuote() {
  const seq = ++quoteSeq;
  return api("/api/v1/quote", { restaurant_id: S.rid, design: S.design }).then((q) => {
    if (seq !== quoteSeq) return q;
    S.quote = q;
    if (S.screen === "create") {
      $("#forecast").innerHTML = forecastHTML(q);
      const ub = $('#forecast [data-act="useBetter"]');
      if (ub) ub.addEventListener("click", ACT.useBetter);
    }
    refreshInside();
    return q;
  }).catch((e) => { if (S.screen === "create") $("#forecast").innerHTML = `<div class="card neg">${esc(e.message)}</div>`; });
}

const ACT = {
  useBetter() {
    if (S.quote?.better) {
      S.original = { design: { ...S.quote.owner.design }, label: S.quote.owner.label };
      S.design = { ...S.quote.better.design }; S.quote = null; render();
    }
  },
  async toOtp() {
    const r = await api("/api/v1/offers", { restaurant_id: S.rid, design: S.design });
    S.otp = r.demo_otp; S.err = "";
    S.offer = await api(`/api/v1/offers/${r.offer_id}`);
    // the version to compare with once this offer ends (A09 D4)
    const q = S.quote && sameDesign(S.quote.owner.design, S.design) ? S.quote : null;
    if (S.original && !sameDesign(S.original.design, S.design)) S.alt[r.offer_id] = { name: "your original version", ...S.original };
    else if (q?.better && !sameDesign(q.better.design, S.design)) S.alt[r.offer_id] = { name: "TrueLift's suggestion", design: { ...q.better.design }, label: q.better.label };
    go("otp");
  },
  async renew() {
    const old = S.offer;
    const r = await api(`/api/v1/offers/${old.offer_id}/renew`, {});
    S.otp = r.demo_otp; S.err = "";
    if (S.alt[old.offer_id]) S.alt[r.offer_id] = S.alt[old.offer_id];
    S.offer = await api(`/api/v1/offers/${r.offer_id}`);
    go("otp");
  },
  async approve(code) {
    const otp = code ?? [...document.querySelectorAll("[data-otp]")].map((b) => b.value).join("");
    try {
      S.offer = await api(`/api/v1/offers/${S.offer.offer_id}/approve`, { otp });
      S.err = ""; go("live"); refreshInside();
    } catch (e) { S.err = e.message; const el = $("#otperr"); if (el) el.textContent = e.message; }
  },
  async runWeek() {
    if (S.busy) return;
    S.busy = true; render();
    try { S.offer = await api(`/api/v1/offers/${S.offer.offer_id}/run_week`, {}); }
    finally { S.busy = false; render(); refreshInside(); loadWhatIf(); }
  },
  async stop() { S.offer = await api(`/api/v1/offers/${S.offer.offer_id}/decision`, { action: "stop" }); render(); refreshInside(); loadWhatIf(); },
};

// ---------------- inside Zomato ----------------
async function refreshInside() {
  const design = S.offer?.design || S.design;
  try {
    const [c, q] = await Promise.all([
      api("/api/v1/customers", { restaurant_id: S.rid, design }),
      S.offer ? Promise.resolve({ owner: S.offer.quote }) : (S.quote && sameDesign(S.quote.owner.design, design) ? Promise.resolve(S.quote) : api("/api/v1/quote", { restaurant_id: S.rid, design })),
    ]);
    $("#who").innerHTML = whoHTML(c, q.owner);
  } catch (e) { $("#who").innerHTML = `<p class="neg">${esc(e.message)}</p>`; }
  renderTruth();
  try {
    const calls = await api("/api/v1/calls");
    $("#calls").innerHTML = (STATIC ? `<p class="note">Measured when this demo was built:</p>` : "") +
      (calls.calls.map((c) => `${esc(c.hook)} · ${c.ms} ms${c.customer !== undefined ? ` · customer ${c.customer} · ${c.show ? "show" : "don't show"}` : ""}`).join("<br>") || "No calls yet.");
  } catch (e) { /* optional panel */ }
}

function whoHTML(c, q) {
  const visits = q.menu_visits || 0, elig = q.eligible_visits || 0;
  const shown = Math.round(elig * (1 - CFG.holdout_share)), ctrl = elig - shown, none = Math.max(visits - elig, 0);
  const w = (v) => (visits ? Math.max((v / visits) * 100, v > 0 ? 3 : 0) : 0);
  const active = S.offer && S.offer.status === "active";
  return `<h2>${active ? "Who sees the discount" : "Who would see it"}</h2>
    <p class="lead">${esc(c.label)}. Each time a customer opens the menu, TrueLift decides in about 1.5 ms whether to show the discount.</p>
    <div class="note">About <b>${n0(visits)}</b> menu visits a week:</div>
    <div class="funnel" role="img" aria-label="${shown} see the discount, ${ctrl} control group, ${none} not offered">
      <div class="f-show" style="width:${w(shown)}%">${shown > visits * 0.12 ? n0(shown) : ""}</div>
      <div class="f-ctrl" style="width:${w(ctrl)}%"></div>
      <div class="f-no" style="width:${w(none)}%">${none > visits * 0.12 ? n0(none) : ""}</div></div>
    <div class="legend"><span><i style="background:var(--series)"></i>see the discount (${n0(shown)})</span>
      <span><i style="background:#6f9fd8"></i>control group: 1 in ${oneIn()} eligible, not shown (${n0(ctrl)})</span>
      <span><i style="background:var(--series-mute)"></i>not offered (${n0(none)})</span></div>
    <h3 style="margin-top:16px">Some of this restaurant's real visitors (synthetic people)</h3>
    <div class="cust-list">${c.customers.map(custHTML).join("")}</div>`;
}

function custHTML(c) {
  const d = c.decision;
  const tag = d.control_group ? `<span class="tag">control group</span>` : d.show_offer ? `<span class="tag good">sees the discount</span>` : `<span class="tag">no discount</span>`;
  const init = { regular: "R", "stopped ordering": "SO", "new to you": "N", "new to Zomato": "NZ" }[c.group] || "C";
  return `<div class="cust"><div class="avatar">${init}</div><div>
    <div class="g">${cap(c.group)} <span class="muted" style="font-weight:400">#${c.customer_id}</span></div>
    <div class="meta">${c.orders_here_4w} orders here in 4 weeks · ${pct(c.share_of_orders_with_discount)} of past orders used a discount</div>
    <div class="d">${tag}${d.brand_pack_reward ? `<span class="tag">₹${d.brand_pack_reward} Brand Pack</span>` : ""}</div>
    <div class="ch">Chance of ordering: <b>${pct(d.p_order_without)}</b> without → <b>${pct(d.p_order_with)}</b> with. ${esc(cap(d.reason))}.</div></div></div>`;
}

function renderTruth() {
  const off = S.offer, el = $("#truth");
  if (!off || !off.weeks.length) { el.hidden = true; el.innerHTML = ""; return; }
  el.hidden = false;
  const last = off.weeks[off.weeks.length - 1], p = last.measurement.profit, t = last.simulator_truth.extra_profit;
  const inside = t >= p.low && t <= p.high;
  el.innerHTML = `<h2>Estimate vs the true effect</h2>
    <p class="lead">Only possible in a simulation: we know what each offer really added. The blue band is TrueLift's 80% range for the extra profit so far; the dots are the truth.</p>
    <div class="chart" style="box-shadow:none;padding:0">${truthChart(off.weeks, Math.max(320, el.clientWidth - 40))}</div>
    <div class="legend"><span><i class="line" style="background:var(--series)"></i>TrueLift estimate</span><span><i style="background:var(--series-soft);border:1px solid rgba(42,120,214,.35)"></i>80% range</span><span><i style="background:#1c1c1c;border-radius:50%"></i>true effect</span></div>
    <p class="note" style="margin-top:8px">After ${last.week} week${last.week === 1 ? "" : "s"}: true extra profit ${inr(t, true)}, estimate ${inr(p.total, true)}; the truth is ${inside ? "<b>inside</b> the range" : "<b>outside</b> the range (by design this happens about 1 time in 5)"}. Weight on this restaurant's own control group: ${pct(p.weight_on_own_data)}; the rest comes from the model learned from all restaurants.</p>`;
  bindTips(el);
}

function truthChart(weeks, W = 520) {
  // drawn at the panel's real width so text stays at its true size
  const H = 220, L = 70, R = 16, T = 12, B = 28;
  const lo = weeks.map((w) => w.measurement.profit.low), hi = weeks.map((w) => w.measurement.profit.high);
  const est = weeks.map((w) => w.measurement.profit.total), tr = weeks.map((w) => w.simulator_truth.extra_profit);
  const ymin = Math.min(0, ...lo, ...tr), ymax = Math.max(0, ...hi, ...tr);
  const xs = [0, ...weeks.map((w) => w.week)], n = Math.max(4, weeks.length);
  const x = (k) => L + (k / n) * (W - L - R);
  const y = (v) => T + (1 - (v - ymin) / (ymax - ymin || 1)) * (H - T - B);
  const pts = (arr) => [[0, 0], ...arr.map((v, i) => [xs[i + 1], v])];
  const band = [...pts(hi).map(([k, v]) => `${x(k)},${y(v)}`), ...pts(lo).reverse().map(([k, v]) => `${x(k)},${y(v)}`)].join(" ");
  const line = pts(est).map(([k, v], i) => `${i ? "L" : "M"}${x(k)},${y(v)}`).join(" ");
  const ticks = [ymin, (ymin + ymax) / 2, ymax].map((v) => `<line x1="${L}" x2="${W - R}" y1="${y(v)}" y2="${y(v)}" stroke="#ececec"></line><text x="${L - 8}" y="${y(v) + 4}" text-anchor="end">${inr(v)}</text>`).join("");
  const xt = Array.from({ length: n + 1 }, (_, k) => `<text x="${x(k)}" y="${H - 8}" text-anchor="middle">${k ? "wk " + k : "start"}</text>`).join("");
  const dots = tr.map((v, i) => `<g data-tip="Week ${weeks[i].week}: truth ${inr(v, true)}, estimate ${inr(est[i], true)} (range ${inr(lo[i], true)} to ${inr(hi[i], true)})">
      <circle cx="${x(xs[i + 1])}" cy="${y(v)}" r="9" fill="transparent"></circle><circle cx="${x(xs[i + 1])}" cy="${y(v)}" r="4.5" fill="#1c1c1c" stroke="#fff" stroke-width="2"></circle></g>`).join("");
  return `<svg viewBox="0 0 ${W} ${H}" width="100%" role="img" aria-label="Estimate and true effect by week">
    ${ticks}${xt}<line x1="${L}" x2="${W - R}" y1="${y(0)}" y2="${y(0)}" stroke="#c3c2b7"></line>
    <polygon points="${band}" fill="rgba(42,120,214,0.14)"></polygon>
    <path d="${line}" fill="none" stroke="var(--series)" stroke-width="2" stroke-linejoin="round" stroke-linecap="round"></path>${dots}</svg>`;
}

// ---------------- guided demo ----------------
const wait = (ms) => new Promise((r) => setTimeout(r, ms));
function spot(sel) {
  document.querySelectorAll(".spot").forEach((e) => e.classList.remove("spot"));
  const el = sel && document.querySelector(sel);
  if (!el) return;
  el.classList.add("spot");
  // inside the phone: centre it; on the page: bring it to the top, clear of the guide card
  const inPhone = !!el.closest("#screen");
  el.style.scrollMarginTop = inPhone ? "0px" : "110px";
  el.scrollIntoView({ behavior: "smooth", block: inPhone ? "center" : "start" });
}

// The guided demo. Each step's action runs against the real (or static) service; Back and the
// number keys rebuild the state by replaying the steps from the start (the simulation is
// deterministic), and a token makes sure a step that finishes after Exit or Restart changes nothing.
const Tour = {
  i: -1, steps: [], ev: null, token: 0, busy: false,
  async start(to = 0) {
    const token = ++this.token;
    showTab("demo");
    $("#tour").classList.add("on");
    this.setBusy(true);
    await openRestaurant(S.rid);
    try { this.ev = await once("evidence", () => api("/api/v1/evidence")); } catch (e) { this.ev = null; }
    if (token !== this.token) return;
    this.steps = tourSteps();
    this.i = -1;
    while (this.i < to - 1) { if (!(await this.step(token, true))) return; }
    await this.step(token, false);
  },
  async step(token, quiet) {
    if (this.i >= this.steps.length - 1) { this.stop(); return false; }
    this.i += 1;
    const s = this.steps[this.i];
    this.setBusy(true);
    try { if (s.run) await s.run(); } catch (e) { console.warn(e); }
    if (token !== this.token) return false;
    if (!quiet) this.show(s);
    return true;
  },
  show(s) {
    $("#tourDots").innerHTML = this.steps.map((_, k) => `<i class="${k <= this.i ? "on" : ""}"></i>`).join("");
    $("#tourStep").textContent = `Step ${this.i + 1} of ${this.steps.length}`;
    $("#tourTitle").textContent = s.title;
    $("#tourText").innerHTML = s.text();
    this.setBusy(false);
    spot(s.spot);
    $("#tourNext").focus({ preventScroll: true });
  },
  setBusy(b) {
    this.busy = b;
    const next = $("#tourNext");
    next.disabled = b;
    next.textContent = b ? "…" : this.i === this.steps.length - 1 ? "Finish" : "Next";
    $("#tourPrev").disabled = b;
    $("#tourBack").disabled = b || this.i <= 0;
  },
  next() { if (!this.busy) this.step(this.token, false); },
  back() { if (!this.busy && this.i > 0) this.start(this.i - 1); },
  jump(n) { if (!this.busy) this.start(Math.max(0, Math.min(n, (this.steps.length || 10) - 1))); },
  restart() { if (!this.busy) this.start(0); },
  stop() { this.token += 1; $("#tour").classList.remove("on"); spot(null); this.i = -1; this.setBusy(false); },
};

function tourSteps() {
  const c = S.card;
  const q = () => S.quote?.owner, b = () => S.quote?.better;
  const lastWeek = () => S.offer?.weeks[S.offer.weeks.length - 1];
  return [
    { title: `Meet ${shownName(c)}, ${c.locality}`, spot: "#phead",
      text: () => `This is the restaurant's partner app. It gets about <b>${n0(c.orders_per_week)} orders a week</b> at <b>${inr(c.aov)}</b> on average, and ${pct(c.regulars_share_of_orders)} of orders come from ${c.regular_customers} regulars. (Real listing; simulated customers and money.)` },
    { title: "The owner sets up today's usual offer", spot: "#ownerCard",
      run: async () => { S.design = defaultDesign(c); S.quote = null; go("create"); await requestQuote(); await wait(150); },
      text: () => q() ? `<b>${esc(q().label)}</b>. Before approving, TrueLift forecasts it: about ${n0(q().redemptions)} orders a week would use it, but <b>${pct(q().anyway_share)} of them would have come anyway</b>. Expected extra profit: <b>${inr(q().profit_change, true)}</b> a week (likely ${inr(q().profit_low, true)} to ${inr(q().profit_high, true)}). Today's report would only show the orders that used it.` : "Calculating…" },
    { title: "TrueLift suggests a better version", spot: "#betterCard",
      run: async () => { await wait(50); },
      text: () => b() ? `It compared ${S.quote.designs_compared} versions of the same discount and suggests <b>${esc(b().label)}</b>: about <b>${inr(b().profit_change, true)} a week</b>, ${inr(b().profit_change - q().profit_change, true)} more than the owner's version, because the discount goes to customers it actually brings in.` : "The owner's offer is already the best version here, so TrueLift keeps it." },
    { title: "Inside Zomato: who sees the discount", spot: "#who",
      run: async () => { if (S.quote?.better) { S.design = { ...S.quote.better.design }; S.quote = null; render(); await requestQuote(); } await wait(300); },
      text: () => q() ? `With the better version, about <b>${n0(q().eligible_visits * (1 - CFG.holdout_share))}</b> of ${n0(q().menu_visits)} weekly menu visits see the discount. Regulars who'd order anyway don't get it. <b>1 in ${oneIn()}</b> eligible customers are held back as a control group: comparing them with the rest is how TrueLift measures what the offer really added.` : "" },
    { title: "The owner approves with an OTP", spot: "#otpCard",
      run: async () => { await ACT.toOtp(); await wait(100); },
      text: () => `Since August 2026, restaurant-funded offers start only after the owner's OTP. TrueLift stores exactly what the owner was shown (the forecast, who pays, and the ${CFG.consent_weeks}-week approval period), so every deduction can be checked later.` },
    { title: "The offer is live", spot: "#runBtn",
      run: async () => { await ACT.approve(S.otp); await wait(100); },
      text: () => `Approved. Now we run simulated weeks of customers through the offer, the way real orders would arrive.` },
    { title: "Week 1: what the offer really added", spot: "#weekCard",
      run: async () => { await ACT.runWeek(); await wait(150); },
      text: () => { const w = lastWeek(); if (!w) return ""; const m = w.measurement;
        return `Today's report would show <b>${n0(m.report_today.orders_with_offer)} orders used the offer</b>. TrueLift measures that about <b>${n0(Math.max(m.orders.total, 0))}</b> of them were extra, worth <b>${inr(m.profit.total, true)}</b> so far (likely ${inr(m.profit.low, true)} to ${inr(m.profit.high, true)}). In week 1 the estimate leans on the model learned from all restaurants.`; } },
    { title: "Four weeks later", spot: "#truth",
      run: async () => { while (S.offer.status === "active") { await ACT.runWeek(); await wait(80); } },
      text: () => { const w = lastWeek(); if (!w) return ""; const p = w.measurement.profit, t = w.simulator_truth.extra_profit; const inside = t >= p.low && t <= p.high;
        return `After ${w.week} weeks: <b>${inr(p.total, true)}</b> extra profit (likely ${inr(p.low, true)} to ${inr(p.high, true)}). The owner got this on WhatsApp each week with keep / change / stop. Because this is a simulation we know the truth: <b>${inr(t, true)}</b>, ${inside ? "inside the range" : "outside the range this time (by design, about 1 time in 5)"}. The approval period is over, so renewing needs a fresh OTP.`; } },
    { title: "Across 300 restaurants", spot: "#evTiles",
      run: async () => { showTab("evidence"); await wait(400); },
      text: () => { const P = Tour.ev?.main?.policies; if (!P) return "See the Evidence tab."; const t = P.truelift, bl = P.today_blanket;
        const v = realTop30(Tour.ev.real_data_criteo, "visit", "t_learner");
        const less = 1 - t.customer_savings / bl.customer_savings, dz = t.zomato_commission_change - bl.zomato_commission_change;
        return `In the simulated market, <b>${t.offers_that_pay} of ${t.restaurants_with_offer}</b> TrueLift offers pay for themselves, against ${bl.offers_that_pay} of ${bl.restaurants_with_offer} blanket ones. Restaurants make ${lakh(t.restaurant_profit_change)} instead of ${lakh(bl.restaurant_profit_change)} extra profit a week with ${pct(less)} less discount, and Zomato's commission changes by ${inr(dz, true)} a week.${v ? ` On real randomised data (Criteo), the model's top 30% picks hold <b>${pct(v.value)}</b> of all the extra visits.` : ""}`; } },
    { title: "Try it yourself", spot: null,
      run: async () => { showTab("demo"); go("home"); },
      text: () => `Pick any restaurant at the top, create any offer, and run the weeks. <b>How it works</b> explains every step in plain words; <b>Money maths</b> shows every rupee.` },
  ];
}

// ---------------- how it works ----------------
// ---------------- overview ----------------
// The first page: what TrueLift is for, the problem, the solution, what it achieves and how we know,
// in plain words. Every number comes from the evidence the other tabs use.
const REPO = "https://github.com/YashG1836/truelift";
async function renderOverview() {
  const el = $("#overview");
  if (el.dataset.done) return;
  el.innerHTML = skeleton(5);
  let E = null;
  try { E = await once("evidence", () => api("/api/v1/evidence")); } catch (e) { /* the words still work without numbers */ }
  const P = E?.main?.policies, A = E?.main?.measurement?.after_4_weeks;
  const tl = P?.truelift, bl = P?.today_blanket, rule = P?.rule_new_customers;
  const waffle = Array.from({ length: 100 }, (_, k) => `<i class="${k >= 70 ? "x" : ""}"></i>`).join("");
  const results = P ? `
  <div class="ov-results">
    <div class="tile"><div class="v">${tl.offers_that_pay} of ${tl.restaurants_with_offer}</div><div class="l">TrueLift offers pay for themselves, against <b>${bl.offers_that_pay} of ${bl.restaurants_with_offer}</b> offers that give everyone the same discount</div></div>
    <div class="tile"><div class="v">+${lakh(tl.restaurant_profit_change)}</div><div class="l">extra restaurant profit a week, against +${lakh(bl.restaurant_profit_change)} with blanket offers and +${lakh(rule.restaurant_profit_change)} with "new customers only"</div></div>
    <div class="tile"><div class="v">${lakh(bl.customer_savings - tl.customer_savings)}</div><div class="l">less discount given a week than blanket offers, for more profit</div></div>
    <div class="tile"><div class="v">+${lakh(tl.zomato_commission_change)}</div><div class="l">extra Zomato commission a week, against +${lakh(bl.zomato_commission_change)} with blanket offers: good offers keep being approved</div></div>
  </div>
  <p class="note">A simulated market of 300 real Bengaluru listings, per week. ${A ? `After four weeks the true effect of an offer falls inside TrueLift's 80% range ${pct(A.coverage_80)} of the time. ` : ""}Details on the <a href="#tab=evidence">Evidence</a> tab.</p>` : "";
  el.innerHTML = `
  <div class="ov-hero">
    <div>
      <h1>Restaurant discounts, judged by the orders they <em>create</em></h1>
      <p class="lead">TrueLift tells a restaurant owner, before they approve an offer on Zomato, how many <b>extra</b> orders and how much <b>extra</b> profit it will bring. While the offer runs it shows the discount only to customers it brings in, and every week it reports what the offer really added.</p>
      <div class="ov-cta">
        <button class="btn small" data-ov="tour">▶ Start the guided demo</button>
        <button class="btn small ghost" data-ov="demo">Try it yourself</button>
        <a class="btn small ghost" href="${REPO}/blob/main/submission/TrueLift_Report.pdf" target="_blank" rel="noopener">Read the report</a>
      </div>
      <p class="note">A prototype for Zomato's restaurant partner app, by Team Banana (IIT Gandhinagar) for the IITGN × Eternal hackathon. Restaurant names and listings are real public 2019 data; every customer, order and rupee is simulated.</p>
    </div>
  </div>

  <h2>The problem</h2>
  <div class="split"><div><div class="waffle" role="img" aria-label="100 orders: 70 would have come anyway, 30 extra">${waffle}</div>
      <div class="legend"><span><i style="background:var(--series-mute)"></i>70 orders that would have come anyway</span><span><i style="background:var(--series)"></i>30 extra orders</span></div></div>
    <div>
      <p class="p">Restaurants pay for most discounts on Zomato. Today an offer is judged by the orders that <b>use</b> it. Take ₹60 off ₹400 orders: 100 orders used it, but 70 came from regulars who would have ordered anyway at full price. The restaurant gave away ₹4,200 for nothing and ends the week <b>₹210 worse off</b>.</p>
      <p class="p">₹60 off pays for itself only if at least <b>32 of every 100</b> orders using it are truly extra. No offer report shows that number, because it needs to know what would have happened without the offer.</p>
    </div></div>

  <h2>Why it matters now</h2>
  <div class="ov-why">
    <div class="tile"><div class="v">OTP</div><div class="l">Since August 2026 a restaurant-funded offer starts only after the owner approves it with an OTP. An owner who cannot see whether offers pay will stop approving them.</div></div>
    <div class="tile"><div class="v">${bl ? `${bl.offers_that_lose} of ${bl.restaurants_with_offer}` : "Most"}</div><div class="l">blanket offers lose their restaurant money in our simulated market, and no report tells the owner which ones.</div></div>
    <div class="tile"><div class="v">₹1,138 Cr</div><div class="l">Eternal's advertising and promotion spend in Q2 FY27, up 41% in a year, while food delivery earns 5.5% of order value.</div></div>
  </div>

  <h2>The solution: four steps inside Zomato's existing offer flow</h2>
  <div class="steps4">
    <div class="step4"><div class="n">1</div><h4>Forecast before the OTP</h4><p>Extra orders and profit with a likely range, and a better version of the same discount: who sees it, minimum order, time of day. The owner keeps the discount size.</p></div>
    <div class="step4"><div class="n">2</div><h4>Show it to the right customers</h4><p>When a customer opens the menu, the discount appears only if it is likely to bring them in. A random 1 in ${oneIn()} eligible customers is held out as a control group.</p></div>
    <div class="step4"><div class="n">3</div><h4>Fair payout</h4><p>The restaurant pays for its own offer, itemised. Zomato co-funds only where its own measurement shows a gain.</p></div>
    <div class="step4"><div class="n">4</div><h4>Measure every week</h4><p>Shown customers against the control group: what the offer really added, with a range and a verdict (keep, change or stop) on WhatsApp.</p></div>
  </div>
  <p class="note">No new screens: the forecast sits on the OTP screen, the result arrives on WhatsApp, and nothing changes in how customers order. Full detail on the <a href="#tab=how">How it works</a> tab.</p>

  <h2>Who gains</h2>
  <div class="ov-why">
    <div class="tile"><div class="v ov-s">Restaurant owners</div><div class="l">Know before approving whether an offer pays, spend discount money only where it brings orders, and see the proof every week.</div></div>
    <div class="tile"><div class="v ov-s">Zomato</div><div class="l">Owners keep approving offers that work, so orders and commission grow; Zomato's own discount money can be measured the same way.</div></div>
    <div class="tile"><div class="v ov-s">Customers</div><div class="l">Discounts go to people they change the decision for. Nobody pays more than the menu price, and targeting uses order history only.</div></div>
  </div>

  ${results ? `<h2>What it achieves</h2>${results}` : ""}

  <h2>How we know it works</h2>
  <div class="gloss">
    <div><b>A market where the truth is known</b>A simulator of 300 real listings and 30,000 synthetic customers knows each customer's true response to every discount, so every forecast and weekly result is checked against the truth.</div>
    <div><b>Strong baselines</b>TrueLift is compared with today's same-discount-for-everyone offers and with the sensible "new customers only" rule, across five market seeds and eight varied assumptions.</div>
    <div><b>Real randomised data</b>The targeting method was also tested on Criteo's advertising and Hillstrom's e-mail experiments. It wins on some outcomes and not on others, and the Evidence tab says which.</div>
    <div><b>Honest limits</b>All outcomes here are simulated; real numbers need Zomato's data. The first step inside Zomato is a silent holdout on offers owners already run.</div>
  </div>

  <h2>What is on this site</h2>
  <div class="ov-map">
    <button data-ov="demo"><b>Demo</b>The partner app: create an offer, approve it with the OTP, run the weeks. Press ▶ Guided demo for the ten-step story.</button>
    <button data-ov="how"><b>How it works</b>The four steps, how TrueLift knows, the words used, common questions.</button>
    <button data-ov="evidence"><b>Evidence</b>Every result against the truth, the checks that could fail, and the real-data tests.</button>
    <button data-ov="money"><b>Money maths</b>Every rupee of one order and the break-even of a discount.</button>
    <button data-ov="ops"><b>Operations</b>Guardrails and drift checks for running it at Zomato's scale.</button>
  </div>
  <p class="note" style="margin-top:18px">Code, report, slides and video: <a href="${REPO}" target="_blank" rel="noopener">github.com/YashG1836/truelift</a> · <a href="${REPO}/tree/main/submission" target="_blank" rel="noopener">submission folder</a>.</p>`;
  el.querySelectorAll("[data-ov]").forEach((b) => b.addEventListener("click", () => {
    const t = b.dataset.ov;
    if (t === "tour") Tour.start(); else showTab(t);
  }));
  el.dataset.done = "1";
}

async function renderHow() {
  const el = $("#how");
  if (el.dataset.done) return;
  let E = null;
  try { E = await once("evidence", () => api("/api/v1/evidence")); } catch (e) { /* page still works without numbers */ }
  const P = E?.main?.policies, v = realTop30(E?.real_data_criteo, "visit", "t_learner");
  const L = E?.latency, F = E?.main?.fairness;
  const serveMs = L ? `${L.serve_sequential.server_side.p50_ms} ms` : "about a millisecond";
  const quoteMs = L ? `${Math.round(L.quote_sequential.p50_ms)} ms` : "a fraction of a second";
  const waffle = Array.from({ length: 100 }, (_, k) => `<i class="${k >= 70 ? "x" : ""}"></i>`).join("");
  el.innerHTML = `<h1>How TrueLift works</h1>
  <p>Restaurant discounts on Zomato are judged by the orders that <b>use</b> them, not the orders they <b>create</b>. Since August 2026 a restaurant-funded offer starts only after the owner approves it with an OTP, so an owner who can't see whether an offer pays will stop approving it. TrueLift shows them, before and after.</p>
  <h2>The problem in one picture</h2>
  <div class="split"><div><div class="waffle" role="img" aria-label="100 orders: 70 would have come anyway, 30 extra">${waffle}</div>
      <div class="legend"><span><i style="background:var(--series-mute)"></i>70 orders that would have come anyway</span><span><i style="background:var(--series)"></i>30 extra orders</span></div></div>
    <div><p class="p">A ₹60-off offer on ₹400 orders: <b>100 orders used it</b>. The report shows 100. But 70 would have come anyway at full price, so the restaurant gave away ₹4,200 for nothing and ends the week <b>₹210 worse off</b>.</p>
      <p class="p">₹60 off pays for itself only if at least <b>32 of every 100</b> orders using it are truly extra. Nobody measures that today. TrueLift does.</p></div></div>
  <h2>Four steps inside Zomato's existing offer flow</h2>
  <div class="steps4">
    <div class="step4"><div class="n">1</div><h4>Before approval</h4><p>Forecast the extra orders and profit, with a range, and suggest a better version of the same discount.</p><div class="where">Offer screen and OTP · <code>POST /api/v1/quote</code></div></div>
    <div class="step4"><div class="n">2</div><h4>While it runs</h4><p>Show the discount only to customers it brings in. A random 1 in ${oneIn()} eligible customers don't see it: the control group.</p><div class="where">Menu page · <code>GET /api/v1/serve</code> · ${serveMs}</div></div>
    <div class="step4"><div class="n">3</div><h4>Who pays</h4><p>The restaurant pays for its own offer, itemised in the payout. Zomato co-funds only where its own measurement shows a gain.</p><div class="where">Payout statement</div></div>
    <div class="step4"><div class="n">4</div><h4>Every week</h4><p>Measured extra orders and profit, keep / change / stop on WhatsApp. Clear losers pause; renewal needs a new OTP.</p><div class="where">Partner app and WhatsApp · <code>GET /api/v1/offers/{id}</code></div></div>
  </div>
  <h2>How it knows</h2>
  <div class="steps4" style="grid-template-columns:repeat(3,1fr)">
    <div class="step4"><h4>A control group</h4><p>Customers who were eligible but randomly not shown the offer show what would have happened without it. The difference is what the offer added.</p></div>
    <div class="step4"><h4>A model learned from all restaurants</h4><p>For each visitor it predicts the chance of ordering with and without the discount. That decides who sees it and gives the forecast.</p></div>
    <div class="step4"><h4>Both, combined</h4><p>A small restaurant's control group is too small to rely on alone, so the estimate weights the model and the restaurant's own control group by how noisy each is, re-checked every week across all running offers, and always shows a range.</p></div>
  </div>
  <h2>Built for Zomato's scale</h2>
  <div class="scale">
    <div class="tile"><div class="v">3.34 lakh</div><div class="l">active restaurant partners it would serve (Q2 FY27)</div></div>
    <div class="tile"><div class="v">${serveMs}</div><div class="l">median time the service takes per serving decision${L ? " (measured)" : ""}; falls back to the owner's own rule if anything fails</div></div>
    <div class="tile"><div class="v">${quoteMs}</div><div class="l">median time per forecast over HTTP, comparing about 34 versions of an offer</div></div>
    <div class="tile"><div class="v">Weekly</div><div class="l">batch measurement per offer; no change to how customers order</div></div>
  </div>
  ${P ? `<h2>Does it work?</h2><p>In a simulated market of 300 real Bengaluru listings, <b>${P.truelift.offers_that_pay} of ${P.truelift.restaurants_with_offer}</b> TrueLift offers pay for themselves against <b>${P.today_blanket.offers_that_pay} of ${P.today_blanket.restaurants_with_offer}</b> blanket offers, and restaurants make ${lakh(P.truelift.restaurant_profit_change)} vs ${lakh(P.today_blanket.restaurant_profit_change)} extra profit a week.${v ? ` On real randomised data (Criteo's ad holdouts), the model's top 30% picks hold ${pct(v.value)} of all the extra visits.` : ""} Details on the Evidence tab.</p>` : ""}
  <h2>Words used on this site</h2>
  <div class="gloss">
    <div><b>Extra orders</b>Orders that happened only because of the offer.</div>
    <div><b>Would come anyway</b>Orders that used the discount but would have been placed at full price too.</div>
    <div><b>Control group</b>A random 1 in ${oneIn()} eligible customers who don't see the offer; they pay normal prices.</div>
    <div><b>Likely range</b>An 80% range: the true value should fall inside about 4 times in 5.</div>
    <div><b>Uplift</b>How much the offer raises one customer's chance of ordering.</div>
    <div><b>Brand Pack</b>Zomato's existing reward for a restaurant's repeat customers.</div>
    <div><b>Minimum order</b>The offer applies only above a bill size, e.g. ₹60 off above ₹499.</div>
    <div><b>Qini score</b>How well a ranking finds the people an offer moves; 0 means no better than random.</div>
  </div>
  <h2>Questions people ask</h2>
  <div class="faq">
    <details><summary>Isn't this just discount targeting? Swiggy and Zomato already have segments.</summary><p>Segments decide who <i>can</i> see an offer. Nobody measures what it <i>caused</i>. In our test the simple "new customers only" segment is a strong baseline, and TrueLift is compared against it, not just against blanket offers.</p></details>
    <details><summary>Doesn't hiding the offer from 1 in ${oneIn()} customers lose sales?</summary><p>Held-out customers pay normal menu prices; they are customers who would otherwise have received a discount. The holdout costs no discount money, but it does give up the extra orders the offer would have brought from those customers${E?.main?.zomato_ledger ? ` (about ${inr(E.main.zomato_ledger.control_group_cost_truelift.profit_forgone_a_week)} of restaurant profit a week across the 300 simulated restaurants)` : ""}. That is the price of knowing what each offer adds; without it no one can tell a paying offer from a losing one.</p></details>
    <details><summary>Can a small restaurant really be measured?</summary><p>Not from its own control group in one week. That's why the estimate starts from the model learned from all restaurants and moves to the restaurant's own data over time, always shown as a range.</p></details>
    <details><summary>Is it fair to give different customers different discounts?</summary><p>Only order history is used: orders here, orders on Zomato, weeks since the last order. Never location, device, payment method or anything that proxies wealth; the tests check the model's inputs against an allow-list. Nobody pays more than the menu price. Targeting does offer a restaurant's regulars fewer discounts, because they order anyway${F?.truelift ? ` (${(F.truelift.loyalty_gap * 100).toFixed(0)} points less often than other customers in the simulation)` : ""}; adding the Brand Pack reward for regulars closes that gap${F?.mitigations?.brand_pack_for_regulars ? ` at ${signed(F.mitigations.brand_pack_for_regulars.own_offer_profit_change_vs_truelift)} a week to restaurants' own-offer profit` : ""}. The Evidence tab has the numbers.</p></details>
    <details><summary>Why trust a simulation?</summary><p>Because it knows the truth, it is the only way to check the whole method end to end. The results hold when customers are 30% more or less price-sensitive, and the targeting was also checked on real randomised data. The next step is a silent test on Zomato's own offer logs.</p></details>
  </div>`;
  el.dataset.done = "1";
}

// Grey placeholder blocks while data loads, so the layout does not jump.
const skeleton = (n) => `<div aria-busy="true" aria-label="Loading">${Array.from({ length: n }, (_, i) => `<div class="skel" style="width:${[92, 70, 84, 60, 76][i % 5]}%"></div>`).join("")}</div>`;

// First visit: point at the guided demo once, then never again (remembered in this browser only).
function firstVisitHint() {
  let seen = true;
  try { seen = !!localStorage.getItem("truelift-seen"); localStorage.setItem("truelift-seen", "1"); } catch (e) { /* private mode */ }
  if (seen || $("#hint")) return;
  const tip = document.createElement("div");
  tip.id = "hint";
  tip.className = "hint";
  tip.setAttribute("role", "status");
  tip.innerHTML = `New here? <b>▶ Guided demo</b> walks through one restaurant in 10 steps. <button class="hint-x" aria-label="Close">×</button>`;
  $(".pick").appendChild(tip);
  tip.querySelector("button").addEventListener("click", () => tip.remove());
  $("#tourBtn").addEventListener("click", () => tip.remove(), { once: true });
}

// A failed load shows what went wrong and a way to try again, never a blank or broken page.
function errorCard(e, what = "this page") {
  return `<div class="card warn" role="alert"><h4>Couldn't load ${esc(what)}</h4><p class="note">${esc(e?.message || e)}</p>
    <button class="btn small" data-reload="1">Try again</button></div>`;
}
document.addEventListener("click", (ev) => { if (ev.target.closest?.("[data-reload]")) location.reload(); });

// ---------------- evidence ----------------
const POLICY_NAMES = { no_offer: "No offer", today_blanket: "Today: same discount for everyone", rule_new_customers: "Rule: new customers only",
  truelift: "TrueLift", measure_only: "Today's offers, measured (losers stop at renewal)", zomato_cofund_naive: "Unmeasured Zomato co-funding" };
const signed = (v) => inr(v, true);
const num = (v, d = 0) => (v === null || v === undefined || Number.isNaN(v) ? "–" : Number(v).toLocaleString("en-IN", { maximumFractionDigits: d, minimumFractionDigits: d }));
const tableHTML = (head, rows, cap = "") => `<div class="tablewrap"><table class="t">${cap ? `<caption>${cap}</caption>` : ""}<tr>${head.map((h) => `<th>${h}</th>`).join("")}</tr>${rows.join("")}</table></div>`;
const tr = (cells, hl = false) => `<tr class="${hl ? "hl" : ""}">${cells.map((c) => `<td>${c}</td>`).join("")}</tr>`;

async function renderEvidence() {
  const el = $("#evidence");
  if (el.dataset.done) return;
  let E;
  try { E = await once("evidence", () => api("/api/v1/evidence")); } catch (e) { el.innerHTML = errorCard(e, "the evidence"); return; }
  const M = E.main, P = M.policies, A = M.measurement;
  const keys = ["today_blanket", "rule_new_customers", "truelift", "measure_only", "zomato_cofund_naive"].filter((k) => P[k]);
  const main3 = ["today_blanket", "rule_new_customers", "truelift"];
  const row = (label, f, fmt = (v) => v, hl = false) => tr([label, ...keys.map((k) => fmt(f(P[k])))], hl);
  const tl = P.truelift, bl = P.today_blanket, a2 = A.after_2_weeks || {}, a4 = A.after_4_weeks || {};
  const keepRight = a2.verdicts && a2.verdicts.keep ? a2.said_keep_and_truly_positive / a2.verdicts.keep : null;
  el.innerHTML = `<h1>Does it work?</h1>
  <p>A simulated market of 300 real Bengaluru restaurants (public 2019 Zomato listings) and 30,000 synthetic customers whose true response to every discount is known. The models see only order history, as Zomato would. Each policy runs for four weeks on the same customer visits. Rupee figures are per week across the 300 restaurants. All outcomes are simulated.</p>
  <div class="tiles" id="evTiles">
    <div class="tile"><div class="v">${bl.offers_that_lose} of ${bl.restaurants_with_offer}</div><div class="l">blanket offers lose the restaurant money</div></div>
    <div class="tile"><div class="v">${tl.offers_that_pay} of ${tl.restaurants_with_offer}</div><div class="l">TrueLift offers pay for themselves</div></div>
    <div class="tile"><div class="v">${lakh(bl.customer_savings)} → ${lakh(tl.customer_savings)}</div><div class="l">discount given a week, with ${lakh(tl.restaurant_profit_change)} instead of ${lakh(bl.restaurant_profit_change)} extra restaurant profit</div></div>
    <div class="tile"><div class="v">${keepRight === null ? "–" : pct(keepRight)}</div><div class="l">of TrueLift's "keep" verdicts were right after two weeks</div></div>
  </div>
  <div class="charts">
    <div class="chart"><h3>Profit the offers create for their own restaurants</h3><div class="s">₹ a week, all 300 restaurants; each offer against not running it</div>${hbar(main3.map((k) => [POLICY_NAMES[k], P[k].own_offer_profit_effect, k === "truelift"]), inr)}</div>
    <div class="chart"><h3>Zomato's extra commission</h3><div class="s">₹ a week against a market with no offers (gross commission, before delivery costs)</div>${hbar(main3.map((k) => [POLICY_NAMES[k], P[k].zomato_commission_change, k === "truelift"]), inr)}</div>
  </div>
  <h2>Policy comparison (true expected values)</h2>
  ${tableHTML(["", ...keys.map((k) => POLICY_NAMES[k])], [
    row("Offers that pay for themselves", (p) => p.offers_that_pay, (v) => v, true),
    row("Offers that lose money", (p) => p.offers_that_lose),
    row("Profit created by own offers (₹ a week)", (p) => p.own_offer_profit_effect, signed, true),
    row("Orders using a discount", (p) => p.redemptions, n0),
    row("Share that would have come anyway", (p) => p.anyway_share_of_redemptions, pct),
    row("Extra orders against no offers", (p) => p.extra_orders_vs_no_offer, n0),
    row("Extra orders new to the platform (not taken from other Zomato restaurants)", (p) => p.platform_extra_orders, n0),
    row("Discount given to customers (₹ a week)", (p) => p.customer_savings, inr),
    row("Discount per extra order", (p) => p.savings_per_extra_order, inr),
    row("Restaurant profit against no offers (₹ a week)", (p) => p.restaurant_profit_change, signed, true),
    row("Restaurants better off / worse off than with no offers", (p) => `${p.restaurants_better_off_vs_no_offers} / ${p.restaurants_worse_off_vs_no_offers}`),
    row("Zomato commission against no offers", (p) => p.zomato_commission_change, signed),
    row("Zomato contribution against no offers (8.5% of bill minus Zomato-paid discount)", (p) => p.zomato_contribution_change, signed),
    row("Discount paid by Zomato", (p) => p.zomato_funded_discount, inr),
    row("Loyal customers' visits going to Swiggy", (p) => p.swiggy_share_loyal, (v) => (v * 100).toFixed(1) + "%"),
  ])}
  <p class="note">No-offer world for reference: ${n0(P.no_offer.orders_per_week)} orders a week; loyal customers' Swiggy share ${(P.no_offer.swiggy_share_loyal * 100).toFixed(1)}%. TrueLift's figures include the cost of its control group.</p>
  ${consentHTML(M)}
  ${ledgerHTML(M, P)}
  ${forecastHTML2(M)}
  <h2>Are TrueLift's weekly numbers right?</h2>
  <p>For every TrueLift offer we compare its estimate of extra profit with the true value. "Control group only" uses just the restaurant's held-out customers; "model only" uses just the learned model; TrueLift combines them, weighting each by how noisy it is. Both noise sizes are re-estimated every week across all running offers, with no need for the truth: two random halves of each offer's customers show the real noise of its own estimate, and the spread of own estimates around the model's shows the model's real error.${M.fleet_calibration?.length ? ` After four weeks the running offers said the model's error was ${pct(M.fleet_calibration[M.fleet_calibration.length - 1].sigma_factor[0])} of what the shadow phase suggested, and the control groups' noise ${M.fleet_calibration[M.fleet_calibration.length - 1].noise_ratio[0].toFixed(2)} times it.` : ""}</p>
  ${tableHTML(["After", "Truth inside the 80% range", "Average error: control group only", "Model only", "TrueLift combined", "\"Keep\" verdicts right"],
    Object.entries(A).map(([k, a]) => tr([k.replace("after_", "").replace("_", " ").replace("1 weeks", "1 week"), pct(a.coverage_80), inr(a.mae_own_holdout_only), inr(a.mae_model_only), `<b>${inr(a.mae_combined)}</b>`, a.verdicts && a.verdicts.keep ? `${a.said_keep_and_truly_positive} of ${a.verdicts.keep}` : "–"])))}
  ${aaHTML(M)}
  <p class="note">Uplift ranking on the evaluation weeks: Qini ${M.uplift_quality.qini_model} (0 = random); correlation of predicted and true uplift per visit ${M.uplift_quality.corr_with_true_uplift}.</p>
  ${seedsHTML(E.seeds)}
  ${scenarioHTML(E)}
  ${tornadoHTML(E.sensitivity)}
  ${adoptionHTML(M)}
  ${fairnessHTML(M)}
  ${benchmarkHTML(E.learner_benchmark)}
  ${realDataHTML(E.real_data_criteo, E.real_data_hillstrom)}
  ${experimentsHTML(E.experiments)}
  ${frontierHTML(M)}
  ${speedHTML(E.latency)}
  <h2>What this does not prove</h2>
  <p>The market is simulated: customer types, price sensitivity and the Swiggy option are our assumptions, chosen to be plausible and then varied above. It shows that TrueLift's method finds the truth when there is one to find, and how much better targeted offers do than blanket ones under those assumptions. Real numbers need Zomato's own offer logs or a silent test on live offers.</p>`;
  el.dataset.done = "1";
  bindTips(el);
}

function consentHTML(M) {
  const c = M.consent_attrition;
  if (!c) return "";
  const P = M.policies, blind = c.blanket_owners_decline_blind;
  const pts = [[0, P.today_blanket.zomato_commission_change], ...Object.entries(blind).map(([k, v]) => [parseFloat(k) / 100, v.zomato_commission_change])];
  const be = c.break_even_blind_decline_share;
  return `<h2>For Zomato: when owners must approve every offer</h2>
  <p>Since August 2026 a restaurant-funded offer runs only after the owner's OTP. An owner who cannot see whether an offer pays may stop approving. The chart shows Zomato's extra commission when a share of owners stop approving blanket offers at random, against TrueLift with every owner approving.</p>
  <div class="charts"><div class="chart"><h3>Zomato's extra commission as owners stop approving</h3><div class="s">₹ a week against no offers; blanket offers with a share of owners declining at random</div>
    ${lineChart(pts, P.truelift.zomato_commission_change, be)}
    <div class="legend"><span><i class="line" style="background:var(--series)"></i>Blanket offers</span><span><i class="line" style="background:var(--ink-2)"></i>TrueLift, every owner approves</span></div></div>
    <div class="chart"><h3>What it means</h3>
      <p class="note">${be === null || be === undefined ? "Blanket offers stay above TrueLift's commission at every share tested." : be <= 0 ? "TrueLift already earns Zomato at least as much commission as blanket offers before any owner declines." : `Once more than <b>${pct(be)}</b> of owners stop approving blanket offers they cannot judge, Zomato earns less than with TrueLift, whose owners can see what each offer adds.`}</p>
      <div class="row"><span class="k">Owners with losing blanket offers decline (${c.blanket_losing_owners_decline.owners})</span><span class="v">${signed(c.blanket_losing_owners_decline.zomato_commission_change)}</span></div>
      <div class="row"><span class="k">TrueLift owners with losing offers decline (${c.truelift_losing_owners_decline.owners})</span><span class="v">${signed(c.truelift_losing_owners_decline.zomato_commission_change)}</span></div>
      <div class="row"><span class="k">TrueLift, every owner approves</span><span class="v">${signed(c.truelift_all_approve.zomato_commission_change)}</span></div></div></div>`;
}

function lineChart(pts, ref, marker) {
  const W = 460, H = 220, L = 70, Rm = 18, T = 14, B = 40;
  const ys = [...pts.map((p) => p[1]), ref], ymin = Math.min(0, ...ys), ymax = Math.max(...ys) * 1.08;
  const xmax = Math.max(...pts.map((p) => p[0]));
  const x = (v) => L + (v / xmax) * (W - L - Rm), y = (v) => T + (1 - (v - ymin) / (ymax - ymin)) * (H - T - B);
  const path = pts.map((p, i) => `${i ? "L" : "M"}${x(p[0]).toFixed(1)},${y(p[1]).toFixed(1)}`).join(" ");
  const yt = [0, 0.5, 1].map((g) => ymin + g * (ymax - ymin)).map((v) => `<line x1="${L}" x2="${W - Rm}" y1="${y(v)}" y2="${y(v)}" stroke="#ececec"></line><text x="${L - 6}" y="${y(v) + 4}" text-anchor="end">${lakh(v)}</text>`).join("");
  const xt = pts.map((p) => `<text x="${x(p[0])}" y="${H - B + 16}" text-anchor="middle">${Math.round(p[0] * 100)}%</text>`).join("");
  const dots = pts.map((p) => `<circle cx="${x(p[0])}" cy="${y(p[1])}" r="4" fill="var(--series)" data-tip="${Math.round(p[0] * 100)}% of owners decline: ${esc(signed(p[1]))} a week"></circle>`).join("");
  const mk = marker > 0 && marker <= xmax ? `<line x1="${x(marker)}" x2="${x(marker)}" y1="${T}" y2="${H - B}" stroke="var(--ink-2)" stroke-dasharray="3 3"></line><text class="lbl" x="${x(marker) + 5}" y="${T + 12}">break-even ${Math.round(marker * 100)}%</text>` : "";
  return `<svg viewBox="0 0 ${W} ${H}" width="100%" role="img" aria-label="Zomato commission as owners decline blanket offers">
    ${yt}${xt}<text x="${(L + W - Rm) / 2}" y="${H - 4}" text-anchor="middle">share of owners who stop approving</text>
    <line x1="${L}" x2="${W - Rm}" y1="${y(ref)}" y2="${y(ref)}" stroke="var(--ink-2)" stroke-width="1.5"></line>
    <path d="${path}" fill="none" stroke="var(--series)" stroke-width="2.2" stroke-linejoin="round"></path>${dots}${mk}</svg>`;
}

function ledgerHTML(M, P) {
  const z = M.zomato_ledger;
  if (!z) return "";
  const cf = z.cofunding, cg = z.control_group_cost_truelift, sh = z.platform_incremental_share_of_extra_orders;
  return `<h2>Zomato's own ledger</h2>
  <p>An extra order for a restaurant is not always an extra order for Zomato: some come from other restaurants on Zomato. The share that is new to the platform is what Zomato gains.</p>
  ${tableHTML(["", ...Object.keys(sh).map((k) => POLICY_NAMES[k] || k)], [tr(["Share of the offers' extra orders new to Zomato", ...Object.values(sh).map(pct)])])}
  <div class="calc"><h4>Zomato paying half the discount for customers new to Zomato, unmeasured</h4>
    <div class="row"><span class="k">Extra discount Zomato pays a week</span><span class="v">${inr(cf.extra_zomato_funded_discount)}</span></div>
    <div class="row"><span class="k">Extra orders new to the platform it buys</span><span class="v">${n0(cf.extra_platform_incremental_orders)}</span></div>
    <div class="row total"><span class="k">${cf.pure_transfer ? "The customer sees the same offer whoever pays for it, so this moves money from Zomato to restaurants and creates no order." : `Cost to Zomato per extra platform order: ${inr(cf.cost_per_extra_platform_incremental_order)}`}</span><span class="v">${signed(cf.contribution_change_vs_truelift)}</span></div></div>
  <p class="note">The price of measuring: TrueLift's control group (${pct(cg.holdout_share)} of eligible customers) forgoes about ${inr(cg.profit_forgone_a_week)} of restaurant profit and ${n0(cg.orders_forgone_a_week)} orders a week across the 300 restaurants, the cost of knowing what each offer adds.</p>`;
}

function forecastHTML2(M) {
  const f = M.forecast?.truelift_design_in_todays_market, o = M.forecast?.owner_blanket_offer_in_todays_market, s = M.selection;
  if (!f) return "";
  return `<h2>Are the forecasts owners approve right?</h2>
  <p>Each quote shown before the OTP is checked against the truth in the market it was made for, where a tenth of restaurants switch at a time.</p>
  ${tableHTML(["", "Forecast against truth", "Truth inside the 80% range", "Average miss a week"], [
    tr(["TrueLift's suggested version", `${f.ratio_forecast_to_truth}×`, pct(f.coverage_80), inr(f.mean_abs_error)]),
    tr(["The owner's own offer", `${o.ratio_forecast_to_truth}×`, pct(o.coverage_80), inr(o.mean_abs_error)]),
  ])}
  ${s ? `<p class="note">Of ${s.restaurants_with_a_different_version} suggested versions, ${pct(s.share_truly_better_than_owner)} truly beat the owner's own offer. Their stated advantage (${signed(s.forecast_advantage_total)} a week in total) runs about ${(s.forecast_advantage_total / s.true_advantage_total).toFixed(1)} times the true advantage (${signed(s.true_advantage_total)}): picking the best of about 34 forecasts favours the ones that came out high.</p>` : ""}`;
}

function aaHTML(M) {
  const aa = M.aa_test, d = M.detection?.blanket_fixed_holdout?.by_week?.week_4;
  if (!aa) return "";
  return `<p>Two checks of the weekly verdicts. <b>Placebo offers</b> that change nothing: over a four-week approval TrueLift paused ${pct(aa.lifetime_false_pause_4_looks)} of them (the rule used before, pause when the range is below zero, would have paused ${pct(aa.lifetime_false_pause_4_looks_rule_before)}).${d ? ` <b>Blanket offers that truly lose money</b>: by week 4, ${pct(d.losing_paused_or_warned)} are paused or flagged "probably losing", and ${pct(d.profitable_paused)} of profitable ones are paused.` : ""}</p>`;
}

function seedsHTML(S) {
  if (!S) return "";
  const lab = { offers_that_pay: "Offers that pay", own_offer_profit_effect: "Own-offer profit (₹ a week)", restaurant_profit_change: "Restaurant profit against no offers", zomato_commission_change: "Zomato commission", customer_savings: "Discount given" };
  const fmt = (m, v) => (m === "offers_that_pay" ? num(v) : signed(v));
  const rows = [];
  for (const [pair, ms] of Object.entries(S.differences)) {
    const other = pair.replace("truelift_minus_", "");
    for (const [m, d] of Object.entries(ms)) rows.push(tr([`TrueLift minus ${POLICY_NAMES[other] || other}: ${lab[m] || m}`, fmt(m, d.mean), fmt(m, d.sd), d.exceeds_2_sd ? "yes" : "no", d.same_sign_every_seed ? "yes" : "no"]));
  }
  return `<h2>Five different markets</h2>
  <p>The whole simulation repeated with ${S.seeds.length} market seeds (different customers, tastes and draws). Each row is TrueLift's difference from a comparison policy: the average, how much it varies, and whether it is larger than twice that variation.</p>
  ${tableHTML(["Difference", "Average", "Standard deviation", "Beyond 2 sd", "Same sign in every market"], rows)}`;
}

function scenarioHTML(E) {
  const sc = [["Customers 30% less price-sensitive", E.less_price_sensitive], ["Base case", E.main], ["Customers 30% more price-sensitive", E.more_price_sensitive], ["Commission charged on the price before the discount", E.pre_discount_commission]].filter((s) => s[1]);
  if (sc.length < 2) return "";
  return `<h2>If customers or commercial terms differ</h2>
  ${tableHTML(["Scenario", "Blanket: offers losing money", "Blanket: own-offer profit", "Rule: own-offer profit", "TrueLift: offers paying", "TrueLift: own-offer profit", "TrueLift: Zomato commission"],
    sc.map(([l, s]) => { const b = s.policies.today_blanket, r = s.policies.rule_new_customers, t = s.policies.truelift;
      return tr([l, `${b.offers_that_lose} of ${b.restaurants_with_offer}`, signed(b.own_offer_profit_effect), signed(r.own_offer_profit_effect), `${t.offers_that_pay} of ${t.restaurants_with_offer}`, signed(t.own_offer_profit_effect), signed(t.zomato_commission_change)], l === "Base case"); }))}
  <p class="note">Whether Zomato's commission is charged before or after the discount is a question for Eternal; it changes how much a blanket offer costs the owner.</p>`;
}

function tornadoHTML(S) {
  if (!S) return "";
  const outs = [["own_offer_profit", "TrueLift minus the rule: restaurants' profit from their own offers (₹ a week)", signed], ["zomato_commission", "TrueLift minus blanket: Zomato's commission (₹ a week)", signed], ["offers_that_pay", "TrueLift minus blanket: offers that pay", (v) => num(v)]];
  const params = Object.values(S.parameters);
  const charts = outs.map(([k, title, fmt]) => {
    const base = params[0].base.outputs[k];
    const items = params.map((p) => ({ label: p.label, lo: p.low.outputs[k], hi: p.high.outputs[k], lv: p.low.value, hv: p.high.value }))
      .sort((a, b) => Math.abs(b.hi - b.lo) - Math.abs(a.hi - a.lo));
    return `<div class="chart"><h3>${title}</h3><div class="s">Base ${esc(fmt(base))}; each bar moves one assumption to its low and high value (quick market)</div>${tornado(items, base, fmt)}</div>`;
  }).join("");
  return `<h2>Which assumptions matter</h2>
  <p>Eight assumptions, each moved to a low and a high value with everything else held. The longest bars are the assumptions a real pilot should pin down first.</p>
  <div class="charts">${charts}<div class="chart"><h3>Where a claim stops holding</h3>${S.boundaries.length ? `<ul class="note">${S.boundaries.map((b) => `<li>${esc(b)}</li>`).join("")}</ul>` : `<p class="note">No claim changes sign within these ranges.</p>`}</div></div>`;
}

function tornado(items, base, fmt) {
  const W = 460, rowH = 30, left = 168, right = 20, H = items.length * rowH + 24;
  const vals = items.flatMap((i) => [i.lo, i.hi, base]);
  const lo = Math.min(0, ...vals), hi = Math.max(0, ...vals);
  const x = (v) => left + ((v - lo) / (hi - lo || 1)) * (W - left - right);
  const bars = items.map((it, i) => {
    const y = 6 + i * rowH, a = x(Math.min(it.lo, it.hi)), b = x(Math.max(it.lo, it.hi));
    return `<g data-tip="${esc(it.label)}: ${esc(String(it.lv))} → ${esc(fmt(it.lo))}; ${esc(String(it.hv))} → ${esc(fmt(it.hi))}"><rect x="0" y="${y - 4}" width="${W}" height="${rowH}" fill="transparent"></rect>
      <text x="${left - 8}" y="${y + 12}" text-anchor="end">${esc(it.label.length > 26 ? it.label.slice(0, 25) + "…" : it.label)}</text>
      <rect x="${a}" y="${y + 2}" width="${Math.max(b - a, 1.5)}" height="14" rx="3" fill="var(--series)" opacity=".75"></rect></g>`;
  }).join("");
  return `<svg viewBox="0 0 ${W} ${H}" width="100%" role="img" aria-label="Sensitivity of the result to each assumption">
    <line x1="${x(0)}" x2="${x(0)}" y1="0" y2="${H - 18}" stroke="#c3c2b7"></line><line x1="${x(base)}" x2="${x(base)}" y1="0" y2="${H - 18}" stroke="var(--ink-2)" stroke-dasharray="3 3"></line>
    <text x="${x(base)}" y="${H - 4}" text-anchor="middle">base</text>${bars}</svg>`;
}

function adoptionHTML(M) {
  const a = M.partial_adoption;
  if (!a) return "";
  const rows = ["10%", "30%"].filter((k) => a[k]).map((k) => tr([`${k} of restaurants (${a[k].adopters})`, signed(a[k].adopters_profit_change_a_week), signed(a[k].others_profit_change_a_week), signed(a[k].zomato_commission_change_a_week), num(a[k].orders_change_a_week)]));
  const mh = M.moving_history;
  return `<h2>A pilot with some restaurants, not all</h2>
  <p>A real rollout starts with a few restaurants while the rest keep today's offers. Against today's market on the same visits:</p>
  ${tableHTML(["Restaurants on TrueLift", "Their profit (₹ a week)", "Everyone else's profit", "Zomato commission", "Orders"], rows)}
  ${mh ? `<p class="note">Letting customers' history move during the four weeks (a customer who orders in week 1 is no longer "new" in week 4) changes TrueLift's own-offer profit from ${signed(mh.fixed_snapshot.own_offer_profit_effect)} to ${signed(mh.features_follow_each_week.own_offer_profit_effect)} a week.</p>` : ""}`;
}

function fairnessHTML(M) {
  const f = M.fairness;
  if (!f || !f.truelift) return "";
  const pols = ["today_blanket", "truelift", "brand_pack_for_regulars", "regulars_always_eligible", "random_20pct_also_shown"].filter((k) => f[k]);
  const name = { today_blanket: "Blanket", truelift: "TrueLift", brand_pack_for_regulars: "TrueLift + Brand Pack for regulars", regulars_always_eligible: "TrueLift + regulars always eligible", random_20pct_also_shown: "TrueLift + 1 in 5 others shown at random" };
  const seg = (k, dim, v) => f[k].by_segment[dim]?.[v];
  const dims = [["regular", "regular here"], ["regular", "not a regular"], ["new_account", "new to Zomato"], ["price_band", "under Rs 300"], ["price_band", "Rs 500+"]];
  const rows = dims.map(([d, v]) => tr([`${v.replace("Rs ", "₹")} (${d === "price_band" ? "restaurant price" : d === "regular" ? "customer" : "account"})`, ...pols.map((k) => { const s = seg(k, d, v); return s ? `${pct(s.share_of_visits_offered_a_saving)} · ${inr(s.saving_received_per_visit)}` : "–"; })]));
  const mit = f.mitigations || {};
  return `<h2>Who gets the savings</h2>
  <p>Targeting gives discounts to the customers they move, so a restaurant's regulars, who order anyway, are offered less. Each cell: share of menu visits offered a saving (discount or Brand Pack reward) · saving received per visit.</p>
  ${tableHTML(["Visits by", ...pols.map((k) => name[k])], [...rows, tr(["Loyalty gap (others minus regulars, share offered)", ...pols.map((k) => (f[k].loyalty_gap === null ? "–" : (f[k].loyalty_gap * 100).toFixed(0) + " points"))], true)])}
  <p class="note">What closing the gap costs restaurants, in profit from their own offers against TrueLift: ${Object.entries(mit).map(([k, v]) => `${name[k]} ${signed(v.own_offer_profit_change_vs_truelift)}`).join("; ")} a week. The model reads only order and visit history, never location, device or payment method (an allow-list checked by the tests).</p>`;
}

function benchmarkHTML(B) {
  if (!B) return "";
  const nm = { random: "Random", response: "Likely buyers (chance of ordering with the offer)", rule: "Rule: new to the restaurant", s_learner: "S-learner (one model)", t_learner: "TrueLift (T-learner)", x_learner: "X-learner", dr_learner: "Doubly robust learner", oracle: "Oracle (true uplift)" };
  const ms = (o) => `${o.mean.toFixed(2)} ± ${o.sd.toFixed(2)}`;
  return `<h2>How the model compares with other ways to choose</h2>
  <p>Each method ranks next week's visits by how much the offer would move them; the simulator knows the truth. Averages over ${B.by_seed.length} markets, ± one standard deviation.</p>
  ${tableHTML(["Method", "Qini, share of the oracle's", "Correlation with true uplift", "Profit from the top 30%, share of the best possible"],
    Object.entries(B.summary).map(([k, m]) => tr([nm[k] || k, ms(m.normalised_qini), ms(m.corr_with_true_uplift), ms(m.profit_top_30pct_vs_best_possible)], k === "t_learner")))}`;
}

// Real randomised data (scripts/validate_uplift.py): one result per dataset, arm and outcome, each
// with five rankings. realTop30 reads one ranking's share of the extra outcomes in its top 30%.
const RANKINGS = [["random", "Random"], ["response", "Likely to act anyway"], ["s_learner", "S-learner"], ["t_learner", "TrueLift's method"], ["x_learner", "X-learner"]];
function realTop30(R, label, ranking, arm) {
  const r = R?.results?.find((x) => x.label === label && (!arm || x.arm === arm));
  return r?.rankings?.[ranking]?.top30_share_of_total_lift || null;
}
function realDataHTML(Rc, Rh) {
  const sets = [Rc, Rh].filter((R) => R?.results?.[0]?.rankings);
  if (!sets.length) return "";
  const outcome = { visit: "visits", conversion: "purchases", spend: "spend in dollars" };
  const arm = { ads: "ads", womens_email: "women's e-mail", mens_email: "men's e-mail" };
  const cell = (m) => (m && m.value !== null ? `${pct(m.value)}${m.interval_90 ? `<br><small>${pct(m.interval_90[0])} to ${pct(m.interval_90[1])}</small>` : ""}` : "–");
  const rows = sets.flatMap((R) => R.results.map((r) => tr([`${R.dataset === "criteo" ? "Criteo" : "Hillstrom"}, ${arm[r.arm] || r.arm}: ${outcome[r.label] || r.label}`,
    ...RANKINGS.map(([k]) => cell(r.rankings[k]?.top30_share_of_total_lift))])));
  const find = (R, label, arm) => R?.results?.find((r) => r.label === label && (!arm || r.arm === arm));
  const top = (r, k) => r?.rankings?.[k]?.top30_share_of_total_lift;
  const cv = find(Rc, "visit"), cc = find(Rc, "conversion"), hw = find(Rh, "visit", "womens_email");
  const tl = cv?.rankings.t_learner, rs = cv?.rankings.response;
  const says = [];
  if (cv) {
    const vals = RANKINGS.filter(([k]) => k !== "random").map(([k]) => top(cv, k).value);
    says.push(`On Criteo's visits every model puts ${pct(Math.min(...vals))} to ${pct(Math.max(...vals))} of the extra visits in its top 30%, the shortcut of ranking people by how likely they are to visit anyway included (TrueLift's method ${pct(top(cv, "t_learner").value)}, shortcut ${pct(top(cv, "response").value)}). In this advertising data, the people the ads move are mostly people already likely to visit.`);
  }
  if (cc) {
    const best = RANKINGS.filter(([k]) => k !== "random").reduce((m, [k, n]) => (top(cc, k).value > top(cc, m[0]).value ? [k, n] : m), ["t_learner", "TrueLift's method"]);
    says.push(`On Criteo's purchases (about ${Math.round(cc.mean_treated * 1000)} in 1,000 users shown ads buy), ${best[1].toLowerCase() === "likely to act anyway" ? "the shortcut" : `the ${best[1]}`} does best (${pct(top(cc, best[0]).value)}); TrueLift's method finds ${pct(top(cc, "t_learner").value)} and the X-learner ${pct(top(cc, "x_learner").value)}. With so few buyers among the ${pct(1 - cc.share_treated)} held out, a model fitted on the held-out group alone is noisy, which is the weakness the X-learner is built to avoid.`);
  }
  if (hw) {
    const t = top(hw, "t_learner"), r = top(hw, "response");
    const wins = t.splits && r.splits ? t.splits.filter((v, i) => v > r.splits[i]).length : null;
    says.push(`On Hillstrom's women's e-mail the uplift models find more: TrueLift's method's top 30% holds ${pct(t.splits_mean ?? t.value)} of the extra visits against ${pct(r.splits_mean ?? r.value)} for the shortcut${wins !== null ? `, higher in ${wins} of ${t.splits.length} random splits` : ""}. Here the customers likely to visit anyway are not the ones the e-mail moves, which is the situation of a restaurant's regulars.`);
  }
  const spend = Rh?.results?.filter((r) => r.label === "spend") || [];
  if (spend.length) {
    const clear = spend.flatMap((r) => RANKINGS.filter(([k]) => k !== "random" && top(r, k)?.interval_90?.[0] > 0.3).map(([, n]) => n));
    says.push(`On dollars spent, ${clear.length ? `only ${[...new Set(clear)].join(" and ")} stayed above random targeting across the resamples` : "no ranking is clearly better than random targeting"} with about ${n0(spend[0].test_rows)} test customers per e-mail: a few large orders decide dollar totals. This is why TrueLift models the chance of an order and computes the money from each order's economics, instead of learning rupees directly.`);
  }
  says.push("So which ranking works depends on the setting, and the shortcut is a real competitor. Zomato would settle it on its own offers the same way: the shadow phase's random holdout scores every candidate ranking before any of them is used.");
  if (tl?.qini_auc_score?.value != null) says.push(`Qini score as scikit-uplift defines it (a perfect ranking scores 1): ${tl.qini_auc_score.value.toFixed(3)} for TrueLift's method on Criteo's visits and ${rs.qini_auc_score.value.toFixed(3)} for the shortcut. This project's own measure, which divides by the campaign's total gain instead, gives ${tl.qini_ours.value.toFixed(3)}.`);
  return `<h2>On real data: two public randomised experiments</h2>
  <p>The same method, refitted on each dataset, ranks customers it never saw. <b>Criteo</b>: ${Rc ? `${(Rc.rows / 1e6).toFixed(0)} million` : "14 million"} users of Criteo's advertising tests, a random 15% held out of ads like TrueLift's control group. <b>Hillstrom</b>: ${Rh ? n0(Rh.rows) : "64,000"} customers of a US retailer, e-mailed at random with men's or women's merchandise or nothing, with what they spent. Neither is about food discounts: they test the method, not Zomato's numbers. Each ranking is compared with the shortcut practitioners use: rank people by how likely they are to act at all.</p>
  ${tableHTML(["Share of the extra outcomes in the top 30% of each ranking", ...RANKINGS.map(([, n]) => n)], rows,
    "Random targeting finds about 30%. Below each figure, its 90% range from 200 resamples of the test customers.")}
  <div class="charts">
    ${cv ? `<div class="chart"><h3>Criteo: extra visits found, by share of people targeted</h3><div class="s">Share of all the extra visits the full campaign created</div>
      ${qiniChart({ share_targeted: cv.curve.share_targeted, model: cv.curve.t_learner, random: cv.curve.random, response: cv.curve.response })}
      <div class="legend"><span><i class="line" style="background:var(--series)"></i>TrueLift's method</span><span><i class="line dash" style="background:var(--series)"></i>Likely to act anyway</span><span><i class="line" style="background:var(--series-mute)"></i>Random targeting</span></div></div>` : ""}
    <div class="chart"><h3>What it means</h3>
      ${says.map((x) => `<p class="p">${x}</p>`).join("")}
      <p class="note">Every model is the same kind of gradient-boosted tree. Five random 70/30 splits of each dataset give the spread in <code>reports/uplift_validation_*.json</code>.</p></div>
  </div>`;
}

function experimentsHTML(X) {
  if (!X) return "";
  const o = X.oracle, d = X.depth_choice, v = X.variance_reduction, h = X.holdout_draws, r = X.retrain_loop, t = X.depth_test;
  const items = [];
  if (o) items.push(`<b>Targeting against a perfect oracle.</b> With one fixed discount at every restaurant, the model's choice of who sees it adds ${signed(o.model_targeting_profit_gain_a_week - o.blanket_profit_gain_a_week)} a week over showing it to everyone; an oracle that knows every visit's true response would add ${signed(o.oracle_profit_gain_a_week - o.blanket_profit_gain_a_week)}. The model captures ${pct(o.share_of_oracle_gain_over_blanket_captured)} of what is possible.`);
  if (d) items.push(`<b>Letting the model pick the discount size.</b> Own-offer profit ${signed(d.model_picks_size.own_offer_profit_effect)} against ${signed(d.owner_size_kept.own_offer_profit_effect)} with the owner's size, but restaurant profit across the market ${signed(d.model_picks_size.restaurant_profit_change)} against ${signed(d.owner_size_kept.restaurant_profit_change)}, and ${d.model_picks_size.offers_that_lose} losing offers against ${d.owner_size_kept.offers_that_lose}. Deeper discounts win orders from other restaurants. The size stays the owner's call.`);
  if (t) items.push(`<b>A test of two sizes.</b> When customers are split at random between the owner's size and the next one up, four weeks of a restaurant's own data pick the truly better size ${pct(t.share_picking_the_truly_better_size)} of the time (${pct(t.share_right_larger_half)} for the larger half of restaurants, ${pct(t.share_right_smaller_half)} for the smaller). A size change needs a longer test or pooling across similar restaurants.`);
  if (v) items.push(`<b>Subtracting each visit's predicted outcome.</b> Cuts the error of an offer's own estimate by ${pct(v.noise_cut)} (${inr(v.rmse_without_adjustment)} → ${inr(v.rmse_with_adjustment)} over four weeks, ${v.draws} random holdout draws).`);
  if (h) items.push(`<b>Ten holdout draws.</b> Across ${h.draws} random choices of who is held out, the weekly estimate's average error is ${signed(h.mean_error_rs)} (standard error ${inr(h.mean_error_se_rs)}): centred on the truth. Its 80% range held the truth ${pct(h.coverage_80)} of the time.`);
  if (r) items.push(`<b>Retraining on live weeks.</b> A model retrained after two weeks of running offers ranks the next two weeks ${r.promote ? "better" : "no better"} (Qini ${r.candidate_model.qini_on_holdout} against ${r.current_model.qini_on_holdout}), so it ${r.promote ? "would be promoted" : "would not be promoted"} under the rule: promote only on the random holdout's evidence.`);
  return `<h2>Experiments behind the write-up</h2><div class="faq">${items.map((i) => `<p class="p">${i}</p>`).join("")}</div>`;
}

function frontierHTML(M) {
  const f = M.zomato_weight_frontier;
  if (!f) return "";
  return `<h2>Should TrueLift weigh Zomato's revenue?</h2>
  <p>We tried giving Zomato's contribution a weight when choosing each restaurant's version. It buys Zomato almost nothing, because restaurant and platform earn from the same extra orders, while restaurants lose. TrueLift chooses for the restaurant.</p>
  ${tableHTML(["Weight on Zomato's contribution", "Restaurant profit against no offers", "Zomato commission", "Offers that lose"], f.points.map((p) => tr([String(p.zomato_weight), signed(p.restaurant_profit_change), signed(p.zomato_commission_change), num(p.offers_that_lose)], p.zomato_weight === 0)))}`;
}

// ---------------- operations ----------------
async function renderOps() {
  const el = $("#ops");
  if (el.dataset.done) return;
  let E;
  try { E = await once("evidence", () => api("/api/v1/evidence")); } catch (e) { el.innerHTML = errorCard(e, "the operations view"); return; }
  const G = E.guardrails, D = E.drift, meta = E.meta || {}, r = E.experiments?.retrain_loop;
  const status = (ok) => `<span class="tag ${ok ? "good" : "bad"}">${ok ? "pass" : "fail"}</span>`;
  const val = (v) => (v === null || v === undefined ? "–" : typeof v === "object" ? Object.entries(v).map(([k, x]) => `${esc(k.replace(/_/g, " "))} ${esc(typeof x === "number" && x < 1 ? pct(x) : String(x))}`).join(", ") : esc(String(v)));
  const tables = D ? [...new Set(Object.values(D.features).flatMap((f) => Object.keys(f).filter((k) => typeof f[k] === "object")))] : [];
  el.innerHTML = `<h1>Operations</h1>
  <p>What an on-call person at Zomato would watch once TrueLift runs: the weekly guardrails, whether the model's inputs have drifted from what it learned on, how fast the hooks answer, and how a new model is promoted. Computed by the pipeline from the simulated market; in production the same checks run on the exposure log.</p>
  ${G ? `<h2>Weekly guardrails</h2><p>Checked on ${G.offers} running offers after ${G.weeks} weeks. ${G.passed ? "All pass." : "At least one fails: the line says what it would mean."}</p>
  ${tableHTML(["Check", "Value", "Threshold", "Status", "What a failure means"], G.checks.map((c) => tr([esc(c.check.replace(/_/g, " ")), val(c.value), esc(c.threshold), status(c.passed), esc(c.meaning)])))}` : ""}
  ${D ? `<h2>Input drift</h2><p>Each model input in the tables it is used on, against the rows it was trained on (population stability index; below ${D.psi_watch} is stable, above ${D.psi_fail} fails the pipeline). Largest: ${D.worst_psi}. ${D.passed ? "No input has moved." : "An input has moved: retrain before trusting the forecasts."}</p>
  ${tableHTML(["Input", ...tables.map((t) => t.replace(/_/g, " "))], Object.entries(D.features).map(([f, e]) => tr([`<code>${esc(f)}</code>`, ...tables.map((t) => (e[t] ? `<span class="tag ${e[t].status === "pass" ? "good" : e[t].status === "watch" ? "warn" : "bad"}">${e[t].status}</span> ${e[t].psi.toFixed(3)}` : "–"))])))}` : ""}
  ${speedHTML(E.latency)}
  <h2>How a new model goes live</h2>
  <div class="steps4">
    <div class="step4"><div class="n">1</div><h4>Log</h4><p>Every shown and held-out visit and every order, with the model version that decided it.</p></div>
    <div class="step4"><div class="n">2</div><h4>Retrain</h4><p>A candidate model learns from the shadow phase plus the weeks offers have run.</p></div>
    <div class="step4"><div class="n">3</div><h4>Compare on the holdout</h4><p>It must rank the next weeks' visits better, judged only on the random control groups.</p></div>
    <div class="step4"><div class="n">4</div><h4>Promote and record</h4><p>The new version's number goes into every quote, decision and consent record.</p></div>
  </div>
  ${r ? `<p class="note">In the simulation, a model retrained after two weeks of running offers scores Qini ${r.candidate_model.qini_on_holdout} on the next two weeks against ${r.current_model.qini_on_holdout} for the current one, so it ${r.promote ? "would be promoted" : "would not be promoted"}.</p>` : ""}
  <h2>This run</h2>
  <div class="calc">
    <div class="row"><span class="k">Code version</span><span class="v"><code>${esc((meta.commit || "").slice(0, 10) || "–")}</code>${meta.uncommitted_changes ? " (with uncommitted changes)" : ""}</span></div>
    <div class="row"><span class="k">Run at (UTC)</span><span class="v">${esc(meta.started_utc || "–")}</span></div>
    <div class="row"><span class="k">Libraries</span><span class="v">${esc(Object.entries(meta.libraries || {}).map(([k, v]) => `${k} ${v}`).join(", ") || "–")}</span></div>
    <div class="row"><span class="k">Live service endpoints</span><span class="v"><code>/healthz</code> <code>/readyz</code> <code>/metrics</code></span></div>
  </div>`;
  el.dataset.done = "1";
}

function speedHTML(L) {
  if (!L) return "";
  const s = L.serve_sequential, p = Object.entries(L).find(([k]) => /^serve_\d+_threads$/.test(k)), q = L.quote_sequential;
  return `<h2>Speed</h2>
  <p>Measured over HTTP on ${esc(L.hardware.processor || "a laptop")} (${L.hardware.logical_cpus} threads). A serving decision is a table lookup plus the control-group hash.</p>
  ${tableHTML(["Call", "Median", "95th percentile", "99th percentile"], [
    tr(["Serve one customer, one at a time", `${s.p50_ms} ms`, `${s.p95_ms} ms`, `${s.p99_ms} ms`]),
    p ? tr([`Serve, ${p[0].match(/\d+/)[0]} at once (${num(p[1].throughput_per_second)} a second)`, `${p[1].p50_ms} ms`, `${p[1].p95_ms} ms`, `${p[1].p99_ms} ms`]) : "",
    tr(["Forecast an offer (about 34 versions compared)", `${q.p50_ms} ms`, `${q.p95_ms} ms`, `${q.p99_ms} ms`]),
  ])}`;
}

function qiniChart(cu) {
  const W = 460, H = 236, L = 44, Rm = 20, T = 16, B = 46;
  const xs = cu.share_targeted, ys = [...cu.model, ...cu.random, ...(cu.response || [])];
  const ymax = Math.max(1, ...ys), ymin = Math.min(0, ...ys);
  const x = (v) => L + v * (W - L - Rm), y = (v) => T + (1 - (v - ymin) / (ymax - ymin)) * (H - T - B);
  const path = (arr) => arr.map((v, i) => `${i ? "L" : "M"}${x(xs[i]).toFixed(1)},${y(v).toFixed(1)}`).join(" ");
  const grid = [0, 0.25, 0.5, 0.75, 1].map((g) => `<line x1="${L}" x2="${W - Rm}" y1="${y(g)}" y2="${y(g)}" stroke="#e1e0d9"></line><text x="${L - 6}" y="${y(g) + 4}" text-anchor="end">${Math.round(g * 100)}%</text>`).join("");
  const xt = [0, 0.25, 0.5, 0.75, 1].map((g) => `<text x="${x(g)}" y="${H - B + 16}" text-anchor="middle">${Math.round(g * 100)}%</text>`).join("");
  const n = xs.length - 1;
  const hits = xs.map((f, i) => `<rect x="${x(f) - (W - L - Rm) / n / 2}" y="${T}" width="${(W - L - Rm) / n}" height="${H - T - B}" fill="transparent"
     data-tip="Target ${Math.round(f * 100)}% of people: the model finds ${Math.round(cu.model[i] * 100)}% of the extra visits${cu.response ? `, the shortcut ${Math.round(cu.response[i] * 100)}%` : ""}, random ${Math.round(cu.random[i] * 100)}%"></rect>`).join("");
  return `<svg viewBox="0 0 ${W} ${H}" width="100%" role="img" aria-label="Qini curve: model versus random">
    ${grid}${xt}<text x="${(L + W - Rm) / 2}" y="${H - 4}" text-anchor="middle">share of people targeted (highest predicted uplift first)</text>
    <path d="${path(cu.random)}" fill="none" stroke="var(--series-mute)" stroke-width="2" stroke-linejoin="round" stroke-linecap="round"></path>
    ${cu.response ? `<path d="${path(cu.response)}" fill="none" stroke="var(--series)" stroke-width="2" stroke-dasharray="5 4" stroke-linejoin="round" stroke-linecap="round"></path>` : ""}
    <path d="${path(cu.model)}" fill="none" stroke="var(--series)" stroke-width="2" stroke-linejoin="round" stroke-linecap="round"></path>
    <text class="lbl" x="${x(xs[Math.round(n * 0.3)]) + 6}" y="${y(cu.model[Math.round(n * 0.3)]) - 10}">Model</text>
    <text x="${x(xs[Math.round(n * 0.7)]) + 8}" y="${y(cu.random[Math.round(n * 0.7)]) + 16}">Random</text>
    ${hits}</svg>`;
}

function hbar(items, fmt) {
  // single series, zero baseline, value label at the bar tip, TrueLift highlighted
  const W = 460, rowH = 34, left = 200, right = 76, H = items.length * rowH + 10;
  const vals = items.map((i) => i[1]);
  const lo = Math.min(0, ...vals), hi = Math.max(0, ...vals);
  const x = (v) => left + ((v - lo) / (hi - lo || 1)) * (W - left - right);
  const bars = items.map(([label, v, hl], i) => {
    const y = 8 + i * rowH, x0 = x(0), x1 = x(v), w = Math.max(Math.abs(x1 - x0), 1), bx = Math.min(x0, x1), r = Math.min(4, w / 2);
    const path = v >= 0
      ? `M${bx},${y} h${w - r} a${r},${r} 0 0 1 ${r},${r} v${18 - 2 * r} a${r},${r} 0 0 1 -${r},${r} h-${w - r} z`
      : `M${bx + w},${y} h-${w - r} a${r},${r} 0 0 0 -${r},${r} v${18 - 2 * r} a${r},${r} 0 0 0 ${r},${r} h${w - r} z`;
    return `<g data-tip="${esc(label)}: ${esc(fmt(v))}"><rect x="0" y="${y - 6}" width="${W}" height="${rowH}" fill="transparent"></rect>
      <text x="${left - 8}" y="${y + 13}" text-anchor="end">${esc(label)}</text>
      <path d="${path}" fill="${hl ? "var(--series)" : "var(--series-mute)"}"></path>
      <text class="lbl" x="${v >= 0 ? x1 + 6 : x1 - 6}" y="${y + 13}" text-anchor="${v >= 0 ? "start" : "end"}">${esc(fmt(v))}</text></g>`;
  }).join("");
  return `<svg viewBox="0 0 ${W} ${H}" width="100%" role="img"><line x1="${x(0)}" x2="${x(0)}" y1="0" y2="${H}" stroke="#c3c2b7"></line>${bars}</svg>`;
}

// Chart tooltips work with a mouse, a keyboard (each mark is focusable) and touch (tap to show).
function bindTips(root) {
  const tip = $("#tip");
  const place = (x, y) => { tip.style.left = Math.max(8, Math.min(x + 12, innerWidth - 310)) + "px"; tip.style.top = Math.min(y + 12, innerHeight - 60) + "px"; };
  const show = (g, x, y) => { tip.textContent = g.dataset.tip; tip.style.display = "block"; place(x, y); };
  const hide = () => { tip.style.display = "none"; };
  root.querySelectorAll("[data-tip]").forEach((g) => {
    g.setAttribute("tabindex", "0");
    g.setAttribute("role", "img");
    g.setAttribute("aria-label", g.dataset.tip);
    g.addEventListener("mousemove", (e) => show(g, e.clientX, e.clientY));
    g.addEventListener("mouseleave", hide);
    g.addEventListener("focus", () => { const r = g.getBoundingClientRect(); show(g, r.left + r.width / 2, r.top); });
    g.addEventListener("blur", hide);
    g.addEventListener("touchstart", (e) => { const t = e.touches[0]; show(g, t.clientX, t.clientY); }, { passive: true });
  });
  document.addEventListener("touchstart", (e) => { if (!e.target.closest?.("[data-tip]")) hide(); }, { passive: true });
}

// ---------------- money maths ----------------
const MONEY = { commission_on: "post_discount", food: 0.37 };
async function renderMoney() {
  const el = $("#money");
  let e;
  try {
    e = await once(`example-${MONEY.commission_on}-${MONEY.food}`, () => api(`/api/v1/example?commission_on=${MONEY.commission_on}&food_cost_share=${MONEY.food}`));
  } catch (err) { el.innerHTML = errorCard(err, "the money example"); return; }
  const f = e.per_order_full, d = e.per_order_discounted, b = e.blanket, t = e.truelift, n = e.no_offer, T = e.terms;
  const pre = T.commission_on === "pre_discount";
  const be = e.break_even.find((x) => Math.round(x.discount) === Math.round(e.discount)) || e.break_even[1];
  const line = (k, v, total) => `<div class="row ${total ? "total" : ""}"><span class="k">${k}</span><span class="v">${v}</span></div>`;
  const pc = (x) => `${Math.round(x * 1000) / 10}%`;
  const chip = (key, val, label) => `<button class="chip ${MONEY[key] === val ? "on" : ""}" data-money="${key}" data-val="${val}" aria-pressed="${MONEY[key] === val}">${label}</button>`;
  el.innerHTML = `<h1>The money, step by step</h1>
  <p>The Round 1 example: a restaurant with ${inr(e.basket)} orders and ${e.regulars} orders a week from regulars. A ${inr(e.discount)}-off offer brings ${e.new_orders} new orders. Commission is ${pct(T.commission_rate)} plus ${pct(T.gst_on_commission)} GST on it; food and packaging cost ${pct(T.food_cost_share)} of the order. Every figure below is computed by the same code the service uses.</p>
  <div class="field"><span class="lab">Commission is charged on</span><div class="chips" role="group" aria-label="Commission base">
    ${chip("commission_on", "post_discount", "the price after the discount")}${chip("commission_on", "pre_discount", "the menu price, before the discount")}</div></div>
  <div class="field"><span class="lab">Food and packaging cost</span><div class="chips" role="group" aria-label="Food cost">
    ${chip("food", 0.3, "30%")}${chip("food", 0.37, "37% (typical)")}${chip("food", 0.45, "45%")}</div></div>
  <div class="charts">
  <div class="calc"><h4>One ${inr(e.basket)} order</h4>
    ${line("Food sales", inr2(f.basket))}${line(`Commission (${pct(T.commission_rate)})`, "−" + inr2(f.commission))}${line(`GST on commission (${pct(T.gst_on_commission)})`, "−" + inr2(f.gst_on_commission))}${line(`Food and packaging (${pct(T.food_cost_share)})`, "−" + inr2(f.food_cost))}
    ${line("<b>Restaurant keeps</b>", inr2(f.restaurant_profit), true)}${line("Zomato's gross commission", inr2(f.commission))}</div>
  <div class="calc"><h4>The same order with ${inr(e.discount)} off (paid by the restaurant)</h4>
    ${line("Food sales", inr2(d.basket))}${line("Discount", "−" + inr2(d.discount))}${line(`Commission (${pct(T.commission_rate)} of ${inr(pre ? d.basket : d.basket - d.discount)})`, "−" + inr2(d.commission))}${line("GST on commission", "−" + inr2(d.gst_on_commission))}${line("Food and packaging", "−" + inr2(d.food_cost))}
    ${line("<b>Restaurant keeps</b>", inr2(d.restaurant_profit), true)}${line("Zomato's gross commission", inr2(d.commission))}</div>
  </div>
  <div class="calc"><h4>When does ${inr(e.discount)} off pay for itself?</h4>
    <p class="note">Of the orders using the offer, let <i>f</i> be the share that would not have happened without it. The restaurant gains ${inr2(d.restaurant_profit)} on those and loses ${inr2(f.restaurant_profit)} − ${inr2(d.restaurant_profit)} = ${inr2(f.restaurant_profit - d.restaurant_profit)} on every other one. It breaks even when f × ${inr2(d.restaurant_profit)} = (1 − f) × ${inr2(f.restaurant_profit - d.restaurant_profit)}, so <b>f = 1 − ${inr2(d.restaurant_profit)} / ${inr2(f.restaurant_profit)} = ${pc(be.extra_share_needed)}</b>.</p>
    ${e.break_even.map((x) => line(`${Math.round(x.share_of_basket * 100)}% off (${inr(x.discount)})`, `pays only if ≥ ${Math.round(x.extra_share_needed * 100)}% of its orders are extra`)).join("")}</div>
  ${e.pct_example ? `<div class="calc"><h4>A percentage offer: ${pct(e.pct_example.pct)} off up to ${inr(e.pct_example.cap)}</h4>
    <p class="note">Most offers on Zomato are written this way. The rupees off depend on the order: ${pct(e.pct_example.pct)} of it, but never more than ${inr(e.pct_example.cap)}. Above ${inr(e.pct_example.cap / e.pct_example.pct)} the offer is simply ${inr(e.pct_example.cap)} off, so the headline percentage is paid only on small orders, where the restaurant keeps least.</p>
    ${e.pct_example.rows.map((x) => line(`${inr(x.basket)} order: ${inr2(x.discount)} off (${Math.round(x.share_of_basket * 100)}% of it)`, `pays only if ≥ ${Math.round(x.extra_share_needed * 100)}% of its orders are extra`)).join("")}</div>` : ""}
  <div class="calc"><h4>One week</h4>
    ${line(`No offer: ${e.regulars} × ${inr2(f.restaurant_profit)}`, inr2(n.restaurant_profit))}
    ${line(`Today, ${inr(e.discount)} off for everyone: ${e.regulars + e.new_orders} × ${inr2(d.restaurant_profit)}`, inr2(b.restaurant_profit))}
    ${line("<b>Change for the restaurant</b>", `<span class="${cls(b.restaurant_change)}">${inr2(b.restaurant_change, true)}</span>`, true)}
    ${line(`Zomato: ${e.regulars + e.new_orders} × ${inr2(d.commission)} − ${e.regulars} × ${inr2(f.commission)}`, inr2(b.zomato_change, true))}
    ${line(`Discount given: ${inr2(b.discount_spend)} (of which ${inr2(b.discount_on_regulars)} on regulars) ÷ ${e.new_orders} extra orders`, inr2(b.discount_per_extra_order) + " per extra order")}
    <br>
    ${line(`TrueLift: ${e.regulars} × ${inr2(f.restaurant_profit)} + ${e.new_orders} × ${inr2(d.restaurant_profit)} − ${inr(e.rewards)} rewards`, inr2(t.restaurant_profit))}
    ${line("<b>Change for the restaurant</b>", `<span class="${cls(t.restaurant_change)}">${inr2(t.restaurant_change, true)}</span>`, true)}
    ${line(`Zomato: ${e.new_orders} × ${inr2(d.commission)}`, inr2(t.zomato_change, true))}
    ${line(`Spend: ${e.new_orders} × ${inr(e.discount)} + ${inr(e.rewards)} rewards = ${inr2(t.discount_spend)} ÷ ${e.new_orders} extra orders`, inr2(t.discount_per_extra_order) + " per extra order")}</div>
  <p class="note">The Round 1 page rounded commission + GST to 30%; the exact figures are above. Whether Zomato charges commission before or after the discount is a question for Eternal: it moves the break-even share. Zomato's gross commission is not its profit: after delivery costs, Zomato's food-delivery business earns about 5.5% of order value as adjusted EBITDA (Q2 FY27).</p>`;
  el.querySelectorAll("[data-money]").forEach((btn) => btn.addEventListener("click", () => {
    const k = btn.dataset.money;
    MONEY[k] = k === "food" ? +btn.dataset.val : btn.dataset.val;
    renderMoney();
  }));
}

boot().catch((e) => { $("#screen").innerHTML = errorCard(e, "the demo"); });
