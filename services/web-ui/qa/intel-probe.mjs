// Thăm dò nhanh (agent C): in dataset màu tăng/giảm, kích thước panel tin tức, số hàng ảo hoá. Chạy: run-c.sh intel-probe.mjs
import { chromium } from "playwright";
const BASE = process.env.BASE || "http://127.0.0.1:8580";
const browser = await chromium.launch();
const ctx = await browser.newContext({ viewport: { width: 1600, height: 950 }, colorScheme: "dark", timezoneId: "Asia/Ho_Chi_Minh", locale: "vi-VN", baseURL: BASE });
const lr = await ctx.request.post(`${BASE}/auth/login`, { data: { platform: "master", login: process.env.QA_USER, secret: process.env.QA_PASS }, headers: { Origin: BASE, "Content-Type": "application/json" } });
console.log("login", lr.status());
const page = await ctx.newPage();
await page.goto(`${BASE}/#/${process.env.PATH_ || "ban-do-nhiet"}`, { waitUntil: "load" });
await page.waitForTimeout(4000);
console.log(JSON.stringify(await page.evaluate(() => {
  const cs = getComputedStyle(document.documentElement);
  const grid = document.querySelector("#main .grid.flex-1");
  const vl = document.querySelector('[aria-label="Dòng tin"][role="list"]');
  const r = (e) => (e ? { h: Math.round(e.getBoundingClientRect().height), w: Math.round(e.getBoundingClientRect().width), ch: e.clientHeight, sh: e.scrollHeight } : null);
  return { tz: Intl.DateTimeFormat().resolvedOptions().timeZone, clockTxt: [...document.querySelectorAll("header *")].map((e) => e.children.length ? "" : e.textContent).filter((t) => /UTC/.test(t)).join("|"), dataset: { ...document.documentElement.dataset }, up: cs.getPropertyValue("--up"), down: cs.getPropertyValue("--down"), ux: localStorage.getItem("ts-ux"),
    grid: r(grid), gridStyle: grid ? grid.getAttribute("class") : null, vl: r(vl), rows: document.querySelectorAll('[aria-label="Dòng tin"] [role="listitem"]').length, upEl: (() => { const e = document.querySelector("#main .up, #main .chip.up"); return e ? [e.className, getComputedStyle(e).color, e.textContent.slice(0, 20)] : null; })(), downEl: (() => { const e = document.querySelector("#main .down, #main .chip.down"); return e ? [e.className, getComputedStyle(e).color, e.textContent.slice(0, 20)] : null; })(), main: r(document.querySelector("#main")), page: r(document.querySelector("#main .page")) };
}), null, 1));
await browser.close();
