// Đo yên mạng/polling + LCP: số request /api trong 20 s sau khi tải trang, theo đường dẫn.
import { chromium } from "playwright";
const BASE = process.env.BASE || "http://127.0.0.1:8580";
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const browser = await chromium.launch();
const ctx = await browser.newContext({ viewport: { width: 1600, height: 900 }, baseURL: BASE });
await ctx.addInitScript(() => { try { localStorage.setItem("ts-ux", JSON.stringify({ onboarded: 99 })); } catch {} });
for (let i = 0; i < 6; i++) { try { const r = await ctx.request.post(`${BASE}/auth/login`, { data: { platform: "master", login: process.env.QA_USER, secret: process.env.QA_PASS }, headers: { Origin: BASE, "Content-Type": "application/json" } }); console.log("login", r.status()); if (r.ok()) break; } catch {} await sleep(3000); }
for (const route of (process.env.ROUTES || "du-lieu").split(",")) {
  const page = await ctx.newPage();
  const reqs = [];
  page.on("requestfinished", (r) => { if (process.env.V) console.log("fin", r.url().slice(-60)); }); page.on("request", (r) => { if (process.env.V) console.log("req", Date.now() % 100000, r.url().slice(-60)); if (r.url().includes("/api/")) reqs.push({ t: Date.now(), u: new URL(r.url()).pathname }); });
  await page.addInitScript(() => { window.__lcp = 0; new PerformanceObserver((l) => { for (const e of l.getEntries()) window.__lcp = e.startTime; }).observe({ type: "largest-contentful-paint", buffered: true }); });
  const t0 = Date.now();
  await page.goto(`${BASE}/#/${route}`, { waitUntil: "load" });
  await page.waitForLoadState("networkidle", { timeout: 20000 }).then(() => console.log(route, "networkidle OK"), () => console.log(route, "KHONG networkidle (20s)")); await sleep(1000);
  const lcp = await page.evaluate(() => Math.round(window.__lcp));
  const inflight = await page.evaluate(() => performance.getEntriesByType("resource").filter((e) => e.responseEnd === 0).length);
  const late = reqs.filter((r) => r.t - t0 > 6000); console.log("pending-resources", inflight);
  const by = {}; for (const r of late) by[r.u] = (by[r.u] || 0) + 1;
  console.log(route, "LCP", lcp, "ms; total", reqs.length, "; sau 6s:", late.length, JSON.stringify(by));
  await page.close();
}
await browser.close();
