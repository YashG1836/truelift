// Print a local HTML page to PDF with Playwright's Chromium, and optionally save a PNG of every
// element marked data-shot="name" (the pitch deck's charts for the editable PPTX).
// Used by scripts/make_deck.py:
//   node print_pdf.js <page.html> <out.pdf> <width px> <height px> [shots folder]
// @ts-check
const path = require("path");
const { pathToFileURL } = require("url");
const { chromium } = require("@playwright/test");

(async () => {
  const [src, pdf, width, height, shots] = process.argv.slice(2);
  if (!src || !pdf || !width || !height) throw new Error("usage: node print_pdf.js page.html out.pdf width height [shots]");
  const browser = await chromium.launch();
  const page = await browser.newPage({ viewport: { width: +width, height: +height }, deviceScaleFactor: 2 });
  await page.goto(pathToFileURL(path.resolve(src)).href, { waitUntil: "load" });
  await page.evaluate(() => document.fonts.ready);
  if (shots) {
    for (const el of await page.$$("[data-shot]")) {
      const name = await el.getAttribute("data-shot");
      await el.screenshot({ path: path.join(shots, `${name}.png`) });
    }
  }
  await page.pdf({ path: pdf, width: `${width}px`, height: `${height}px`, printBackground: true, preferCSSPageSize: true });
  await browser.close();
})().catch((e) => {
  console.error(e);
  process.exit(1);
});
