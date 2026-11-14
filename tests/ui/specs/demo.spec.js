// The demo end to end, in every mode the config selects (static site, live service, public URL):
// home, the guided demo to its last step, every tab, and a manual offer (wrong and right OTP, one
// simulated week) at desktop and phone width. Fails on page errors, console errors or broken text.
// Ported from tests/ui_check.js (kept for the team's existing workflow).
// @ts-check
const { test, expect } = require("@playwright/test");

const BROKEN = /NaN|undefined|\[object Object\]|Infinity/;

/** Collect page errors and console errors (a wrong OTP's 403 is expected, so it is ignored). */
function watch(page) {
  const errors = [];
  page.on("pageerror", (e) => errors.push(`pageerror: ${e.message}`));
  page.on("console", (m) => {
    if (m.type() === "error" && !/403/.test(m.text())) errors.push(`console: ${m.text()}`);
  });
  return errors;
}

async function expectCleanText(page, label) {
  const text = await page.evaluate(() => document.body.innerText);
  const m = text.match(BROKEN);
  const near = m ? text.slice(Math.max(0, (m.index || 0) - 60), (m.index || 0) + 20).replace(/\s+/g, " ") : "";
  expect(m, `${label}: found "${m && m[0]}" near "${near}"`).toBeNull();
}

async function openHome(page) {
  await page.goto("./");
  await page.waitForSelector(".hero-card", { timeout: 90_000 });
}

test("home page loads the demo restaurant with clean text", async ({ page }) => {
  const errors = watch(page);
  await openHome(page);
  await expectCleanText(page, "home");
  expect(errors).toEqual([]);
});

test("guided demo runs from the first step to Finish", async ({ page }) => {
  const errors = watch(page);
  await openHome(page);
  await page.click("#tourBtn");
  let finished = false;
  for (let i = 0; i < 15 && !finished; i++) {
    await page.waitForFunction(
      () => {
        const n = document.querySelector("#tourNext");
        return n && !(/** @type {HTMLButtonElement} */ (n).disabled) && n.textContent !== "…";
      },
      null,
      { timeout: 90_000 },
    );
    const step = await page.textContent("#tourStep");
    await expectCleanText(page, `tour ${step}`);
    finished = (await page.textContent("#tourNext")) === "Finish";
    await page.click("#tourNext");
  }
  expect(finished, "the guided demo reached its Finish button").toBe(true);
  expect(errors).toEqual([]);
});

test("every tab renders", async ({ page }) => {
  const errors = watch(page);
  await openHome(page);
  for (const tab of ["how", "evidence", "money", "demo"]) {
    await page.click(`nav button[data-tab="${tab}"]`);
    await page.waitForTimeout(500);
    await expectCleanText(page, `tab ${tab}`);
  }
  expect(errors).toEqual([]);
});

test("manual offer: wrong OTP refused, right OTP approves, a week is measured", async ({ page }) => {
  const errors = watch(page);
  await openHome(page);
  const options = await page.$$eval("#rest option", (os) => os.map((o) => /** @type {HTMLOptionElement} */ (o).value));
  await page.selectOption("#rest", options[options.length - 1]);
  await page.click('#screen [data-go="create"]');
  await page.waitForSelector("#ownerCard", { timeout: 60_000 });
  await page.click("#screen [data-val='\"targeted\"']");
  await page.waitForSelector("#ownerCard", { timeout: 60_000 });
  await expectCleanText(page, "create");

  await page.click('[data-act="toOtp"]');
  await page.waitForSelector("[data-otp]");
  await page.keyboard.type("0000");
  await page.click('[data-act="approve"]');
  await expect(page.locator("#otperr")).not.toBeEmpty();

  const code = ((await page.textContent("#otpCard")) || "").match(/Demo OTP: (\d{4})/)?.[1];
  expect(code, "the demo OTP is shown").toBeTruthy();
  const boxes = await page.$$("[data-otp]");
  for (const box of boxes) await box.fill("");
  await boxes[0].focus();
  await page.keyboard.type(String(code));
  await page.click('[data-act="approve"]');
  await page.waitForSelector("#runBtn");
  await page.click("#runBtn");
  await page.waitForSelector("#weekCard", { timeout: 60_000 });
  await expectCleanText(page, "week");

  await page.setViewportSize({ width: 390, height: 844 });
  await page.waitForTimeout(300);
  await expectCleanText(page, "phone width");
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
  expect(overflow, "no sideways scrolling at 390 px").toBeLessThanOrEqual(1);
  expect(errors).toEqual([]);
});
