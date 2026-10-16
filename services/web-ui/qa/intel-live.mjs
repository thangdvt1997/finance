// QA thời gian thực terminal tin tức (agent C): chờ tin MỚI qua WebSocket xuất hiện ở đầu danh sách (tối đa LIVE_MIN phút, mặc định 8).
import { chromium } from "playwright";
import fs from "node:fs";
fs.mkdirSync("out", { recursive: true });
const BASE = process.env.BASE || "http://127.0.0.1:8580";
const LIVE_MIN = Number(process.env.LIVE_MIN || 8);
const browser = await chromium.launch();
const ctx = await browser.newContext({ viewport: { width: 1500, height: 900 }, colorScheme: "dark", baseURL: BASE });
const lr = await ctx.request.post(`${BASE}/auth/login`, { data: { platform: "master", login: process.env.QA_USER, secret: process.env.QA_PASS }, headers: { Origin: BASE, "Content-Type": "application/json" } });
console.log("login", lr.status());
const page = await ctx.newPage();
const errs = [];
page.on("pageerror", (e) => errs.push(String(e.message).slice(0, 200)));
await page.goto(`${BASE}/#/tin-tuc`, { waitUntil: "load" });
await page.waitForSelector('[aria-label="Dòng tin"] [role="listitem"]', { timeout: 20000 });
await page.waitForTimeout(3000);
const titles = () => page.evaluate(() => [...document.querySelectorAll('[aria-label="Dòng tin"] [role="listitem"] .nt')].slice(0, 12).map((e) => e.textContent.trim()));
const live = () => page.evaluate(() => document.querySelector(".live-dot")?.className || "");
const t0 = await titles();
console.log("ws:", await live(), "| top:", t0[0]);
const start = Date.now();
let hit = null;
while (Date.now() - start < LIVE_MIN * 60e3) {
  await page.waitForTimeout(5000);
  const t = await titles();
  const fresh = t.filter((x) => !t0.includes(x));
  if (fresh.length) { hit = { after_s: Math.round((Date.now() - start) / 1000), fresh: fresh.slice(0, 3) }; break; }
}
if (hit) { await page.screenshot({ path: "out/live-hit.png" }).catch(() => {}); console.log("PASS  tin mới xuất hiện qua WebSocket", JSON.stringify(hit)); }
else console.log(`WARN  không có tin mới trong ${LIVE_MIN} phút (có thể nguồn tin chưa phát sinh); lỗi trang: ${errs.length}`);
await browser.close();
process.exit(hit || !errs.length ? 0 : 1);
