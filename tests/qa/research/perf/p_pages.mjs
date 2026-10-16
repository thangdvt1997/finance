// P-005: thoi gian tai trang master (Playwright, 1366x768): tai lanh "tong-quan" (ctx moi: DCL/load/LCP/so request/KB) + dieu huong SPA moi trang
// (hash -> mang yen 500ms hoac 8 s). Chay qua p_pages.sh. Ra JSON stdout. Chi GET, khong dat lenh.
import { chromium } from "playwright";
const BASE = process.env.BASE || "http://127.0.0.1:8580", H = { Origin: BASE, "Content-Type": "application/json" };
const PAGES = (process.env.PAGES || "tong-quan,chung-khoan-vn,danh-sach,phan-tich,ban-tin,tin-tuc,lich,chuyen-gia,tai-khoan,mo-phong,nhat-ky,canh-bao,bao-cao,khach-hang,he-thong,luat,su-co,cai-dat,du-lieu,phien-giao-dich,suc-manh-tien-te,movers,ban-do-nhiet,kich-ban").split(",");
const browser = await chromium.launch();
async function mk() {
  const ctx = await browser.newContext({ viewport: { width: 1366, height: 768 }, baseURL: BASE });
  await ctx.addInitScript(() => { try { localStorage.setItem("ts-ux", JSON.stringify({ onboarded: 99, theme: "dark", numFmt: "vi", dateFmt: "vi", t: 0 })); } catch {} });
  const r = await ctx.request.post(`${BASE}/auth/login`, { data: { platform: "master", login: process.env.QA_USER, secret: process.env.QA_PASS }, headers: H });
  if (r.status() !== 200) { console.log("LOGIN FAIL", r.status()); process.exit(2); }
  return ctx;
}
const out = { cold: [], spa: [] };
for (let i = 0; i < 3; i++) {   // 3 lan tai lanh
  const ctx = await mk(), page = await ctx.newPage(); let n = 0, bytes = 0;
  page.on("response", async (x) => { n++; try { bytes += (await x.body()).length; } catch {} });
  await page.addInitScript(() => { window.__lcp = 0; new PerformanceObserver((l) => { for (const e of l.getEntries()) window.__lcp = e.startTime; }).observe({ type: "largest-contentful-paint", buffered: true }); });
  const t0 = Date.now(); await page.goto(`${BASE}/#/tong-quan`, { waitUntil: "load" }).catch(() => {});
  const tload = Date.now() - t0; await page.waitForLoadState("networkidle", { timeout: 10000 }).catch(() => {}); const tidle = Date.now() - t0;
  const m = await page.evaluate(() => { const n = performance.getEntriesByType("navigation")[0]; return { dcl: Math.round(n.domContentLoadedEventEnd), lcp: Math.round(window.__lcp) }; });
  out.cold.push({ load_ms: tload, idle_ms: tidle, ...m, requests: n, kb: Math.round(bytes / 1024) }); await ctx.close();
}
const ctx = await mk(), page = await ctx.newPage();
await page.goto(`${BASE}/#/tong-quan`, { waitUntil: "load" }).catch(() => {}); await page.waitForTimeout(2000);
for (const p of PAGES) {
  let t = 0, inflight = 0, last = Date.now();
  const on = () => { inflight++; last = Date.now(); }, off = () => { inflight--; last = Date.now(); };
  page.on("request", on); page.on("requestfinished", off); page.on("requestfailed", off);
  const t0 = Date.now(); await page.evaluate((x) => { location.hash = "#/" + x; }, p);
  while (Date.now() - t0 < 8000 && !(Date.now() - t0 > 300 && inflight <= 0 && Date.now() - last > 500)) await page.waitForTimeout(50);
  t = Date.now() - t0 - 500; page.off("request", on); page.off("requestfinished", off); page.off("requestfailed", off);
  out.spa.push({ page: p, settle_ms: Math.max(t, 0), capped: Date.now() - t0 >= 8000 });
}
console.log(JSON.stringify(out)); await browser.close();
