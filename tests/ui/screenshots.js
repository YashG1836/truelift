// Take the README's images from the static site (scripts/make_video.py runs it):
//   node screenshots.js <page URL ending in #names=generic> <output folder>
// Generic names only: the README shows "Burger place #233", never a real brand.
//   tour_NN.png         the guided demo at 1280 x 720, one frame per step kept in the animation
//                       (make_video.py turns them into tour.gif and deletes them)
//   owner_forecast.png  phone: the forecast of the owner's offer, before approval
//   owner_better.png    phone: TrueLift's better version of the same discount
//   owner_otp.png       phone: the OTP approval
//   owner_result.png    phone: the offer after four simulated weeks, "Show me how you know" open
//   who_sees.png        Zomato's side: who sees the discount, and the 1-in-10 control group
//   problem.png         How it works: 100 orders used an offer, 70 would have come anyway
//   evidence.png        Evidence: the headline tiles and the first two charts
// Fails on any page error, so a broken page never becomes a README image.
// @ts-check
const path = require("path");
const { chromium } = require("@playwright/test");

// 1-based steps of the guided demo kept in the animation: the restaurant, the owner's offer, the
// better version, who sees it, the OTP, week 1, week 4 and the market (not "live" or "try it").
const TOUR_STEPS = [1, 2, 3, 4, 5, 7, 8, 9];
const PHONE = { viewport: { width: 390, height: 844 }, deviceScaleFactor: 2, isMobile: true, hasTouch: true };
const DESKTOP = { viewport: { width: 1280, height: 800 }, deviceScaleFactor: 2 };
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

/** Phone frame: the screen below the site's sticky header (left out, it is the same in every
 * frame), starting just above the card. */
async function phoneShot(page, selector, file) {
  const header = await page.locator(selector).evaluate((el) => {
    const h = document.querySelector("header")?.getBoundingClientRect().height || 0;
    window.scrollTo(0, Math.max(0, el.getBoundingClientRect().top + window.scrollY - h - 12));
    return Math.ceil(h);
  });
  await page.waitForTimeout(500);
  const { width, height } = PHONE.viewport;
  await page.screenshot({ path: file, clip: { x: 0, y: header, width, height: height - header } });
}

/** Desktop picture of a page region from the top of `first` to the bottom of `last`, with a margin. */
async function regionShot(page, first, last, file, { x = 16, top = 16, bottom = 16 } = {}) {
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
  const clip = { x: Math.max(0, box.x - x), y, width: box.width + 2 * x, height: box.y + box.height + bottom - y };
  await page.screenshot({ path: file, clip, fullPage: true });
}

async function tourFrames(browser, url, out) {
  const page = await open(browser, url, { viewport: { width: 1280, height: 720 } });
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
      await page.screenshot({ path: path.join(out, `tour_${String(step).padStart(2, "0")}.png`) });
    }
    finished = (await page.textContent("#tourNext")) === "Finish";
    if (!finished) await page.click("#tourNext");
  }
  if (step < Math.max(...TOUR_STEPS)) throw new Error(`the guided demo stopped at step ${step}`);
  await page.context().close();
}

async function phoneFrames(browser, url, out) {
  const page = await open(browser, url, PHONE);
  await createOffer(page);
  await phoneShot(page, "#ownerCard", path.join(out, "owner_forecast.png"));
  await phoneShot(page, "#betterCard", path.join(out, "owner_better.png"));
  await useBetter(page);
  await page.click('[data-act="toOtp"]');
  await page.waitForSelector("[data-otp]");
  // from "Change offer": what the owner approves (forecast, range, four weeks, who pays), then the OTP
  await phoneShot(page, "#screen > .back", path.join(out, "owner_otp.png"));
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
  await page.click("#howKnow summary");
  await phoneShot(page, "#weekCard", path.join(out, "owner_result.png"));
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
  await regionShot(page, "#who", "#who .cust-list > :nth-child(6)", path.join(out, "who_sees.png"), { x: 0, top: 0, bottom: 0 });

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
    await desktopPictures(browser, url, out);
  } finally {
    await browser.close();
  }
  if (errors.length) throw new Error("page errors: " + errors.join("; "));
})().catch((e) => {
  console.error(e);
  process.exit(1);
});
