// Browser tests for the demo (Playwright Test), in every way the demo is opened:
//   static        the static site (site/) over HTTP, desktop Chrome
//   phone         the same site on a phone (Pixel 7 viewport and touch)
//   offline-file  the offline bundle opened from disk (file://), no server at all
//   offline-http  the offline bundle through its own local server, every other host blocked
//   live          the live service (uvicorn), started here
//   public        the published site (set TRUELIFT_PUBLIC_URL)
//
//   cd tests/ui && npm ci && npx playwright install chromium
//   npx playwright test                                   static, phone, offline-file, offline-http, live
//   UI_PROJECTS=static,phone npx playwright test          only the static site (needs `python tasks.py export`)
//   UI_PROJECTS=offline-file,offline-http npx playwright test   needs `python scripts/build_offline.py`
//   UI_PROJECTS=public TRUELIFT_PUBLIC_URL=https://yashg1836.github.io/truelift/ npx playwright test
// @ts-check
const path = require("path");
const { pathToFileURL } = require("url");
const { defineConfig, devices } = require("@playwright/test");

const ROOT = path.resolve(__dirname, "..", "..");
const STATIC_PORT = 4173;
const OFFLINE_PORT = 4174;
const LIVE_PORT = 8765;
const OFFLINE_DIR = path.join(ROOT, "dist", "truelift-offline");
const wanted = (process.env.UI_PROJECTS || "static,phone,offline-file,offline-http,live").split(",").map((s) => s.trim());
const python = process.env.TRUELIFT_PYTHON || "python";
const liveCommand = process.env.TRUELIFT_LIVE_COMMAND || "uv run uvicorn truelift.api:app";

const projects = [
  { name: "static", use: { ...devices["Desktop Chrome"], baseURL: `http://127.0.0.1:${STATIC_PORT}/` } },
  { name: "phone", use: { ...devices["Pixel 7"], baseURL: `http://127.0.0.1:${STATIC_PORT}/` } },
  { name: "offline-file", use: { ...devices["Desktop Chrome"], baseURL: pathToFileURL(OFFLINE_DIR).href + "/" } },
  { name: "offline-http", use: { ...devices["Desktop Chrome"], baseURL: `http://127.0.0.1:${OFFLINE_PORT}/` } },
  { name: "live", use: { ...devices["Desktop Chrome"], baseURL: `http://127.0.0.1:${LIVE_PORT}/` } },
  { name: "public", use: { ...devices["Desktop Chrome"], baseURL: process.env.TRUELIFT_PUBLIC_URL } },
].filter((p) => wanted.includes(p.name));

const servers = [];
if (wanted.includes("static") || wanted.includes("phone")) {
  servers.push({
    command: `${python} -m http.server ${STATIC_PORT} --bind 127.0.0.1 --directory "${path.join(ROOT, "site")}"`,
    url: `http://127.0.0.1:${STATIC_PORT}/data/config.json`,
    stdout: "ignore",
    stderr: "ignore", // http.server logs every request
    reuseExistingServer: !process.env.CI,
    timeout: 30_000,
  });
}
if (wanted.includes("offline-http")) {
  servers.push({
    command: `${python} "${path.join(OFFLINE_DIR, "serve.py")}" ${OFFLINE_PORT}`,
    url: `http://127.0.0.1:${OFFLINE_PORT}/data/config.json`,
    env: { BROWSER: "none" }, // serve.py would open a browser tab; keep the test headless
    stdout: "ignore",
    stderr: "ignore",
    reuseExistingServer: !process.env.CI,
    timeout: 30_000,
  });
}
if (wanted.includes("live")) {
  servers.push({
    command: `${liveCommand} --host 127.0.0.1 --port ${LIVE_PORT}`,
    cwd: ROOT,
    url: `http://127.0.0.1:${LIVE_PORT}/readyz`,
    env: { TRUELIFT_DB: ":memory:", TRUELIFT_LOG_JSON: "0", PYTHONIOENCODING: "utf-8" },
    reuseExistingServer: !process.env.CI,
    timeout: 180_000,
  });
}

module.exports = defineConfig({
  testDir: "./specs",
  timeout: 180_000,
  expect: { timeout: 60_000 },
  fullyParallel: false,
  workers: 1,
  retries: process.env.CI ? 1 : 0,
  reporter: [["list"], ["html", { open: "never" }]],
  use: { trace: "retain-on-failure", screenshot: "only-on-failure" },
  projects,
  webServer: servers,
});
