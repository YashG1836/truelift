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
const LOCAL = { offers: {}, next: 1 };
// One file per design. With no discount, minimum order, audience and time make no difference, so
// those designs share one key (the export writes exactly these keys; scripts/export_static.py key()).
const dkey = (d) => (d.discount > 0
  ? `${Math.round(d.discount)}-${Math.round(d.min_order)}-${d.audience}-${d.offpeak_only ? 1 : 0}-${Math.round(d.reward)}`
  : `0-0-all-0-${Math.round(d.reward)}`);

async function sget(file) {
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
  const consent = o.status === "awaiting_otp" ? null : { ...o.full.consent, approved_at: o.approvedAt };
  return { ...o.full, offer_id: +id, status: o.status, consent, weeks: o.full.weeks.slice(0, o.shown) };
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
  if (path === "/api/v1/example") return sget("example.json");
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
const S = { rid: null, card: null, design: null, quote: null, offer: null, otp: null, screen: "home", busy: false, err: "" };
const AUDIENCES = [["all", "Everyone"], ["new_to_restaurant", "New to you"], ["lapsed", "Stopped ordering"], ["targeted", "Let TrueLift choose"]];
const STATUS = {
  awaiting_otp: ["Waiting for your OTP", ""], active: ["Running", "good"], paused: ["Paused: it was losing money", "bad"],
  stopped: ["Stopped", ""], consent_expired: ["4-week approval over", "red"],
};

// The create screen offers exactly the options the server lists on the restaurant's card, so the
// page can never ask for a design the static export did not write (audit TL-002).
function defaultDesign(card) {
  return { discount: card.design_options.default_depth, min_order: 0, audience: "all", offpeak_only: false, reward: 0, zomato_share: 0 };
}
function designOptions(card) {
  const o = card.design_options;
  return { depths: o.depths, mov: o.min_order, reward: o.reward };
}

// ---------------- boot and navigation ----------------
async function boot() {
  document.querySelectorAll("nav button").forEach((b) => b.addEventListener("click", () => showTab(b.dataset.tab)));
  $("#tourBtn").addEventListener("click", () => Tour.start());
  $("#tourNext").addEventListener("click", () => Tour.next());
  $("#tourPrev").addEventListener("click", () => Tour.restart());
  $("#who").innerHTML = `<div class="empty">Loading who sees the discount…</div>`;
  $("#tourExit").addEventListener("click", () => Tour.stop());
  document.addEventListener("keydown", (e) => { // presenter keys while the guided demo is open
    if (!$("#tour").classList.contains("on") || e.target.matches("input, select, textarea")) return;
    if (e.key === "ArrowRight" || e.key === "Enter") { e.preventDefault(); if (!$("#tourNext").disabled) Tour.next(); }
    if (e.key === "Escape") Tour.stop();
  });
  const now = new Date();
  $("#clock").textContent = now.toLocaleTimeString("en-IN", { hour: "2-digit", minute: "2-digit" });
  $("#screen").innerHTML = `<div class="empty">Loading the market…</div>`;
  const data = await api("/api/v1/restaurants");
  const sel = $("#rest");
  const list = data.restaurants.filter((r) => r.menu_visits_per_week > 0)
    .sort((a, b) => (b.restaurant_id === data.demo_restaurant) - (a.restaurant_id === data.demo_restaurant) || a.name.localeCompare(b.name));
  sel.innerHTML = list.map((r) => `<option value="${r.restaurant_id}">${esc(r.name)} · ${esc(r.locality)}</option>`).join("");
  sel.value = data.demo_restaurant;
  sel.addEventListener("change", () => openRestaurant(+sel.value));
  const tab = (location.hash || "").replace("#", "");
  await openRestaurant(data.demo_restaurant);
  if (["how", "evidence", "money"].includes(tab)) showTab(tab);
}

function showTab(t) {
  document.querySelectorAll("nav button").forEach((b) => b.classList.toggle("on", b.dataset.tab === t));
  document.querySelectorAll(".tab").forEach((s) => s.classList.toggle("on", s.id === "tab-" + t));
  $(".pick label").style.visibility = $(".pick select").style.visibility = t === "demo" ? "visible" : "hidden";
  history.replaceState(null, "", t === "demo" ? location.pathname : "#" + t);
  if (t === "how") renderHow();
  if (t === "evidence") renderEvidence();
  if (t === "money") renderMoney();
  window.scrollTo(0, 0);
}

async function openRestaurant(rid) {
  await api("/api/v1/reset", {});
  Object.assign(S, { rid, offer: null, quote: null, err: "" });
  S.card = await api(`/api/v1/restaurants/${rid}`);
  S.design = defaultDesign(S.card);
  $("#rest").value = rid;
  go("home");
  refreshInside();
}

function go(screen) { S.screen = screen; render(); }

function render() {
  const c = S.card;
  $("#phead").innerHTML = `<div class="row1"><h1>${esc(c.name)}</h1><span class="online">Online</span></div>
    <div class="sub">${esc(c.locality)} · ${esc(c.cuisines)} · <span class="rating">${c.rating} ★</span> · <span class="tag sim">simulated data</span></div>`;
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
      <div class="row"><span class="k">3. 1 in 10 don't see it, so it's measured</span><span class="v">✓</span></div>
      <div class="row"><span class="k">4. Weekly result on WhatsApp</span><span class="v">✓</span></div></div>`;
}

function createHTML() {
  const d = S.design, o = designOptions(S.card);
  const chip = (field, val, label) => `<button class="chip ${d[field] === val ? "on" : ""}" data-set="${field}" data-val='${JSON.stringify(val)}'>${label}</button>`;
  return `<button class="back" data-go="home">← Back</button>
  <div class="field"><span class="lab">Discount</span><div class="chips">${o.depths.map((v) => chip("discount", v, "₹" + v + " off")).join("")}</div></div>
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

function forecastBlock(x) {
  return `<div class="big ${cls(x.profit_change)}">${inr(x.profit_change, true)}<span class="note" style="font-weight:400"> extra profit a week</span></div>
    <div class="note">likely between ${inr(x.profit_low, true)} and ${inr(x.profit_high, true)}</div>
    ${rangeHTML(x.profit_low, x.profit_high, x.profit_change)}
    <div class="mini">
      <div><div class="v">${n0(x.redemptions)}</div><div class="l">orders would use it</div></div>
      <div><div class="v">${n0(x.extra_orders)}</div><div class="l">of them are extra orders</div></div>
      <div><div class="v">${x.anyway_share === null ? "–" : pct(x.anyway_share)}</div><div class="l">would come anyway</div></div>
    </div>
    <div class="row"><span class="k">Discount you give per extra order</span><span class="v">${x.discount_per_extra_order ? inr(x.discount_per_extra_order) : "–"}</span></div>
    <div class="row"><span class="k">Average order with the offer</span><span class="v">${inr(x.order_value_with_offer)}</span></div>
    <div class="row"><span class="k">Zomato's extra commission</span><span class="v">${inr(x.zomato_commission_change, true)}</span></div>`;
}

function forecastHTML(q) {
  const o = q.owner, b = q.better;
  const why = o.redemptions > 0 && o.anyway_share !== null
    ? `${Math.round(o.anyway_share * 10)} in 10 orders using this offer would have come anyway, so that part of the discount buys nothing.`
    : "Forecast from customers who visited your menu in the last two weeks.";
  return `<div class="card ${o.profit_change < 0 ? "warn" : ""}" id="ownerCard"><div class="eyebrow">Forecast for your offer · one week</div>
      ${forecastBlock(o)}<p class="note">${why}</p></div>
    ${b ? `<div class="card better" id="betterCard"><div class="eyebrow">TrueLift suggests</div><h4>${esc(b.label)}</h4>
      <p class="note"><b class="pos">${inr(b.profit_change - o.profit_change, true)} more a week</b> than your version, same discount size. Best of ${q.designs_compared} versions compared.</p>
      ${forecastBlock(b)}<button class="btn small" data-act="useBetter">Use this version</button></div>`
      : `<div class="card"><p class="note">This is already the best of the ${q.designs_compared} versions compared (who sees it, minimum order, time, Brand Pack). The discount size is yours to choose.</p></div>`}`;
}

function otpHTML() {
  const off = S.offer, q = off.quote;
  return `<button class="back" data-go="create">← Change offer</button>
  <div class="card"><div class="eyebrow">Approve this offer</div><h4>${esc(off.label)}</h4>
    <div class="row"><span class="k">Expected extra orders a week</span><span class="v">${n0(q.extra_orders)}</span></div>
    <div class="row"><span class="k">Expected extra profit a week</span><span class="v ${cls(q.profit_change)}">${inr(q.profit_change, true)}</span></div>
    <div class="row"><span class="k">Likely range</span><span class="v">${inr(q.profit_low, true)} to ${inr(q.profit_high, true)}</span></div>
    <div class="row"><span class="k">Runs for</span><span class="v">4 weeks, then needs a new OTP</span></div>
    <p class="note">${esc(off.who_pays)}</p>
    <p class="note">A weekly summary comes on WhatsApp. If the offer is clearly losing money it pauses by itself.</p></div>
  <div class="card" id="otpCard"><div class="note" style="text-align:center">Enter the OTP sent to your registered phone</div>
    <div class="otp-boxes">${[0, 1, 2, 3].map((i) => `<input inputmode="numeric" maxlength="1" aria-label="OTP digit ${i + 1}" data-otp="${i}">`).join("")}</div>
    <div class="note" style="text-align:center">Demo OTP: <b>${esc(S.otp)}</b></div>
    <div id="otperr" class="neg note" style="text-align:center;min-height:18px">${esc(S.err)}</div>
    <button class="btn" data-act="approve">Approve with OTP</button></div>`;
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
    <p class="note" style="text-align:center">${off.weeks.length ? `${4 - off.weeks.length} of 4 approved weeks left` : "Runs a week of simulated customers through the offer."}</p>` : ""}
  ${w ? weekHTML(w, off) : `<div class="card empty">No results yet. Simulate a week to see what the offer really adds.</div>`}
  ${off.weeks.length > 1 ? `<div class="card weeks-list"><h4>Week by week</h4>${off.weeks.map((x) => `<div class="wk"><span>Week ${x.week}</span>
     <span>${inr(x.measurement.profit.total, true)} so far</span><span class="tag ${verdictTag(x)}">${shortVerdict(x)}</span></div>`).join("")}</div>` : ""}
  ${off.status !== "active" && off.status !== "stopped" ? `<button class="btn ghost" data-go="create">Change and re-approve</button>` : ""}
  ${off.weeks.length && canRun ? `<button class="btn ghost" data-act="stop">Stop offer</button>` : ""}`;
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
  return `<div class="card" id="weekCard"><div class="eyebrow">After ${n} week${n === 1 ? "" : "s"}</div>
    <span class="tag ${verdictTag(w)}">${cap(m.verdict)}</span>
    <div class="mini" style="grid-template-columns:1fr 1fr">
      <div><div class="v">${n0(Math.max(o.total, 0))}</div><div class="l">extra orders the offer created so far (likely ${n0(Math.max(o.low, 0))}–${n0(Math.max(o.high, 0))})</div></div>
      <div><div class="v ${cls(p.total)}">${inr(p.total, true)}</div><div class="l">your extra profit so far</div></div>
    </div>
    <div class="note">Extra profit, likely between ${inr(p.low, true)} and ${inr(p.high, true)}</div>
    ${rangeHTML(p.low, p.high, p.total)}
    ${w.brand_pack ? brandPackHTML(w.brand_pack) : ""}
    <div class="card" style="background:var(--bg);box-shadow:none;margin:10px 0 4px;padding:10px 12px">
      <div class="note"><b>Today's offer report would show ${n0(r.orders_with_offer)} orders</b> using the offer (${inr(r.sales_from_offer)} of sales). TrueLift's measurement says about ${n0(Math.max(o.total, 0))} of them would not have happened without it.</div></div>
    <details><summary>WhatsApp summary sent to the owner</summary><div class="wa">${esc(w.whatsapp)}</div></details>
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
  useBetter() { if (S.quote?.better) { S.design = { ...S.quote.better.design }; S.quote = null; render(); } },
  async toOtp() {
    const r = await api("/api/v1/offers", { restaurant_id: S.rid, design: S.design });
    S.otp = r.demo_otp; S.err = "";
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
    finally { S.busy = false; render(); refreshInside(); }
  },
  async stop() { S.offer = await api(`/api/v1/offers/${S.offer.offer_id}/decision`, { action: "stop" }); render(); refreshInside(); },
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
  const shown = Math.round(elig * 0.9), ctrl = elig - shown, none = Math.max(visits - elig, 0);
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
      <span><i style="background:#6f9fd8"></i>control group: 1 in 10 eligible, not shown (${n0(ctrl)})</span>
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

const Tour = {
  i: -1, steps: [], ev: null,
  async start() {
    showTab("demo");
    await openRestaurant(S.rid);
    try { this.ev = await once("evidence", () => api("/api/v1/evidence")); } catch (e) { this.ev = null; }
    this.steps = tourSteps();
    this.i = -1;
    $("#tour").classList.add("on");
    await this.next();
  },
  restart() { this.start(); },
  stop() { $("#tour").classList.remove("on"); spot(null); this.i = -1; },
  async next() {
    if (this.i >= this.steps.length - 1) { this.stop(); return; }
    this.i += 1;
    const s = this.steps[this.i], btn = $("#tourNext");
    btn.disabled = true; btn.textContent = "…";
    try { if (s.run) await s.run(); } catch (e) { console.warn(e); }
    $("#tourDots").innerHTML = this.steps.map((_, k) => `<i class="${k <= this.i ? "on" : ""}"></i>`).join("");
    $("#tourStep").textContent = `Step ${this.i + 1} of ${this.steps.length}`;
    $("#tourTitle").textContent = s.title;
    $("#tourText").innerHTML = s.text();
    btn.disabled = false; btn.textContent = this.i === this.steps.length - 1 ? "Finish" : "Next";
    spot(s.spot);
  },
};

function tourSteps() {
  const c = S.card;
  const q = () => S.quote?.owner, b = () => S.quote?.better;
  const lastWeek = () => S.offer?.weeks[S.offer.weeks.length - 1];
  return [
    { title: `Meet ${c.name}, ${c.locality}`, spot: "#phead",
      text: () => `This is the restaurant's partner app. It gets about <b>${n0(c.orders_per_week)} orders a week</b> at <b>${inr(c.aov)}</b> on average, and ${pct(c.regulars_share_of_orders)} of orders come from ${c.regular_customers} regulars. (Real listing; simulated customers and money.)` },
    { title: "The owner sets up today's usual offer", spot: "#ownerCard",
      run: async () => { S.design = defaultDesign(c); S.quote = null; go("create"); await requestQuote(); await wait(150); },
      text: () => q() ? `<b>${esc(q().label)}</b>. Before approving, TrueLift forecasts it: about ${n0(q().redemptions)} orders a week would use it, but <b>${pct(q().anyway_share)} of them would have come anyway</b>. Expected extra profit: <b>${inr(q().profit_change, true)}</b> a week (likely ${inr(q().profit_low, true)} to ${inr(q().profit_high, true)}). Today's report would only show the orders that used it.` : "Calculating…" },
    { title: "TrueLift suggests a better version", spot: "#betterCard",
      run: async () => { await wait(50); },
      text: () => b() ? `It compared ${S.quote.designs_compared} versions of the same discount and suggests <b>${esc(b().label)}</b>: about <b>${inr(b().profit_change, true)} a week</b>, ${inr(b().profit_change - q().profit_change, true)} more than the owner's version, because the discount goes to customers it actually brings in.` : "The owner's offer is already the best version here, so TrueLift keeps it." },
    { title: "Inside Zomato: who sees the discount", spot: "#who",
      run: async () => { if (S.quote?.better) { S.design = { ...S.quote.better.design }; S.quote = null; render(); await requestQuote(); } await wait(300); },
      text: () => q() ? `With the better version, about <b>${n0(q().eligible_visits * 0.9)}</b> of ${n0(q().menu_visits)} weekly menu visits see the discount. Regulars who'd order anyway don't get it. <b>1 in 10</b> eligible customers are held back as a control group: comparing them with the rest is how TrueLift measures what the offer really added.` : "" },
    { title: "The owner approves with an OTP", spot: "#otpCard",
      run: async () => { await ACT.toOtp(); await wait(100); },
      text: () => `Since August 2026, restaurant-funded offers start only after the owner's OTP. TrueLift stores exactly what the owner was shown (the forecast, who pays, and the 4-week approval period), so every deduction can be checked later.` },
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
        const v = Tour.ev.real_data_criteo?.results?.find((r) => r.label === "visit");
        return `In the simulated market, <b>${t.offers_that_pay} of 300</b> TrueLift offers pay for themselves, against ${bl.offers_that_pay} blanket ones. Restaurants make ${lakh(t.restaurant_profit_change)} vs ${lakh(bl.restaurant_profit_change)} extra profit a week with 40% less discount, and Zomato's commission stays about the same.${v ? ` On real randomised data (Criteo), the model's top 30% picks hold <b>${pct(v.top30_share_of_total_lift)}</b> of all the extra visits.` : ""}`; } },
    { title: "Try it yourself", spot: null,
      run: async () => { showTab("demo"); go("home"); },
      text: () => `Pick any restaurant at the top, create any offer, and run the weeks. <b>How it works</b> explains every step in plain words; <b>Money maths</b> shows every rupee.` },
  ];
}

// ---------------- how it works ----------------
async function renderHow() {
  const el = $("#how");
  if (el.dataset.done) return;
  let E = null;
  try { E = await once("evidence", () => api("/api/v1/evidence")); } catch (e) { /* page still works without numbers */ }
  const P = E?.main?.policies, v = E?.real_data_criteo?.results?.find((r) => r.label === "visit");
  const waffle = Array.from({ length: 100 }, (_, k) => `<i class="${k >= 70 ? "x" : ""}"></i>`).join("");
  el.innerHTML = `<h1>How TrueLift works</h1>
  <p>Restaurant discounts on Zomato are judged by the orders that <b>use</b> them, not the orders they <b>create</b>. Since August 2026 a restaurant-funded offer starts only after the owner approves it with an OTP, so an owner who can't see whether an offer pays will stop approving it. TrueLift shows them, before and after.</p>
  <h2>The problem in one picture</h2>
  <div class="split"><div><div class="waffle" role="img" aria-label="100 orders: 70 would have come anyway, 30 extra">${waffle}</div>
      <div class="legend"><span><i style="background:var(--series-mute)"></i>70 orders that would have come anyway</span><span><i style="background:var(--red)"></i>30 extra orders</span></div></div>
    <div><p class="p">A ₹60-off offer on ₹400 orders: <b>100 orders used it</b>. The report shows 100. But 70 would have come anyway at full price, so the restaurant gave away ₹4,200 for nothing and ends the week <b>₹210 worse off</b>.</p>
      <p class="p">₹60 off pays for itself only if at least <b>32 of every 100</b> orders using it are truly extra. Nobody measures that today. TrueLift does.</p></div></div>
  <h2>Four steps inside Zomato's existing offer flow</h2>
  <div class="steps4">
    <div class="step4"><div class="n">1</div><h4>Before approval</h4><p>Forecast the extra orders and profit, with a range, and suggest a better version of the same discount.</p><div class="where">Offer screen and OTP · <code>POST /api/quote</code></div></div>
    <div class="step4"><div class="n">2</div><h4>While it runs</h4><p>Show the discount only to customers it brings in. A random 1 in 10 eligible customers don't see it: the control group.</p><div class="where">Menu page · <code>GET /api/serve</code> · 1.5 ms</div></div>
    <div class="step4"><div class="n">3</div><h4>Who pays</h4><p>The restaurant pays for its own offer, itemised in the payout. Zomato co-funds only where its own measurement shows a gain.</p><div class="where">Payout statement</div></div>
    <div class="step4"><div class="n">4</div><h4>Every week</h4><p>Measured extra orders and profit, keep / change / stop on WhatsApp. Clear losers pause; renewal needs a new OTP.</p><div class="where">Partner app and WhatsApp · <code>GET /api/offers/{id}</code></div></div>
  </div>
  <h2>How it knows</h2>
  <div class="steps4" style="grid-template-columns:repeat(3,1fr)">
    <div class="step4"><h4>A control group</h4><p>Customers who were eligible but randomly not shown the offer show what would have happened without it. The difference is what the offer added.</p></div>
    <div class="step4"><h4>A model learned from all restaurants</h4><p>For each visitor it predicts the chance of ordering with and without the discount. That decides who sees it and gives the forecast.</p></div>
    <div class="step4"><h4>Both, combined</h4><p>A small restaurant's control group is too small alone at first, so the estimate starts from the model and shifts to the restaurant's own data as it grows, always with a range.</p></div>
  </div>
  <h2>Built for Zomato's scale</h2>
  <div class="scale">
    <div class="tile"><div class="v">3.34 lakh</div><div class="l">active restaurant partners it would serve (Q2 FY27)</div></div>
    <div class="tile"><div class="v">1.5 ms</div><div class="l">per serving decision; falls back to the owner's own rule if anything fails</div></div>
    <div class="tile"><div class="v">≈35 ms</div><div class="l">per forecast, comparing 34 versions of an offer</div></div>
    <div class="tile"><div class="v">Weekly</div><div class="l">batch measurement per offer; no change to how customers order</div></div>
  </div>
  ${P ? `<h2>Does it work?</h2><p>In a simulated market of 300 real Bengaluru listings, <b>${P.truelift.offers_that_pay} of 300</b> TrueLift offers pay for themselves against <b>${P.today_blanket.offers_that_pay}</b> blanket offers, and restaurants make ${lakh(P.truelift.restaurant_profit_change)} vs ${lakh(P.today_blanket.restaurant_profit_change)} extra profit a week.${v ? ` On real randomised data (Criteo's ad holdouts), the model's top 30% picks hold ${pct(v.top30_share_of_total_lift)} of all the extra visits.` : ""} Details on the Evidence tab.</p>` : ""}
  <h2>Words used on this site</h2>
  <div class="gloss">
    <div><b>Extra orders</b>Orders that happened only because of the offer.</div>
    <div><b>Would come anyway</b>Orders that used the discount but would have been placed at full price too.</div>
    <div><b>Control group</b>A random 1 in 10 eligible customers who don't see the offer; they pay normal prices.</div>
    <div><b>Likely range</b>An 80% range: the true value should fall inside about 4 times in 5.</div>
    <div><b>Uplift</b>How much the offer raises one customer's chance of ordering.</div>
    <div><b>Brand Pack</b>Zomato's existing reward for a restaurant's repeat customers.</div>
    <div><b>Minimum order</b>The offer applies only above a bill size, e.g. ₹60 off above ₹499.</div>
    <div><b>Qini score</b>How well a ranking finds the people an offer moves; 0 means no better than random.</div>
  </div>
  <h2>Questions people ask</h2>
  <div class="faq">
    <details><summary>Isn't this just discount targeting? Swiggy and Zomato already have segments.</summary><p>Segments decide who <i>can</i> see an offer. Nobody measures what it <i>caused</i>. In our test the simple "new customers only" segment is a strong baseline, and TrueLift is compared against it, not just against blanket offers.</p></details>
    <details><summary>Doesn't hiding the offer from 1 in 10 customers lose sales?</summary><p>Held-out customers pay normal menu prices; they are customers who would otherwise have received a discount. The holdout costs no discount money and is the only way to know what the offer added.</p></details>
    <details><summary>Can a small restaurant really be measured?</summary><p>Not from its own control group in one week. That's why the estimate starts from the model learned from all restaurants and moves to the restaurant's own data over time, always shown as a range.</p></details>
    <details><summary>Is it fair to give different customers different discounts?</summary><p>Only order history is used: orders here, orders on Zomato, weeks since the last order. Never device, payment method or anything that proxies wealth. Nobody pays more than the menu price.</p></details>
    <details><summary>Why trust a simulation?</summary><p>Because it knows the truth, it is the only way to check the whole method end to end. The results hold when customers are 30% more or less price-sensitive, and the targeting was also checked on real randomised data. The next step is a silent test on Zomato's own offer logs.</p></details>
  </div>`;
  el.dataset.done = "1";
}

// ---------------- evidence ----------------
const POLICY_NAMES = { no_offer: "No offer", today_blanket: "Today: same discount for everyone", rule_new_customers: "Rule: new customers only", truelift: "TrueLift", zomato_cofund_naive: "Unmeasured Zomato co-funding" };

async function renderEvidence() {
  const el = $("#evidence");
  if (el.dataset.done) return;
  let E;
  try { E = await once("evidence", () => api("/api/v1/evidence")); } catch (e) { el.innerHTML = `<p class="neg">${esc(e.message)}</p>`; return; }
  const M = E.main, P = M.policies, A = M.measurement;
  const keys = ["today_blanket", "rule_new_customers", "truelift", "zomato_cofund_naive"], main3 = keys.slice(0, 3);
  const row = (label, f, fmt = (v) => v, hl = false) => `<tr class="${hl ? "hl" : ""}"><td>${label}</td>${keys.map((k) => `<td>${fmt(f(P[k]))}</td>`).join("")}</tr>`;
  const tl = P.truelift, bl = P.today_blanket;
  el.innerHTML = `<h1>Does it work?</h1>
  <p>A simulated market of 300 real Bengaluru restaurants (Zomato listings) and 30,000 synthetic customers whose true response to every discount is known. The models only see order history, like Zomato would. Each policy runs for 4 weeks on identical customer visits. All rupee figures are per week across the 300 restaurants.</p>
  <div class="tiles" id="evTiles">
    <div class="tile"><div class="v">${bl.offers_that_lose} of ${bl.restaurants_with_offer}</div><div class="l">blanket offers lose the restaurant money</div></div>
    <div class="tile"><div class="v">${tl.offers_that_pay} of ${tl.restaurants_with_offer}</div><div class="l">TrueLift offers pay for themselves</div></div>
    <div class="tile"><div class="v">${lakh(bl.customer_savings)} → ${lakh(tl.customer_savings)}</div><div class="l">discount given a week, with ${lakh(tl.restaurant_profit_change)} vs ${lakh(bl.restaurant_profit_change)} extra restaurant profit</div></div>
    <div class="tile"><div class="v">${pct(A.after_2_weeks.said_keep_and_truly_positive / A.after_2_weeks.said_keep)}</div><div class="l">of TrueLift's "keep" verdicts were right after 2 weeks</div></div>
  </div>
  <div class="charts">
    <div class="chart"><h3>Profit the offers create for their own restaurants</h3><div class="s">₹ per week, all 300 restaurants; each offer vs not running it</div>${hbar(main3.map((k) => [POLICY_NAMES[k], P[k].own_offer_profit_effect, k === "truelift"]), inr)}</div>
    <div class="chart"><h3>Zomato's extra commission</h3><div class="s">₹ per week vs a market with no offers (gross commission, before delivery costs)</div>${hbar(main3.map((k) => [POLICY_NAMES[k], P[k].zomato_commission_change, k === "truelift"]), inr)}</div>
  </div>
  <h2>Policy comparison (true expected values)</h2>
  <div class="tablewrap"><table class="t"><tr><th></th>${keys.map((k) => `<th>${POLICY_NAMES[k]}</th>`).join("")}</tr>
    ${row("Offers that pay for themselves", (p) => p.offers_that_pay, (v) => v, true)}
    ${row("Offers that lose money", (p) => p.offers_that_lose)}
    ${row("Profit created by own offers (₹/week)", (p) => p.own_offer_profit_effect, (v) => inr(v, true), true)}
    ${row("Orders using a discount", (p) => p.redemptions, n0)}
    ${row("Share that would have come anyway", (p) => p.anyway_share_of_redemptions, pct)}
    ${row("Extra orders vs no offers", (p) => p.extra_orders_vs_no_offer, n0)}
    ${row("Discount given to customers (₹/week)", (p) => p.customer_savings, inr)}
    ${row("Discount per extra order", (p) => p.savings_per_extra_order, inr)}
    ${row("Average order value", (p) => p.order_value, inr)}
    ${row("Restaurant profit vs no offers (₹/week)", (p) => p.restaurant_profit_change, (v) => inr(v, true), true)}
    ${row("Zomato commission vs no offers", (p) => p.zomato_commission_change, (v) => inr(v, true))}
    ${row("Zomato contribution vs no offers (8.5% of bill − Zomato-paid discount)", (p) => p.zomato_contribution_change, (v) => inr(v, true))}
    ${row("Discount paid by Zomato", (p) => p.zomato_funded_discount, inr)}
    ${row("Loyal customers' visits going to Swiggy", (p) => p.swiggy_share_loyal, (v) => (v * 100).toFixed(1) + "%")}
  </table></div>
  <p class="note">No-offer world for reference: ${n0(P.no_offer.orders_per_week)} orders a week; loyal customers' Swiggy share ${(P.no_offer.swiggy_share_loyal * 100).toFixed(1)}%. TrueLift's figures include the cost of its 10% control group. The last column is a warning, not a feature: when Zomato pays half the discount for customers new to Zomato without measuring its own gain, it spends ${lakh(P.zomato_cofund_naive.zomato_funded_discount)} a week for about ${n0(P.zomato_cofund_naive.extra_orders_vs_no_offer - tl.extra_orders_vs_no_offer)} more orders.</p>
  ${realDataHTML(E.real_data_criteo)}
  <h2>Are TrueLift's weekly numbers right?</h2>
  <p>For every TrueLift offer we compare its estimate of extra profit with the true value. "Control group only" uses just the restaurant's 10% holdout; "model only" uses just the learned model; TrueLift combines them.</p>
  <div class="tablewrap"><table class="t"><tr><th>After</th><th>Truth inside 80% range</th><th>Avg error: control group only</th><th>Model only</th><th>TrueLift combined</th><th>"Keep" verdicts right</th></tr>
  ${Object.entries(A).map(([k, a]) => `<tr><td>${k.replace("after_", "").replace("_", " ").replace("1 weeks", "1 week")}</td><td>${pct(a.coverage_80)}</td><td>${inr(a.mae_own_holdout_only)}</td><td>${inr(a.mae_model_only)}</td><td><b>${inr(a.mae_combined)}</b></td><td>${a.said_keep ? `${a.said_keep_and_truly_positive} of ${a.said_keep}` : "–"}</td></tr>`).join("")}</table></div>
  <p class="note">Uplift ranking on the evaluation weeks: Qini ${M.uplift_quality.qini_model} (0 = random); correlation of predicted and true uplift per visit ${M.uplift_quality.corr_with_true_uplift}.</p>
  <h2>If customers are more or less price-sensitive</h2>
  <div class="tablewrap"><table class="t"><tr><th>Scenario</th><th>Blanket: offers losing money</th><th>Blanket: own-offer profit</th><th>TrueLift: offers paying</th><th>TrueLift: own-offer profit</th><th>TrueLift: Zomato commission vs no offers</th></tr>
  ${[["Less price-sensitive (−30%)", E.less_price_sensitive], ["Base case", E.main], ["More price-sensitive (+30%)", E.more_price_sensitive]].filter((s) => s[1]).map(([l, s]) => {
    const b = s.policies.today_blanket, t = s.policies.truelift;
    return `<tr><td>${l}</td><td>${b.offers_that_lose} of ${b.restaurants_with_offer}</td><td>${inr(b.own_offer_profit_effect, true)}</td><td>${t.offers_that_pay} of ${t.restaurants_with_offer}</td><td>${inr(t.own_offer_profit_effect, true)}</td><td>${inr(t.zomato_commission_change, true)}</td></tr>`; }).join("")}
  </table></div>
  <h2>What this does not prove</h2>
  <p>The market is simulated: customer types, price sensitivity and the Swiggy option are our assumptions, chosen to be plausible and then varied. It shows that TrueLift's method finds the truth when there is one to find, and how much better targeted offers do than blanket ones under those assumptions. Real numbers need Zomato's own offer logs or a silent test on live offers.</p>`;
  el.dataset.done = "1";
  bindTips(el);
}

function realDataHTML(R) {
  if (!R) return "";
  const v = R.results.find((r) => r.label === "visit"), c = R.results.find((r) => r.label === "conversion");
  return `<h2>On real data: Criteo's randomised ad holdouts</h2>
  <p>The same model, trained on ${(R.train_rows / 1e6).toFixed(0)} million users of Criteo's open incrementality tests (a random 15% of people were held out of advertising, like TrueLift's control group), ranked ${(v.test_rows / 1e6).toFixed(1)} million users it had never seen. Advertising, not food discounts: this tests the method, not Zomato's numbers.</p>
  <div class="charts">
    <div class="chart"><h3>Extra visits found, by share of people targeted</h3><div class="s">Share of all the extra visits the full campaign created</div>
      ${qiniChart(v.curve)}
      <div class="legend"><span><i class="line" style="background:var(--series)"></i>TrueLift's model</span><span><i class="line" style="background:var(--series-mute)"></i>Random targeting</span></div></div>
    <div class="chart"><h3>What it means</h3>
      <div class="row"><span class="k">Visits: held out vs shown ads</span><span class="v">${(v.rate_control * 100).toFixed(2)}% → ${(v.rate_treated * 100).toFixed(2)}%</span></div>
      <div class="row"><span class="k">Qini score, model vs random (visits)</span><span class="v">${v.qini_t_learner} vs ${v.qini_random}</span></div>
      <div class="row"><span class="k">Extra visits in the top 30% the model picks</span><span class="v">${pct(v.top30_share_of_total_lift)}</span></div>
      <div class="row"><span class="k">Qini score, model vs random (purchases, rare)</span><span class="v">${c.qini_t_learner} vs ${c.qini_random}</span></div>
      <div class="row"><span class="k">Extra purchases in the top 30%</span><span class="v">${pct(c.top30_share_of_total_lift)}</span></div>
      <p class="note">If a campaign could reach only 30% of people, the model's choice would capture ${pct(v.top30_share_of_total_lift)} of all the extra visits the full campaign creates; random choice captures about 30%.</p></div>
  </div>`;
}

function qiniChart(cu) {
  const W = 460, H = 236, L = 44, Rm = 20, T = 16, B = 46;
  const xs = cu.share_targeted, ys = [...cu.model, ...cu.random];
  const ymax = Math.max(1, ...ys), ymin = Math.min(0, ...ys);
  const x = (v) => L + v * (W - L - Rm), y = (v) => T + (1 - (v - ymin) / (ymax - ymin)) * (H - T - B);
  const path = (arr) => arr.map((v, i) => `${i ? "L" : "M"}${x(xs[i]).toFixed(1)},${y(v).toFixed(1)}`).join(" ");
  const grid = [0, 0.25, 0.5, 0.75, 1].map((g) => `<line x1="${L}" x2="${W - Rm}" y1="${y(g)}" y2="${y(g)}" stroke="#e1e0d9"></line><text x="${L - 6}" y="${y(g) + 4}" text-anchor="end">${Math.round(g * 100)}%</text>`).join("");
  const xt = [0, 0.25, 0.5, 0.75, 1].map((g) => `<text x="${x(g)}" y="${H - B + 16}" text-anchor="middle">${Math.round(g * 100)}%</text>`).join("");
  const n = xs.length - 1;
  const hits = xs.map((f, i) => `<rect x="${x(f) - (W - L - Rm) / n / 2}" y="${T}" width="${(W - L - Rm) / n}" height="${H - T - B}" fill="transparent"
     data-tip="Target ${Math.round(f * 100)}% of people: the model finds ${Math.round(cu.model[i] * 100)}% of the extra visits, random ${Math.round(cu.random[i] * 100)}%"></rect>`).join("");
  return `<svg viewBox="0 0 ${W} ${H}" width="100%" role="img" aria-label="Qini curve: model versus random">
    ${grid}${xt}<text x="${(L + W - Rm) / 2}" y="${H - 4}" text-anchor="middle">share of people targeted (highest predicted uplift first)</text>
    <path d="${path(cu.random)}" fill="none" stroke="var(--series-mute)" stroke-width="2" stroke-linejoin="round" stroke-linecap="round"></path>
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

function bindTips(root) {
  const tip = $("#tip");
  root.querySelectorAll("[data-tip]").forEach((g) => {
    g.addEventListener("mousemove", (e) => { tip.textContent = g.dataset.tip; tip.style.display = "block"; tip.style.left = Math.min(e.clientX + 12, innerWidth - 290) + "px"; tip.style.top = e.clientY + 12 + "px"; });
    g.addEventListener("mouseleave", () => { tip.style.display = "none"; });
  });
}

// ---------------- money maths ----------------
async function renderMoney() {
  const el = $("#money");
  if (el.dataset.done) return;
  const e = await once("example", () => api("/api/v1/example"));
  const f = e.per_order_full, d = e.per_order_discounted, b = e.blanket, t = e.truelift, n = e.no_offer;
  const line = (k, v, total) => `<div class="row ${total ? "total" : ""}"><span class="k">${k}</span><span class="v">${v}</span></div>`;
  el.innerHTML = `<h1>The money, step by step</h1>
  <p>The Round 1 example: a restaurant with ₹400 orders and 70 orders a week from regulars. A ₹60-off offer brings 30 new orders. Commission is 25% plus 18% GST on it (29.5% in total); food and packaging cost 37% of the order.</p>
  <div class="charts">
  <div class="calc"><h4>One ₹400 order</h4>
    ${line("Food sales", inr2(f.basket))}${line("Commission (25%)", "−" + inr2(f.commission))}${line("GST on commission (18%)", "−" + inr2(f.gst_on_commission))}${line("Food and packaging (37%)", "−" + inr2(f.food_cost))}
    ${line("<b>Restaurant keeps</b>", inr2(f.restaurant_profit), true)}${line("Zomato's gross commission", inr2(f.commission))}</div>
  <div class="calc"><h4>The same order with ₹60 off (paid by the restaurant)</h4>
    ${line("Food sales", inr2(d.basket))}${line("Discount", "−" + inr2(d.discount))}${line("Commission (25% of ₹340)", "−" + inr2(d.commission))}${line("GST on commission", "−" + inr2(d.gst_on_commission))}${line("Food and packaging", "−" + inr2(d.food_cost))}
    ${line("<b>Restaurant keeps</b>", inr2(d.restaurant_profit), true)}${line("Zomato's gross commission", inr2(d.commission))}</div>
  </div>
  <div class="calc"><h4>When does ₹60 off pay for itself?</h4>
    <p class="note">Of the orders using the offer, let <i>f</i> be the share that would not have happened without it. The restaurant gains ₹91.70 on those and loses ₹134 − ₹91.70 = ₹42.30 on every other one. It breaks even when f × ₹91.70 = (1 − f) × ₹42.30, so <b>f = 1 − 91.70 / 134 = 31.6%</b>.</p>
    ${line("10% off (₹40)", "pays only if ≥ 21% of its orders are extra")}${line("15% off (₹60)", "≥ 32%")}${line("20% off (₹80)", "≥ 42%")}${line("25% off (₹100)", "≥ 53%")}</div>
  <div class="calc"><h4>One week</h4>
    ${line("No offer: 70 × " + inr2(f.restaurant_profit), inr2(n.restaurant_profit))}
    ${line("Today, ₹60 off for everyone: 100 × " + inr2(d.restaurant_profit), inr2(b.restaurant_profit))}
    ${line("<b>Change for the restaurant</b>", `<span class="${cls(b.restaurant_change)}">${inr2(b.restaurant_change, true)}</span>`, true)}
    ${line("Zomato: 100 × " + inr2(d.commission) + " − 70 × " + inr2(f.commission), inr2(b.zomato_change, true))}
    ${line("Discount given: " + inr2(b.discount_spend) + " (of which " + inr2(b.discount_on_regulars) + " on regulars) ÷ 30 extra orders", inr2(b.discount_per_extra_order) + " per extra order")}
    <br>
    ${line("TrueLift: 70 × " + inr2(f.restaurant_profit) + " + 30 × " + inr2(d.restaurant_profit) + " − ₹650 rewards", inr2(t.restaurant_profit))}
    ${line("<b>Change for the restaurant</b>", `<span class="${cls(t.restaurant_change)}">${inr2(t.restaurant_change, true)}</span>`, true)}
    ${line("Zomato: 30 × " + inr2(d.commission), inr2(t.zomato_change, true))}
    ${line("Spend: 30 × ₹60 + ₹650 rewards = " + inr2(t.discount_spend) + " ÷ 30 extra orders", inr2(t.discount_per_extra_order) + " per extra order")}</div>
  <p class="note">The Round 1 page rounded commission + GST to 30%, which gave −₹240 and +₹2,050; the exact 29.5% gives the figures above. Zomato's gross commission is not its profit: after delivery costs, Zomato's food-delivery business earns about 5.5% of order value as adjusted EBITDA (Q2 FY27).</p>`;
  el.dataset.done = "1";
}

boot().catch((e) => { $("#screen").innerHTML = `<div class="card neg">${esc(e.message)}</div>`; });
