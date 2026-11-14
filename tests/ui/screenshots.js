// Take the README's two screenshots from the static site (scripts/make_video.py runs it):
//   node screenshots.js <page URL> <create-offer.png> <weekly-results.png>
// 1. the create screen: the owner's offer, its forecast and TrueLift's better version;
// 2. the offer after four simulated weeks, with "Show me how you know" open.
// @ts-check
const { chromium } = require("@playwright/test");

(async () => {
  const [url, createPng, weeksPng] = process.argv.slice(2);
  if (!url || !createPng || !weeksPng) throw new Error("usage: node screenshots.js URL create.png weeks.png");
  const browser = await chromium.launch();
  const page = await browser.newPage({ viewport: { width: 1280, height: 860 } });
  const errors = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await page.goto(url);
  await page.waitForSelector(".hero-card", { timeout: 90_000 });
  await page.evaluate(() => document.fonts.ready);
  const hint = await page.$(".hint-x");
  if (hint) await hint.click();

  await page.click('#screen [data-go="create"]');
  await page.waitForSelector("#ownerCard", { timeout: 60_000 });
  await page.waitForSelector("#betterCard", { timeout: 60_000 });
  // the end of the owner's forecast and TrueLift's better version, side by side with who sees it
  await page.locator("#betterCard").evaluate((el) => el.scrollIntoView({ block: "center" }));
  await page.waitForTimeout(600);
  await page.screenshot({ path: createPng });

  await page.click('[data-act="useBetter"]');
  await page.waitForSelector("#ownerCard", { timeout: 60_000 });
  await page.click('[data-act="toOtp"]');
  await page.waitForSelector("[data-otp]");
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
  await page.locator("#weekCard").scrollIntoViewIfNeeded();
  await page.waitForTimeout(600);
  await page.screenshot({ path: weeksPng });
  await browser.close();
  if (errors.length) throw new Error("page errors: " + errors.join("; "));
})().catch((e) => {
  console.error(e);
  process.exit(1);
});
