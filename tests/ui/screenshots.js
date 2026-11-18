// Take the README's images from the static site (scripts/make_video.py runs it):
//   node screenshots.js <page URL ending in #names=generic> <output folder>
// Generic names only: the README shows "Burger place #233", never a real brand.
//   tour_NN.png         the guided demo at 1440 x 1000, one frame per step kept in the animation, with
//                       the whole phone in view (make_video.py turns them into tour.gif and deletes them)
//   owner_forecast.png  phone: the forecast card of the owner's offer, before approval
//   owner_better.png    phone: TrueLift's better version of the same discount
//   owner_otp.png       phone: what the owner approves, and the OTP
//   owner_result.png    phone: the offer after four simulated weeks
//   owner_flow.png      the four above in one picture, two by two, with a caption each
//   who_sees.png        Zomato's side: who sees the discount, and the 1-in-10 control group
//   problem.png         How it works: 100 orders used an offer, 70 would have come anyway
//   evidence.png        Evidence: the headline tiles and the first two charts
// Every picture shows whole cards with a margin around them: nothing is cut at an edge.
// Fails on any page error, so a broken page never becomes a README image.
// @ts-check
const fs = require("fs");
const path = require("path");
const { chromium } = require("@playwright/test");

// 1-based steps of the guided demo kept in the animation: the restaurant, the owner's offer, the
// better version, who sees it, the OTP, week 1, week 4 and the market (not "live" or "try it").
const TOUR_STEPS = [1, 2, 3, 4, 5, 7, 8, 9];
const PHONE = { viewport: { width: 390, height: 844 }, deviceScaleFactor: 2, isMobile: true, hasTouch: true };
const DESKTOP = { viewport: { width: 1280, height: 800 }, deviceScaleFactor: 2 };
// wide and tall enough that the header and the whole 820-pixel phone fit in one frame
const TOUR = { viewport: { width: 1440, height: 1000 } };
const errors = [];

/** Open the page in a fresh context and close the first-visit hint. */
async function open(browser, url, options) {
  const context = await browser.newContext(options);
  const page = await context.newPage();
  page.on("pageerror", (e) => errors.push(e.message));
  await page.goto(url);
  await page.waitForSelector(".hero-card", { timeout: 90_000 });
  await page.evaluate(() => document.fonts.ready);
  const hint = await page.waitForSelector(".hint-x", { timeout: 5_000 }).catch(() => null);
  if (hint) await hint.click();
  return page;
}

/** Create the owner's usual offer and wait for its forecast and TrueLift's suggestion. */
async function createOffer(page) {
  await page.click('#screen [data-go="create"]');
  await page.waitForSelector("#ownerCard", { timeout: 60_000 });
  await page.waitForSelector("#betterCard", { timeout: 60_000 });
}

/** Take the suggested version and wait until the forecast shows it (it is then the best, so the
 * suggestion card goes away). */
async function useBetter(page) {
  await page.click('[data-act="useBetter"]');
  await page.waitForFunction(() => !document.querySelector("#betterCard") && document.querySelector("#ownerCard"), null, {
    timeout: 60_000,
  });
  await page.waitForTimeout(300);
}

/** Phone picture of whole cards: from the top of `first` to the bottom of `last`, the full screen
 * width, with a margin of page background above and below, so no card is cut. */
async function cardShot(page, first, last, file) {
  // hide everything before `first` and after `last` (layout kept), so the margin shows no sliver
  // of a neighbouring card
  await page.evaluate(
    ([a, b]) => {
      const f = document.querySelector(a), l = document.querySelector(b);
      if (!f || !l) return;
      document.querySelectorAll("body *").forEach((el) => {
        if (el.contains(f) || el.contains(l)) return; // an ancestor of the cards
        const fromFirst = f === el || f.contains(el) || !!(f.compareDocumentPosition(el) & Node.DOCUMENT_POSITION_FOLLOWING);
        const toLast = l === el || l.contains(el) || !!(l.compareDocumentPosition(el) & Node.DOCUMENT_POSITION_PRECEDING);
        if (!(fromFirst && toLast)) /** @type {HTMLElement} */ (el).dataset.shotHidden = "1";
      });
    },
    [first, last],
  );
  const style = await page.addStyleTag({ content: "[data-shot-hidden] { visibility: hidden !important; }" });
  await page.waitForTimeout(400);
  await regionShot(page, first, last, file, { x: 0, top: 14, bottom: 14, fullWidth: true });
  await style.evaluate((s) => s.remove());
  await page.evaluate(() => document.querySelectorAll("[data-shot-hidden]").forEach((el) => el.removeAttribute("data-shot-hidden")));
}

/** The four owner screens in one picture, two by two, each with its step and a caption. Cards are
 * aligned at the top; the page's own font and colours. */
async function ownerFlow(browser, url, out) {
  const cells = [
    ["owner_forecast.png", "1", "Before approval: the forecast"],
    ["owner_better.png", "2", "A better version of the same discount"],
    ["owner_otp.png", "3", "The OTP approval"],
    ["owner_result.png", "4", "Four weeks later: what it really added"],
  ];
  const img = (f) => "data:image/png;base64," + fs.readFileSync(path.join(out, f)).toString("base64");
  const html = `<!doctype html><html><head><meta charset="utf-8"><style>
    body { margin: 0; background: #f8f8f8; font-family: Figtree, system-ui, sans-serif; color: #1c1c1c; }
    .grid { display: grid; grid-template-columns: 1fr 1fr; gap: 28px 24px; padding: 28px 24px; width: 840px; box-sizing: border-box; align-items: start; }
    .cap { display: flex; gap: 10px; align-items: center; font-size: 16px; font-weight: 600; margin: 0 0 4px 14px; }
    .cap b { width: 26px; height: 26px; border-radius: 50%; background: #e23744; color: #fff; display: inline-flex; align-items: center; justify-content: center; font-size: 14px; flex: none; }
    .grid img { width: 100%; display: block; }
  </style></head><body><div class="grid">${cells
    .map(([f, n, t]) => `<div><div class="cap"><b>${n}</b>${t}</div><img src="${img(f)}" alt=""></div>`)
    .join("")}</div></body></html>`;
  const page = await open(browser, url, { viewport: { width: 840, height: 800 }, deviceScaleFactor: 2 });
  await page.setContent(html.replace("<head>", `<head><base href="${url.split("#")[0]}">`));
  await page.addStyleTag({ url: "static/style.css" }).catch(() => {}); // the page's Figtree faces
  await page.evaluate(() => document.fonts.ready);
  await page.waitForTimeout(300);
  await (await page.$(".grid"))?.screenshot({ path: path.join(out, "owner_flow.png") });
  await page.context().close();
}

/** Guided-demo frame: at the top of the page, so the header and the whole phone show. If the step
 * points at a panel lower on the page, the visitor list above it is folded away for this frame only,
 * so the panel fits too; only if it still does not fit, the page scrolls to it. */
async function frameWhole(page) {
  await page.evaluate(() => {
    window.scrollTo({ top: 0, behavior: "instant" });
    const spot = document.querySelector(".spot");
    if (!spot || spot.closest(".phone")) return;
    const fits = () => spot.getBoundingClientRect().bottom <= window.innerHeight - 16;
    if (fits()) return;
    const list = document.querySelector("#who .cust-list");
    list?.setAttribute("data-frame-hide", "1");
    list?.previousElementSibling?.setAttribute("data-frame-hide", "1"); // its heading
    if (fits()) return;
    const header = document.querySelector("header")?.getBoundingClientRect().height || 0;
    window.scrollTo({ top: spot.getBoundingClientRect().top - header - 20, behavior: "instant" });
  });
  await page.waitForTimeout(400);
}

/** Desktop picture of a page region from the top of `first` to the bottom of `last`, with a margin. */
async function regionShot(page, first, last, file, { x = 16, top = 16, bottom = 16, fullWidth = false } = {}) {
  const box = await page.evaluate(
    ([a, b]) => {
      const top = /** @type {Element} */ (typeof a === "string" ? document.querySelector(a) : null);
      const end = /** @type {Element} */ (typeof b === "string" ? document.querySelector(b) : null);
      if (!top || !end) return null;
      const r1 = top.getBoundingClientRect(), r2 = end.getBoundingClientRect();
      const x = Math.min(r1.left, r2.left), right = Math.max(r1.right, r2.right);
      return { x, y: r1.top + window.scrollY, width: right - x, height: r2.bottom - r1.top };
    },
    [first, last],
  );
  if (!box) throw new Error(`missing ${first} or ${last} for ${path.basename(file)}`);
  const y = Math.max(0, box.y - top);
  const vw = await page.evaluate(() => document.documentElement.clientWidth);
  const clip = fullWidth
    ? { x: 0, y, width: vw, height: box.y + box.height + bottom - y }
    : { x: Math.max(0, box.x - x), y, width: box.width + 2 * x, height: box.y + box.height + bottom - y };
  await page.screenshot({ path: file, clip, fullPage: true });
}

async function tourFrames(browser, url, out) {
  const page = await open(browser, url, TOUR);
  // room below the page, so a frame can put a low panel right under the header (see frameWhole)
  await page.addStyleTag({
    content: "body { padding-bottom: 800px !important; } #callsBox, [data-frame-hide] { display: none !important; }",
  });
  await page.click("#tourBtn");
  let step = 0, finished = false;
  while (!finished && step < 15) {
    step += 1;
    await page.waitForFunction(
      () => {
        const n = /** @type {HTMLButtonElement | null} */ (document.querySelector("#tourNext"));
        return n && !n.disabled && n.textContent !== "…";
      },
      null,
      { timeout: 90_000 },
    );
    await page.waitForTimeout(1200); // the spotlight moves and the caption settles
    if (TOUR_STEPS.includes(step)) {
      await frameWhole(page);
      await page.screenshot({ path: path.join(out, `tour_${String(step).padStart(2, "0")}.png`) });
      await page.evaluate(() => document.querySelectorAll("[data-frame-hide]").forEach((e) => e.removeAttribute("data-frame-hide")));
    }
    finished = (await page.textContent("#tourNext")) === "Finish";
    if (!finished) await page.click("#tourNext");
  }
  if (step < Math.max(...TOUR_STEPS)) throw new Error(`the guided demo stopped at step ${step}`);
  await page.context().close();
}

async function phoneFrames(browser, url, out) {
  const page = await open(browser, url, PHONE);
  // a full-page capture would draw the sticky header over the cards
  await page.addStyleTag({ content: "header { position: static !important; }" });
  await createOffer(page);
  await cardShot(page, "#ownerCard", "#ownerCard", path.join(out, "owner_forecast.png"));
  await cardShot(page, "#betterCard", "#betterCard", path.join(out, "owner_better.png"));
  await useBetter(page);
  await page.click('[data-act="toOtp"]');
  await page.waitForSelector("[data-otp]");
  // from "Change offer": what the owner approves (forecast, range, four weeks, who pays), then the OTP
  await cardShot(page, "#screen > .back", "#otpCard", path.join(out, "owner_otp.png"));
  const code = ((await page.textContent("#otpCard")) || "").match(/Demo OTP: (\d{4})/)?.[1];
  if (!code) throw new Error("no demo OTP on the approval screen");
  const boxes = await page.$$("[data-otp]");
  await boxes[0].focus();
  await page.keyboard.type(code);
  await page.click('[data-act="approve"]');
  for (let week = 1; week <= 4; week++) {
    await page.waitForSelector("#runBtn:not([disabled])", { timeout: 60_000 });
    await page.click("#runBtn");
    // done when the button offers the next week, or is gone once the approved weeks are used up
    await page.waitForFunction(
      (n) => {
        const b = document.querySelector("#runBtn");
        return !b || (b.textContent || "").includes(`week ${n + 1}`);
      },
      week,
      { timeout: 60_000 },
    );
  }
  await cardShot(page, "#weekCard", "#weekCard", path.join(out, "owner_result.png"));
  await page.context().close();
}

async function desktopPictures(browser, url, out) {
  const page = await open(browser, url, DESKTOP);
  // a full-page capture draws the sticky header over the region; these pictures leave it out anyway
  await page.addStyleTag({ content: "header { position: static !important; }" });
  await createOffer(page);
  await useBetter(page);
  // three rows of visitors: regulars and lapsed customers who get no discount, then a new customer
  // who sees it and one held out in the control group
  await page.waitForSelector("#who .cust-list > :nth-child(6)", { timeout: 60_000 });
  // the whole panel with its first six visitors, so it ends on complete cards and its own border
  await page.addStyleTag({ content: "#who .cust-list > :nth-child(n+7) { display: none !important; }" });
  await page.waitForTimeout(300);
  await regionShot(page, "#who", "#who", path.join(out, "who_sees.png"), { x: 16, top: 16, bottom: 16 });

  await page.click('nav button[data-tab="how"]');
  await page.waitForSelector("#how .waffle", { timeout: 60_000 });
  // little room above: the section heading sits right on top of the picture
  await regionShot(page, "#how .split", "#how .split", path.join(out, "problem.png"), { top: 2 });

  await page.click('nav button[data-tab="evidence"]');
  await page.waitForSelector("#evidence .charts .chart", { timeout: 90_000 });
  await page.waitForTimeout(800);
  await regionShot(page, "#evidence h1", "#evidence .charts", path.join(out, "evidence.png"));
  await page.context().close();
}

(async () => {
  const [url, out] = process.argv.slice(2);
  if (!url || !out) throw new Error("usage: node screenshots.js URL OUT_DIR");
  if (!url.includes("names=generic")) throw new Error("the URL must ask for generic names (#names=generic)");
  const browser = await chromium.launch();
  try {
    await tourFrames(browser, url, out);
    await phoneFrames(browser, url, out);
    await ownerFlow(browser, url, out);
    await desktopPictures(browser, url, out);
  } finally {
    await browser.close();
  }
  if (errors.length) throw new Error("page errors: " + errors.join("; "));
})().catch((e) => {
  console.error(e);
  process.exit(1);
});
