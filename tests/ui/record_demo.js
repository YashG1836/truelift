// Record the guided demo as a video with Playwright's Chromium: the tour's own captions explain
// each step, so no voice is needed. Used by scripts/make_video.py:
//   node record_demo.js <page URL> <output folder> <seconds per step>
// Prints the path of the recorded .webm on its last line.
// @ts-check
const { chromium } = require("@playwright/test");

(async () => {
  const [url, outDir, perStep] = process.argv.slice(2);
  if (!url || !outDir) throw new Error("usage: node record_demo.js URL OUT_DIR [seconds per step]");
  const hold = 1000 * (+perStep || 12);
  const browser = await chromium.launch();
  const context = await browser.newContext({
    viewport: { width: 1280, height: 720 },
    recordVideo: { dir: outDir, size: { width: 1280, height: 720 } },
  });
  const page = await context.newPage();
  const errors = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await page.goto(url + (url.includes("#") ? "&" : "#") + "tab=demo"); // the site opens on the Overview
  await page.waitForSelector(".hero-card", { timeout: 90_000 });
  await page.evaluate(() => document.fonts.ready);
  await page.waitForTimeout(3000);
  const hint = await page.$(".hint-x");
  if (hint) await hint.click();
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
    await page.waitForTimeout(hold);
    finished = (await page.textContent("#tourNext")) === "Finish";
    if (!finished) await page.click("#tourNext");
  }
  await page.waitForTimeout(2500);
  const video = page.video();
  await context.close();
  await browser.close();
  if (errors.length) throw new Error("page errors while recording: " + errors.join("; "));
  if (!finished) throw new Error("the guided demo did not reach its Finish button");
  console.log(video ? await video.path() : "");
})().catch((e) => {
  console.error(e);
  process.exit(1);
});
