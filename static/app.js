// TrueLift prototype UI: the owner's partner-app screens, the "inside Zomato" panel,
// the evidence page and the money maths. Plain JS; talks to the FastAPI service.

const $ = (s) => document.querySelector(s);
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const inr = (x, sign = false) => {
  if (x === null || x === undefined || Number.isNaN(x)) return "–";
  const v = Math.round(x);
  const s = Math.abs(v).toLocaleString("en-IN");
  return (v < 0 ? "−₹" : sign && v > 0 ? "+₹" : "₹") + s;
};
// exact rupees with paise when needed (₹91.70), for per-order maths
const inr2 = (x, sign = false) => {
  const v = Math.round(x * 100) / 100;
  const s = Math.abs(v).toLocaleString("en-IN", { minimumFractionDigits: Number.isInteger(v) ? 0 : 2, maximumFractionDigits: 2 });
  return (v < 0 ? "−₹" : sign && v > 0 ? "+₹" : "₹") + s;
};
const n1 = (x) => (x === null || x === undefined ? "–" : (Math.round(x * 10) / 10).toLocaleString("en-IN"));
const pct = (x) => (x === null || x === undefined ? "–" : Math.round(x * 100) + "%");
const cls = (x) => (x > 0 ? "pos" : x < 0 ? "neg" : "");

// On GitHub Pages there is no server: STATIC points to precomputed answers from the real service
// (scripts/export_static.py), and offers are replayed week by week in the browser.
const STATIC = window.TRUELIFT_STATIC || null;
const LOCAL = { offers: {}, next: 1 };
const dkey = (d) => `${Math.round(d.discount)}-${Math.round(d.min_order)}-${d.audience}-${d.offpeak_only ? 1 : 0}-${Math.round(d.reward)}`;

async function sget(file) {
  const r = await fetch(STATIC + file);
  if (!r.ok) throw new Error("This combination isn't in the static demo; the live version answers any design.");
  return r.json();
}

function localView(id) {
  const o = LOCAL.offers[id];
  if (!o) throw new Error("no such offer");
  return { ...o.full, offer_id: +id, status: o.status, consent: o.status === "awaiting_otp" ? null : o.full.consent,
           weeks: o.full.weeks.slice(0, o.shown) };
}

async function staticApi(path, body) {
  let m;
  if (path === "/api/restaurants") return sget("restaurants.json");
  if ((m = path.match(/^\/api\/restaurants\/(\d+)$/))) return sget(`${m[1]}/card.json`);
  if (path === "/api/quote") return (await sget(`${body.restaurant_id}/${dkey(body.design)}.json`)).quote;
  if (path === "/api/customers") return (await sget(`${body.restaurant_id}/${dkey(body.design)}.json`)).customers;
  if (path === "/api/offers") {
    const f = await sget(`${body.restaurant_id}/${dkey(body.design)}.json`);
    if (!f.offer) throw new Error("Nothing to approve: this design has no discount.");
    const id = LOCAL.next++;
    LOCAL.offers[id] = { full: f.offer, otp: String(1000 + Math.floor(Math.random() * 9000)), shown: 0, status: "awaiting_otp" };
    return { offer_id: id, demo_otp: LOCAL.offers[id].otp };
  }
  if ((m = path.match(/^\/api\/offers\/(\d+)$/))) return localView(m[1]);
  if ((m = path.match(/^\/api\/offers\/(\d+)\/approve$/))) {
    const o = LOCAL.offers[m[1]];
    if (String(body.otp).trim() !== o.otp) throw new Error("wrong OTP");
    o.status = "active";
    return localView(m[1]);
  }
  if ((m = path.match(/^\/api\/offers\/(\d+)\/run_week$/))) {
    const o = LOCAL.offers[m[1]];
    o.shown = Math.min(o.shown + 1, o.full.weeks.length);
    if (o.shown >= o.full.weeks.length) o.status = o.full.status === "active" ? "consent_expired" : o.full.status;
    return localView(m[1]);
  }
  if ((m = path.match(/^\/api\/offers\/(\d+)\/decision$/))) { LOCAL.offers[m[1]].status = "stopped"; return localView(m[1]); }
  if (path === "/api/calls") return sget("calls.json");
  if (path === "/api/evidence") return sget("evidence.json");
  if (path === "/api/example") return sget("example.json");
  if (path === "/api/reset") { LOCAL.offers = {}; return { ok: true }; }
  throw new Error("not available in the static demo: " + path);
}

async function api(path, body) {
  if (STATIC) return staticApi(path, body);
  const opt = body === undefined ? {} : { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) };
  const r = await fetch(path, opt);
  const j = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(j.detail ? (typeof j.detail === "string" ? j.detail : JSON.stringify(j.detail)) : r.statusText);
  return j;
}

const S = { rid: null, card: null, design: null, quote: null, offer: null, otp: null, screen: "home", busy: false };
const AUDIENCES = [["all", "Everyone"], ["new_to_restaurant", "New to you"], ["lapsed", "Stopped ordering"], ["targeted", "Let TrueLift choose"]];

function defaultDesign(aov) {
  return { discount: Math.max(20, Math.round((aov * 0.15) / 10) * 10), min_order: 0, audience: "all", offpeak_only: false, reward: 0, zomato_share: 0 };
}

// ---------------- boot ----------------
async function boot() {
  document.querySelectorAll("nav button").forEach((b) => b.addEventListener("click", () => showTab(b.dataset.tab)));
  $("#clock").textContent = new Date().toLocaleDateString("en-IN", { day: "numeric", month: "short" });
  $("#screen").innerHTML = `<p class="muted">Loading the market (a few seconds)…</p>`;
  const data = await api("/api/restaurants");
  const sel = $("#rest");
  const list = data.restaurants.filter((r) => r.menu_visits_per_week > 0).sort((a, b) => a.locality.localeCompare(b.locality) || a.name.localeCompare(b.name));
  sel.innerHTML = list.map((r) => `<option value="${r.restaurant_id}">${esc(r.name)} · ${esc(r.locality)}</option>`).join("");
  sel.value = data.demo_restaurant;
  sel.addEventListener("change", () => openRestaurant(+sel.value));
  await openRestaurant(data.demo_restaurant);
}

function showTab(t) {
  document.querySelectorAll("nav button").forEach((b) => b.classList.toggle("on", b.dataset.tab === t));
  document.querySelectorAll(".tab").forEach((s) => s.classList.toggle("on", s.id === "tab-" + t));
  $(".pick").style.visibility = t === "demo" ? "visible" : "hidden";
  if (t === "evidence") renderEvidence();
  if (t === "money") renderMoney();
}

async function openRestaurant(rid) {
  await api("/api/reset", {});
  S.rid = rid; S.offer = null; S.quote = null;
  S.card = await api(`/api/restaurants/${rid}`);
  S.design = defaultDesign(S.card.aov);
  go("home");
  refreshInside();
}

function go(screen) { S.screen = screen; render(); }

function render() {
  const el = $("#screen");
  el.innerHTML = { home: homeHTML, create: createHTML, otp: otpHTML, live: liveHTML }[S.screen]();
  el.scrollTop = 0;
  bind();
}

// ---------------- screens ----------------
function headHTML() {
  const c = S.card;
  return `<div class="rhead"><h1>${esc(c.name)}</h1><div class="sub">${esc(c.locality)} · ${esc(c.cuisines)} · ★ ${c.rating} · <span class="tag">simulated data</span></div></div>`;
}

function homeHTML() {
  const c = S.card;
  const off = S.offer;
  return `${headHTML()}
  <div class="stats">
    <div class="stat"><div class="v">${n1(c.orders_per_week)}</div><div class="l">orders a week</div></div>
    <div class="stat"><div class="v">${inr(c.aov)}</div><div class="l">average order</div></div>
    <div class="stat"><div class="v">${c.regular_customers}</div><div class="l">regulars (3+ orders a month)</div></div>
    <div class="stat"><div class="v">${pct(c.regulars_share_of_orders)}</div><div class="l">of orders come from regulars</div></div>
  </div>
  ${off ? `<div class="card"><h4>Your offer</h4><div>${esc(off.label)}</div><div class="row"><span class="k">Status</span><span class="v">${statusText(off.status)}</span></div><button class="btn small ghost" data-go="live">Open</button></div>` : ""}
  <div class="card"><h4>Discounts, measured</h4><p class="note">Before you approve an offer, TrueLift forecasts the extra orders and profit it will bring. While it runs, 1 in 10 eligible customers don't see it, so you see what the offer really added.</p></div>
  <button class="btn" data-go="create">Create an offer</button>`;
}

function statusText(s) {
  return { awaiting_otp: "Waiting for your OTP", active: "Running", paused: "Paused: it was losing money", stopped: "Stopped", consent_expired: "Approval period over: renew with a new OTP" }[s] || s;
}

function createHTML() {
  const d = S.design, aov = S.card.aov;
  const depths = [...new Set([0.1, 0.15, 0.2, 0.25].map((f) => Math.max(20, Math.round((aov * f) / 10) * 10)))];
  const mov = Math.ceil((aov * 1.15) / 50) * 50 - 1;
  const rw = Math.max(5, Math.round((aov * 0.05) / 5) * 5);
  const chip = (field, val, label) => `<button class="chip ${d[field] === val ? "on" : ""}" data-set="${field}" data-val='${JSON.stringify(val)}'>${label}</button>`;
  return `<button class="back" data-go="home">← Back</button>${headHTML()}
  <div class="field"><label>Discount</label><div class="chips">${depths.map((v) => chip("discount", v, "₹" + v + " off")).join("")}</div></div>
  <div class="field"><label>Minimum order</label><div class="chips">${chip("min_order", 0, "None")}${chip("min_order", mov, "Above ₹" + mov)}</div></div>
  <div class="field"><label>Who sees it</label><div class="chips">${AUDIENCES.map(([v, l]) => chip("audience", v, l)).join("")}</div></div>
  <div class="field"><label>When</label><div class="chips">${chip("offpeak_only", false, "All day")}${chip("offpeak_only", true, "3–6 pm only")}</div></div>
  <div class="field"><label>Reward regulars instead (Brand Pack)</label><div class="chips">${chip("reward", 0, "No")}${chip("reward", rw, "₹" + rw + " off per order for regulars")}</div></div>
  <div id="forecast"><p class="muted">Calculating forecast…</p></div>
  ${d.discount > 0 ? `<button class="btn" data-act="toOtp">Continue to approve</button>` :
    `<p class="note">No discount to approve. Brand Pack rewards for regulars are set up in Zomato's Brand Packs screen.</p>`}`;
}

function forecastHTML(q) {
  if (!q) return "";
  const o = q.owner, b = q.better;
  const block = (x) => `
    <div class="row"><span class="k">Orders using the offer</span><span class="v">${n1(x.redemptions)}</span></div>
    <div class="row"><span class="k">Extra orders it creates</span><span class="v">${n1(x.extra_orders)}</span></div>
    <div class="row"><span class="k">Orders that would come anyway</span><span class="v">${x.anyway_share === null ? "–" : pct(x.anyway_share)}</span></div>
    <div class="row"><span class="k">Your extra profit</span><span class="v ${cls(x.profit_change)}">${inr(x.profit_change, true)}</span></div>
    <div class="row"><span class="k">Likely range</span><span class="v">${inr(x.profit_low, true)} to ${inr(x.profit_high, true)}</span></div>
    <div class="row"><span class="k">Discount you give per extra order</span><span class="v">${x.discount_per_extra_order ? inr(x.discount_per_extra_order) : "–"}</span></div>
    <div class="row"><span class="k">Zomato's extra commission</span><span class="v">${inr(x.zomato_commission_change, true)}</span></div>`;
  return `<div class="card ${o.profit_change < 0 ? "warn" : ""}"><h4>Forecast for one week</h4>${block(o)}
      <p class="note">${o.profit_change < 0 ? "This offer is likely to cost you more than it brings in, mostly because regular customers would get the discount on orders they place anyway." : "Forecast from customers who visited your menu in the last two weeks."}</p></div>
    ${b ? `<div class="card better"><h4>Better version</h4><div><b>${esc(b.label)}</b></div>${block(b)}
      <button class="btn small" data-act="useBetter">Use this version</button></div>` : `<p class="note">This is already the best of the ${q.designs_compared} versions compared (who sees it, minimum order, time, Brand Pack). The discount size is yours to choose.</p>`}`;
}

function otpHTML() {
  const off = S.offer, q = off.quote;
  return `<button class="back" data-go="create">← Change offer</button>${headHTML()}
  <div class="card"><h4>Approve this offer</h4>
    <div><b>${esc(off.label)}</b></div>
    <div class="row"><span class="k">Expected extra orders a week</span><span class="v">${n1(q.extra_orders)}</span></div>
    <div class="row"><span class="k">Expected extra profit a week</span><span class="v ${cls(q.profit_change)}">${inr(q.profit_low, true)} to ${inr(q.profit_high, true)}</span></div>
    <div class="row"><span class="k">Runs for</span><span class="v">4 weeks, then needs your approval again</span></div>
    <p class="note">${esc(off.who_pays)}</p>
    <p class="note">You will get a summary on WhatsApp every week. If the offer is clearly losing money it pauses automatically.</p>
  </div>
  <label class="note" for="otp">Enter the OTP sent to your registered phone</label>
  <input id="otp" class="otp" inputmode="numeric" maxlength="4" autocomplete="one-time-code">
  <p class="note">Demo OTP: <b>${esc(S.otp)}</b></p>
  <div id="otperr" class="neg note"></div>
  <button class="btn" data-act="approve">Approve with OTP</button>`;
}

function liveHTML() {
  const off = S.offer;
  const weeks = [...off.weeks].reverse();
  const canRun = off.status === "active";
  return `<button class="back" data-go="home">← Home</button>${headHTML()}
  <div class="card"><h4>${esc(off.label)}</h4>
    <div class="row"><span class="k">Status</span><span class="v">${statusText(off.status)}</span></div>
    <div class="row"><span class="k">Approved</span><span class="v">${esc(off.consent?.approved_at || "")} by OTP</span></div>
    <div class="row"><span class="k">Forecast at approval</span><span class="v">${inr(off.quote.profit_low, true)} to ${inr(off.quote.profit_high, true)} a week</span></div>
  </div>
  ${canRun ? `<button class="btn" data-act="runWeek" ${S.busy ? "disabled" : ""}>${S.busy ? "Running…" : `Simulate week ${off.weeks.length + 1}`}</button>` : ""}
  ${off.status !== "active" && off.status !== "stopped" ? `<button class="btn ghost" data-go="create">Change and re-approve</button>` : ""}
  ${weeks.map(weekHTML).join("")}
  ${off.weeks.length && canRun ? `<button class="btn small ghost" data-act="stop">Stop offer</button>` : ""}`;
}

function weekHTML(w) {
  const m = w.measurement, p = m.profit, o = m.orders, r = m.report_today, pay = w.payout;
  const verdictTag = m.verdict.startsWith("making") ? "good" : m.verdict.startsWith("losing") ? "bad" : "";
  return `<div class="card"><h4>Week ${w.week} <span class="tag ${verdictTag}">${esc(m.verdict)}</span></h4>
    <div class="vs">
      <div><div class="h">Today's offer report would say</div><div class="big">${r.orders_with_offer}</div><div class="note">orders used the offer, ${inr(r.sales_from_offer)} sales</div></div>
      <div><div class="h">TrueLift measured (so far)</div><div class="big">${n1(Math.max(o.total, 0))}</div><div class="note">extra orders; profit ${inr(p.total, true)}</div></div>
    </div>
    <div class="note" style="margin-top:8px">Extra profit, likely range: ${inr(p.low, true)} to ${inr(p.high, true)}</div>
    ${rangeHTML(p.low, p.high, p.total)}
    <details><summary class="note">WhatsApp summary</summary><div class="wa">${esc(w.whatsapp)}</div></details>
    <details><summary class="note">Itemised payout for the week</summary>
      <div class="row"><span class="k">Orders</span><span class="v">${pay.orders}</span></div>
      <div class="row"><span class="k">Food sales</span><span class="v">${inr(pay.gross_sales)}</span></div>
      <div class="row"><span class="k">Discount paid by you</span><span class="v">−${inr(pay.discount_paid_by_you)}</span></div>
      <div class="row"><span class="k">Brand Pack rewards paid by you</span><span class="v">−${inr(pay.brand_pack_rewards_paid_by_you)}</span></div>
      <div class="row"><span class="k">Discount paid by Zomato</span><span class="v">${inr(pay.discount_paid_by_zomato)}</span></div>
      <div class="row"><span class="k">Commission (25%)</span><span class="v">−${inr(pay.commission_25pct)}</span></div>
      <div class="row"><span class="k">GST on commission (18%)</span><span class="v">−${inr(pay.gst_on_commission_18pct)}</span></div>
      <div class="row"><span class="k"><b>Net payout</b></span><span class="v">${inr(pay.net_payout)}</span></div>
    </details></div>`;
}

function rangeHTML(lo, hi, mid, truth) {
  const vals = [lo, hi, mid, 0].concat(truth === undefined ? [] : [truth]);
  const a = Math.min(...vals), b = Math.max(...vals);
  const pad = (b - a) * 0.1 || 1;
  const x = (v) => ((v - (a - pad)) / (b - a + 2 * pad)) * 100;
  return `<div class="range" aria-hidden="true">
    <div class="bar" style="left:${x(lo)}%;width:${x(hi) - x(lo)}%"></div>
    <div class="zero" style="left:${x(0)}%" title="₹0"></div>
    <div class="mid" style="left:${x(mid)}%"></div>
    ${truth === undefined ? "" : `<div class="truth" style="left:${x(truth)}%" title="true value"></div>`}
  </div>`;
}

// ---------------- actions ----------------
function bind() {
  document.querySelectorAll("[data-go]").forEach((b) => b.addEventListener("click", () => go(b.dataset.go)));
  document.querySelectorAll("[data-set]").forEach((b) => b.addEventListener("click", () => {
    S.design[b.dataset.set] = JSON.parse(b.dataset.val);
    render();
  }));
  document.querySelectorAll("[data-act]").forEach((b) => b.addEventListener("click", () => ACT[b.dataset.act]()));
  if (S.screen === "create") requestQuote();
}

let quoteTimer = null, quoteSeq = 0;
function requestQuote() {
  clearTimeout(quoteTimer);
  quoteTimer = setTimeout(async () => {
    const seq = ++quoteSeq;
    try {
      const q = await api("/api/quote", { restaurant_id: S.rid, design: S.design });
      if (seq !== quoteSeq || S.screen !== "create") return;
      S.quote = q;
      $("#forecast").innerHTML = forecastHTML(q);
      const ub = document.querySelector('[data-act="useBetter"]');
      if (ub) ub.addEventListener("click", ACT.useBetter);
      refreshInside();
    } catch (e) { $("#forecast").innerHTML = `<p class="neg">${esc(e.message)}</p>`; }
  }, 150);
}

const ACT = {
  useBetter() { if (S.quote?.better) { S.design = { ...S.quote.better.design }; render(); } },
  async toOtp() {
      const r = await api("/api/offers", { restaurant_id: S.rid, design: S.design });
    S.otp = r.demo_otp;
    S.offer = await api(`/api/offers/${r.offer_id}`);
    go("otp");
  },
  async approve() {
    try {
      S.offer = await api(`/api/offers/${S.offer.offer_id}/approve`, { otp: $("#otp").value });
      go("live"); refreshInside();
    } catch (e) { $("#otperr").textContent = e.message; }
  },
  async runWeek() {
    S.busy = true; render();
    try { S.offer = await api(`/api/offers/${S.offer.offer_id}/run_week`, {}); }
    finally { S.busy = false; render(); refreshInside(); }
  },
  async stop() { S.offer = await api(`/api/offers/${S.offer.offer_id}/decision`, { action: "stop" }); render(); },
};

// ---------------- inside Zomato panel ----------------
async function refreshInside() {
  try {
    const c = await api("/api/customers", { restaurant_id: S.rid, design: S.offer?.design || S.design });
    $("#who").innerHTML = `<h3>${S.offer && S.offer.status === "active" ? "Who sees the discount" : "Who would see it"}: ${esc(c.label)}</h3>
      <p class="note">The serving hook decides each time a customer opens this menu. Regulars get the Brand Pack reward (if on) instead of a discount they don't need.</p>
      <div class="who">${c.customers.map(custHTML).join("")}</div>`;
  } catch (e) { $("#who").innerHTML = `<p class="neg">${esc(e.message)}</p>`; }
  renderTruth();
  const calls = await api("/api/calls");
  $("#calls").innerHTML = `<h3>${STATIC ? "Service response times (measured when this demo was built)" : "Hook calls (latest first)"}</h3><div class="calls">${calls.calls.map((c) =>
    `${esc(c.hook)} · ${c.ms} ms${c.customer !== undefined ? ` · customer ${c.customer} · ${c.show ? "show" : "don't show"}` : ""}`).join("<br>") || "No calls yet."}</div>`;
}

function custHTML(c) {
  const d = c.decision;
  const what = d.control_group ? `<span class="tag">control group: no discount</span>` :
    d.show_offer ? `<span class="tag good">sees the discount</span>` : `<span class="tag">no discount</span>`;
  return `<div class="cust"><div class="g">Customer ${c.customer_id} · ${esc(c.group)}</div>
    <div class="note">${c.orders_here_4w} orders here in 4 weeks · ${c.zomato_orders_per_week} Zomato orders a week · ${pct(c.share_of_orders_with_discount)} of orders used a discount</div>
    <div class="d">${what}${d.brand_pack_reward ? ` <span class="tag">₹${d.brand_pack_reward} Brand Pack</span>` : ""}</div>
    <div class="note">Chance of ordering here: ${pct(d.p_order_without)} without, ${pct(d.p_order_with)} with the discount. ${esc(d.reason.charAt(0).toUpperCase() + d.reason.slice(1))}.</div></div>`;
}

function renderTruth() {
  const off = S.offer;
  if (!off || !off.weeks.length) { $("#truth").innerHTML = ""; return; }
  const rows = off.weeks.map((w) => {
    const p = w.measurement.profit, t = w.simulator_truth;
    const inside = t.extra_profit >= p.low && t.extra_profit <= p.high;
    return `<tr><td>Week ${w.week}</td><td>${w.measurement.report_today.orders_with_offer}</td><td>${n1(t.extra_orders)}</td><td>${n1(w.measurement.orders.total)}</td>
      <td>${inr(t.extra_profit, true)}</td><td>${inr(p.total, true)}</td><td>${inr(p.low, true)} to ${inr(p.high, true)}</td><td>${inside ? "yes" : "no"}</td><td>${pct(p.weight_on_own_data)}</td></tr>`;
  }).join("");
  $("#truth").innerHTML = `<h3>Only in the simulation: estimate vs the true effect (cumulative)</h3>
    <table class="t"><tr><th>Up to</th><th>Report: orders used offer</th><th>True extra orders</th><th>TrueLift estimate</th><th>True extra profit</th><th>TrueLift estimate</th><th>80% range</th><th>Truth inside?</th><th>Weight on own control group</th></tr>${rows}</table>
    <p class="note">Early on the estimate leans on the model learned from all restaurants; as this restaurant's own control group grows, it gets more weight.</p>`;
}

// ---------------- evidence page ----------------
const POLICY_NAMES = { no_offer: "No offer", today_blanket: "Today: same discount for everyone", rule_new_customers: "Rule: new customers only", truelift: "TrueLift", zomato_cofund_naive: "Unmeasured Zomato co-funding" };
const lakh = (x) => (x === null || x === undefined ? "–" : (x < 0 ? "−" : "") + "₹" + (Math.abs(x) / 1e5).toFixed(2) + " lakh");

async function renderEvidence() {
  const el = $("#evidence");
  if (el.dataset.done) return;
  let E;
  try { E = await api("/api/evidence"); } catch (e) { el.innerHTML = `<p class="neg">${esc(e.message)}</p>`; return; }
  const M = E.main, P = M.policies, A = M.measurement;
  const keys = ["today_blanket", "rule_new_customers", "truelift", "zomato_cofund_naive"];
  const main3 = keys.slice(0, 3);
  const row = (label, f, fmt = (v) => v) => `<tr><td>${label}</td>${keys.map((k) => `<td>${fmt(f(P[k]))}</td>`).join("")}</tr>`;
  const tl = P.truelift, bl = P.today_blanket;
  el.innerHTML = `<h1>Does it work? Evidence from the simulated market</h1>
  <p>300 real Bengaluru restaurants (Zomato listings), 30,000 synthetic customers whose true response to every discount is known. The models only see order history, like Zomato would. Each policy runs for 4 weeks on identical customer visits. All rupee figures are per week across the 300 restaurants.</p>
  <div class="tiles">
    <div class="tile"><div class="v">${bl.offers_that_lose} of ${bl.restaurants_with_offer}</div><div class="l">blanket offers lose the restaurant money</div></div>
    <div class="tile"><div class="v">${tl.offers_that_pay} of ${tl.restaurants_with_offer}</div><div class="l">TrueLift offers pay for themselves</div></div>
    <div class="tile"><div class="v">${lakh(bl.customer_savings)} → ${lakh(tl.customer_savings)}</div><div class="l">discount given a week, blanket → TrueLift, with ${lakh(tl.restaurant_profit_change)} vs ${lakh(bl.restaurant_profit_change)} extra restaurant profit</div></div>
    <div class="tile"><div class="v">${pct(A.after_2_weeks.said_keep_and_truly_positive / A.after_2_weeks.said_keep)}</div><div class="l">of TrueLift's "keep" verdicts were right after 2 weeks (${A.after_2_weeks.said_keep_and_truly_positive} of ${A.after_2_weeks.said_keep})</div></div>
  </div>
  <div class="charts">
    <div class="chart"><h3>Profit the offers create for their own restaurants</h3><div class="s">₹ per week, all 300 restaurants; each offer vs not running it</div>${hbar(main3.map((k) => [POLICY_NAMES[k], P[k].own_offer_profit_effect, k === "truelift"]), inr)}</div>
    <div class="chart"><h3>Zomato's extra commission</h3><div class="s">₹ per week vs a market with no offers (gross commission, before delivery costs)</div>${hbar(main3.map((k) => [POLICY_NAMES[k], P[k].zomato_commission_change, k === "truelift"]), inr)}</div>
  </div>
  <h2>Policy comparison (true expected values)</h2>
  <table class="t"><tr><th></th>${keys.map((k) => `<th>${POLICY_NAMES[k]}</th>`).join("")}</tr>
    ${row("Restaurants running an offer", (p) => p.restaurants_with_offer)}
    ${row("Offers that pay for themselves", (p) => p.offers_that_pay)}
    ${row("Offers that lose money", (p) => p.offers_that_lose)}
    ${row("Profit created by own offers (₹/week)", (p) => p.own_offer_profit_effect, (v) => inr(v, true))}
    ${row("Orders using a discount", (p) => p.redemptions, (v) => v.toLocaleString("en-IN"))}
    ${row("Share that would have come anyway", (p) => p.anyway_share_of_redemptions, pct)}
    ${row("Extra orders vs no offers", (p) => p.extra_orders_vs_no_offer, (v) => v.toLocaleString("en-IN"))}
    ${row("Customer savings (₹/week)", (p) => p.customer_savings, inr)}
    ${row("Discount per extra order", (p) => p.savings_per_extra_order, inr)}
    ${row("Average order value", (p) => p.order_value, inr)}
    ${row("Restaurant profit vs no offers (₹/week)", (p) => p.restaurant_profit_change, (v) => inr(v, true))}
    ${row("Zomato commission vs no offers", (p) => p.zomato_commission_change, (v) => inr(v, true))}
    ${row("Zomato contribution vs no offers (8.5% of bill − Zomato-paid discount)", (p) => p.zomato_contribution_change, (v) => inr(v, true))}
    ${row("Discount paid by Zomato", (p) => p.zomato_funded_discount, inr)}
    ${row("Share of loyal customers' occasions going to Swiggy", (p) => p.swiggy_share_loyal, (v) => (v * 100).toFixed(1) + "%")}
  </table>
  <p class="note">No-offer world for reference: ${P.no_offer.orders_per_week.toLocaleString("en-IN")} orders a week; loyal customers' Swiggy share ${(P.no_offer.swiggy_share_loyal * 100).toFixed(1)}%. TrueLift's figures include the cost of its 10% control group. The last column is a warning, not a feature: when Zomato pays half the discount for customers new to Zomato without measuring its own gain, it spends ${lakh(P.zomato_cofund_naive.zomato_funded_discount)} a week for about ${P.zomato_cofund_naive.extra_orders_vs_no_offer - tl.extra_orders_vs_no_offer} more orders.</p>
  ${realDataHTML(E.real_data_criteo)}
  <h2>Are TrueLift's weekly numbers right?</h2>
  <p>For every TrueLift offer we compare its estimate of extra profit with the true value. "Own control group only" uses just the restaurant's 10% holdout; "model only" uses just the learned model; TrueLift combines them.</p>
  <table class="t"><tr><th>After</th><th>Offers</th><th>Truth inside 80% range (profit)</th><th>Truth inside 80% range (orders)</th><th>Avg error: own control group only</th><th>Model only</th><th>TrueLift combined</th><th>Right sign</th></tr>
  ${Object.entries(A).map(([k, a]) => `<tr><td>${k.replace("after_", "").replace("_", " ").replace("1 weeks", "1 week")}</td><td>${a.offers}</td><td>${pct(a.coverage_80)}</td><td>${pct(a.coverage_80_orders)}</td><td>${inr(a.mae_own_holdout_only)}</td><td>${inr(a.mae_model_only)}</td><td>${inr(a.mae_combined)}</td><td>${pct(a.verdict_right_sign)}</td></tr>`).join("")}</table>
  <p class="note">Uplift ranking quality on the evaluation weeks: Qini ${M.uplift_quality.qini_model} (0 = random); correlation of predicted and true uplift per visit ${M.uplift_quality.corr_with_true_uplift}.</p>
  <h2>If customers are more or less price-sensitive</h2>
  <table class="t"><tr><th>Scenario</th><th>Blanket: offers losing money</th><th>Blanket: own-offer profit</th><th>TrueLift: offers paying</th><th>TrueLift: own-offer profit</th><th>TrueLift: Zomato commission vs no offers</th></tr>
  ${[["Less price-sensitive (−30%)", E.less_price_sensitive], ["Base case", E.main], ["More price-sensitive (+30%)", E.more_price_sensitive]].filter((x) => x[1]).map(([l, s]) => {
    const b = s.policies.today_blanket, t = s.policies.truelift;
    return `<tr><td>${l}</td><td>${b.offers_that_lose} of ${b.restaurants_with_offer}</td><td>${inr(b.own_offer_profit_effect, true)}</td><td>${t.offers_that_pay} of ${t.restaurants_with_offer}</td><td>${inr(t.own_offer_profit_effect, true)}</td><td>${inr(t.zomato_commission_change, true)}</td></tr>`; }).join("")}
  </table>
  <h2>What this does not prove</h2>
  <p>The market is simulated: customer types, price sensitivity and the Swiggy option are our assumptions, chosen to be plausible and then varied. The point is that TrueLift's method finds the truth when there is one to find, and how much better targeted offers do than blanket ones under those assumptions. Real numbers need Zomato's own offer logs or a silent test on live offers.</p>`;
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
      <div class="legend"><span><i style="background:var(--series)"></i>TrueLift's model</span><span><i style="background:var(--series-mute)"></i>Random targeting</span></div></div>
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
  // two series on one axis: model and random line; legend below, direct labels at the right end
  const W = 460, H = 236, L = 44, Rm = 20, T = 16, B = 46;
  const xs = cu.share_targeted, ys = [...cu.model, ...cu.random];
  const ymax = Math.max(1, ...ys), ymin = Math.min(0, ...ys);
  const x = (v) => L + v * (W - L - Rm), y = (v) => T + (1 - (v - ymin) / (ymax - ymin)) * (H - T - B);
  const path = (arr) => arr.map((v, i) => `${i ? "L" : "M"}${x(xs[i]).toFixed(1)},${y(v).toFixed(1)}`).join(" ");
  const grid = [0, 0.25, 0.5, 0.75, 1].map((g) => `<line x1="${L}" x2="${W - Rm}" y1="${y(g)}" y2="${y(g)}" stroke="#e1e0d9"></line><text x="${L - 6}" y="${y(g) + 4}" text-anchor="end">${Math.round(g * 100)}%</text>`).join("");
  const xt = [0, 0.25, 0.5, 0.75, 1].map((g) => `<text x="${x(g)}" y="${H - B + 16}" text-anchor="middle">${Math.round(g * 100)}%</text>`).join("");
  const n = xs.length - 1;
  const hits = xs.map((f, i) => `<rect class="hit" x="${x(f) - (W - L - Rm) / n / 2}" y="${T}" width="${(W - L - Rm) / n}" height="${H - T - B}" fill="transparent"
     data-tip="Target ${Math.round(f * 100)}% of people: model finds ${Math.round(cu.model[i] * 100)}% of the extra visits, random ${Math.round(cu.random[i] * 100)}%"></rect>`).join("");
  return `<svg viewBox="0 0 ${W} ${H}" width="100%" role="img" aria-label="Qini curve">
    ${grid}${xt}<text x="${(L + W - Rm) / 2}" y="${H - 4}" text-anchor="middle">share of people targeted (highest predicted uplift first)</text>
    <path d="${path(cu.random)}" fill="none" stroke="var(--series-mute)" stroke-width="2" stroke-linejoin="round" stroke-linecap="round"></path>
    <path d="${path(cu.model)}" fill="none" stroke="var(--series)" stroke-width="2" stroke-linejoin="round" stroke-linecap="round"></path>
    <text class="lbl" x="${x(xs[Math.round(n * 0.3)]) + 6}" y="${y(cu.model[Math.round(n * 0.3)]) - 10}">Model</text>
    <text x="${x(xs[Math.round(n * 0.7)]) + 8}" y="${y(cu.random[Math.round(n * 0.7)]) + 16}">Random</text>
    ${hits}</svg>`;
}

function hbar(items, fmt) {
  // items: [label, value, highlight]; single series, zero baseline, value label at the bar tip
  const W = 460, rowH = 34, left = 200, right = 70, H = items.length * rowH + 10;
  const vals = items.map((i) => i[1]);
  const lo = Math.min(0, ...vals), hi = Math.max(0, ...vals);
  const x = (v) => left + ((v - lo) / (hi - lo || 1)) * (W - left - right);
  const bars = items.map(([label, v, hl], i) => {
    const y = 8 + i * rowH, x0 = x(0), x1 = x(v), w = Math.max(Math.abs(x1 - x0), 1);
    const bx = Math.min(x0, x1), r = Math.min(4, w / 2);
    const path = v >= 0
      ? `M${bx},${y} h${w - r} a${r},${r} 0 0 1 ${r},${r} v${18 - 2 * r} a${r},${r} 0 0 1 -${r},${r} h-${w - r} z`
      : `M${bx + w},${y} h-${w - r} a${r},${r} 0 0 0 -${r},${r} v${18 - 2 * r} a${r},${r} 0 0 0 ${r},${r} h${w - r} z`;
    return `<g class="hit" data-tip="${esc(label)}: ${esc(fmt(v))}">
      <rect x="0" y="${y - 6}" width="${W}" height="${rowH}" fill="transparent"></rect>
      <text x="${left - 8}" y="${y + 13}" text-anchor="end">${esc(label)}</text>
      <path d="${path}" fill="${hl ? "var(--series)" : "var(--series-mute)"}"></path>
      <text class="lbl" x="${v >= 0 ? x1 + 6 : x1 - 6}" y="${y + 13}" text-anchor="${v >= 0 ? "start" : "end"}">${esc(fmt(v))}</text></g>`;
  }).join("");
  return `<svg viewBox="0 0 ${W} ${H}" width="100%" role="img"><line x1="${x(0)}" x2="${x(0)}" y1="0" y2="${H}" stroke="#c3c2b7"></line>${bars}</svg>`;
}

function bindTips(root) {
  const tip = $("#tip");
  root.querySelectorAll("[data-tip]").forEach((g) => {
    g.addEventListener("mousemove", (e) => { tip.textContent = g.dataset.tip; tip.style.display = "block"; tip.style.left = e.clientX + 12 + "px"; tip.style.top = e.clientY + 12 + "px"; });
    g.addEventListener("mouseleave", () => { tip.style.display = "none"; });
  });
}

// ---------------- money maths ----------------
async function renderMoney() {
  const el = $("#money");
  if (el.dataset.done) return;
  const e = await api("/api/example");
  const f = e.per_order_full, d = e.per_order_discounted, b = e.blanket, t = e.truelift, n = e.no_offer;
  const line = (k, v, total) => `<div class="row ${total ? "total" : ""}"><span class="k">${k}</span><span class="v">${v}</span></div>`;
  el.innerHTML = `<h1>The money, step by step</h1>
  <p>The Round 1 example: a restaurant with ₹400 orders and 70 orders a week from regulars. A ₹60-off offer brings 30 new orders. Commission is 25% plus 18% GST on it (29.5% in total); food and packaging cost 37% of the order.</p>
  <div class="calc"><h4>One ₹400 order</h4>
    ${line("Food sales", inr2(f.basket))}${line("Commission (25%)", "−" + inr2(f.commission))}${line("GST on commission (18%)", "−" + inr2(f.gst_on_commission))}${line("Food and packaging (37%)", "−" + inr2(f.food_cost))}
    ${line("<b>Restaurant keeps</b>", inr2(f.restaurant_profit), true)}${line("Zomato's gross commission", inr2(f.commission))}</div>
  <div class="calc"><h4>The same order with ₹60 off (paid by the restaurant)</h4>
    ${line("Food sales", inr2(d.basket))}${line("Discount", "−" + inr2(d.discount))}${line("Commission (25% of ₹340)", "−" + inr2(d.commission))}${line("GST on commission", "−" + inr2(d.gst_on_commission))}${line("Food and packaging", "−" + inr2(d.food_cost))}
    ${line("<b>Restaurant keeps</b>", inr2(d.restaurant_profit), true)}${line("Zomato's gross commission", inr2(d.commission))}</div>
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

boot().catch((e) => { $("#screen").innerHTML = `<p class="neg">${esc(e.message)}</p>`; });
