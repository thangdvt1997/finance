// Thăm dò (debug QA): phân trang lịch sử bằng phím Z với dữ liệu tổng hợp 30.000 nến M1.
import { chromium } from "playwright";
const BASE = process.env.BASE || "http://127.0.0.1:8080";
const browser = await chromium.launch();
const ctx = await browser.newContext({ baseURL: BASE, viewport: { width: 1500, height: 900 } });
const page = await ctx.newPage();
const sleep = (ms) => page.waitForTimeout(ms);
page.on("console", (m) => { if (/\[dbg\]/.test(m.text())) console.log(m.text()); });
await page.addInitScript(() => { window.__dbgMore = true; });
page.on("pageerror", (e) => console.log("pageerror", e.message));
const SYN_N = 30000, STEP = 60, END = Math.floor(Date.now() / 1000 / STEP) * STEP, T0 = END - (SYN_N - 1) * STEP;
const bar = (i) => { const x = i, base = 2300 + 40 * Math.sin(x / 700) + 15 * Math.sin(x / 90), o = base + Math.sin(x * 1.7), c = base + Math.cos(x * 1.3);
  return { symbol: "XAUUSD", tf: "M1", ts_open: new Date((T0 + i * STEP) * 1000).toISOString(), o, h: Math.max(o, c) + 2, l: Math.min(o, c) - 2, c, v: 100, source: "syn" }; };
const reqs = [];
await page.route(/\/api\/v1\/bars\?/, async (route) => {
  const u = new URL(route.request().url());
  if (u.searchParams.get("symbol") !== "XAUUSD" || u.searchParams.get("tf") !== "M1") return route.continue();
  const lim = Number(u.searchParams.get("limit") || 500), to = u.searchParams.get("to");
  let hi = SYN_N - 1; if (to) hi = Math.min(hi, Math.floor((Date.parse(to) / 1000 - T0) / STEP));
  reqs.push(`${lim}@${hi}`);
  const items = []; for (let i = hi; i >= 0 && items.length < lim; i--) items.push(bar(i));
  await route.fulfill({ json: { items, limit: lim, offset: 0, count: items.length } });
});
await page.goto(`${BASE}/#/thi-truong/XAUUSD?tf=M1`, { waitUntil: "load" });
await page.waitForSelector(".ws-cell canvas", { timeout: 40000 }); await sleep(5000);
const cnt = async () => Number(((await page.locator('dt:has-text("Nến") + dd').first().innerText().catch(() => "0")) + "").replace(/[^\d]/g, "") || 0);
console.log("start", await cnt(), "tf active:", await page.locator('.seg button[aria-pressed="true"]').allInnerTexts());
for (let i = 0; i < 14; i++) { await page.keyboard.press("z"); await sleep(1500); console.log("z", i, await cnt(), reqs.length); }
console.log(reqs.join(" "));
await browser.close();
