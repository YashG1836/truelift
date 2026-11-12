// Browser check of the whole site: runs the guided demo end to end, every tab, and a manual flow
// (create offer, wrong and right OTP, one week, phone width). Fails on page errors or broken text.
//   npm i playwright-core
//   node tests/ui_check.js reports/ui http://localhost:8000/      (or the GitHub Pages URL)
// Uses the installed Chrome; set CHROME to its path on other systems.
const { chromium } = require("playwright-core");
const fs = require("fs");
const out = process.argv[2] || "reports/ui", url = process.argv[3] || "http://localhost:8000/";
fs.mkdirSync(out, { recursive: true });
const bad = /NaN|undefined|\[object Object\]|Infinity/;
(async () => {
  const b = await chromium.launch({ executablePath: process.env.CHROME || "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome", headless: true });
  const p = await b.newPage({ viewport: { width: 1440, height: 1000 } });
  const errors = [];
  p.on("pageerror", (e) => errors.push("pageerror: " + e.message));
  p.on("console", (m) => { if (m.type() === "error" && !/403/.test(m.text())) errors.push("console: " + m.text()); });
  const check = async (label) => {
    const t = await p.evaluate(() => document.body.innerText);
    const m = t.match(bad);
    if (m) errors.push(`${label}: found "${m[0]}" near "${t.slice(Math.max(0, m.index - 60), m.index + 20).replace(/\s+/g, " ")}"`);
  };
  await p.goto(url);
  await p.waitForSelector(".hero-card", { timeout: 90000 });
  await p.screenshot({ path: out + "/t0_home.png" }); await check("home");
  await p.click("#tourBtn");
  for (let i = 0; i < 12; i++) {
    await p.waitForFunction(() => { const n = document.querySelector("#tourNext"); return n && !n.disabled && n.textContent !== "…"; }, null, { timeout: 90000 });
    const step = await p.textContent("#tourStep"), title = await p.textContent("#tourTitle");
    await p.waitForTimeout(600);
    await p.screenshot({ path: `${out}/t${i + 1}.png` }); await check("tour " + step + " " + title);
    console.log(step, "|", title, "|", (await p.textContent("#tourText")).slice(0, 170));
    if ((await p.textContent("#tourNext")) === "Finish") { await p.click("#tourNext"); break; }
    await p.click("#tourNext");
  }
  for (const tab of ["how", "evidence", "money"]) {
    await p.click(`nav button[data-tab="${tab}"]`); await p.waitForTimeout(800);
    await p.screenshot({ path: `${out}/tab_${tab}.png`, fullPage: true }); await check("tab " + tab);
  }
  // manual flow on another restaurant
  await p.click('nav button[data-tab="demo"]');
  const opts = await p.$$eval("#rest option", (os) => os.map((o) => o.value));
  await p.selectOption("#rest", opts[opts.length - 1]); await p.waitForTimeout(1000);
  await p.click('#screen [data-go="create"]'); await p.waitForSelector("#ownerCard", { timeout: 60000 });
  await p.click("#screen [data-val='\"targeted\"']"); await p.waitForTimeout(300); await p.waitForSelector("#ownerCard", { timeout: 60000 }); await p.waitForTimeout(500);
  await check("manual create");
  await p.click('[data-act="toOtp"]'); await p.waitForSelector("[data-otp]");
  await p.keyboard.type("0000"); await p.click('[data-act="approve"]'); await p.waitForTimeout(400);
  console.log("wrong otp message:", await p.textContent("#otperr"));
  const code = (await p.textContent("#otpCard")).match(/Demo OTP: (\d{4})/)[1];
  const boxes = await p.$$("[data-otp]"); for (const bx of boxes) await bx.fill("");
  await boxes[0].focus(); await p.keyboard.type(code); await p.click('[data-act="approve"]');
  await p.waitForSelector("#runBtn"); await p.click("#runBtn"); await p.waitForSelector("#weekCard", { timeout: 60000 });
  await p.waitForTimeout(400); await check("manual week"); await p.screenshot({ path: out + "/m_week.png" });
  await p.setViewportSize({ width: 390, height: 844 }); await p.waitForTimeout(400);
  await p.screenshot({ path: out + "/m_mobile.png", fullPage: true }); await check("mobile");
  console.log(errors.length ? "PROBLEMS:\n" + errors.join("\n") : "no problems found");
  await b.close();
  process.exit(errors.length ? 1 : 0);
})().catch((e) => { console.error("FAILED", e.message); process.exit(1); });
