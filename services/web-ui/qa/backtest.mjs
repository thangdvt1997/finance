// QA tab "Backtest" của trang Kịch bản (#/kich-ban): 1366 + 375, sáng/tối, tràn ngang, ảnh tải được, tải CSV, cột không lộ tên nguồn.
import { chromium } from "playwright";
import fs from "node:fs";
const BASE = process.env.BASE || "http://127.0.0.1:8580", OUT = process.env.OUT || "out";
fs.mkdirSync(OUT, { recursive: true });
const browser = await chromium.launch();
const res = []; const errs = [];
for (const [w, h] of [[1366, 768], [375, 800]]) for (const th of ["dark", "light"]) {
  const ctx = await browser.newContext({ viewport: { width: w, height: h }, colorScheme: th, baseURL: BASE, acceptDownloads: true });
  const r = await ctx.request.post(`${BASE}/auth/login`, { data: { platform: "master", login: process.env.QA_USER, secret: process.env.QA_PASS }, headers: { Origin: BASE, "Content-Type": "application/json" } });
  await ctx.addInitScript((t) => { try { const v = JSON.parse(localStorage.getItem("ts-ux") || "{}"); v.onboarded = 99; localStorage.setItem("ts-ux", JSON.stringify(v)); localStorage.setItem("ts-theme", t); sessionStorage.setItem("sc.tab", "backtest"); } catch { /* bỏ */ } }, th);
  const page = await ctx.newPage(); page.setDefaultTimeout(10000);
  page.on("pageerror", (e) => errs.push(String(e.message).slice(0, 200)));
  await page.goto(`${BASE}/#/kich-ban`, { waitUntil: "load" }); await page.waitForTimeout(3500);
  await page.getByRole("tab", { name: /Backtest/ }).click().catch(() => {}); await page.waitForTimeout(2500);
  const info = await page.evaluate(() => ({
    rows: document.querySelectorAll("table tbody tr").length, imgs: document.querySelectorAll(".sc-fig img").length,
    broken: [...document.querySelectorAll(".sc-fig img")].filter((i) => i.complete && i.naturalWidth === 0).length,
    overflow: document.documentElement.scrollWidth > innerWidth + 1, offender: (() => { const o = [...document.querySelectorAll('body *')].filter((e) => e.getBoundingClientRect().right > innerWidth + 1 && !e.closest('table,.overflow-x-auto,[class*=scroll]')).slice(0, 3); return o.map((e) => e.tagName + '.' + String(e.className).slice(0, 50)); })(), verdict: /Không có edge sau chi phí/.test(document.body.innerText),
    leak: /binance|yahoo|metaquotes|twelve|mt5/i.test(document.body.innerText),
  }));
  await page.screenshot({ path: `${OUT}/backtest-${w}-${th}.png`, fullPage: false });
  await page.screenshot({ path: `${OUT}/backtest-${w}-${th}-full.png`, fullPage: true }).catch(() => {});
  let dl = null;
  if (w === 1366 && th === "dark") {
    const [d] = await Promise.all([page.waitForEvent("download"), page.getByRole("link", { name: /ledger_summary\.csv/ }).click()]);
    const p = `${OUT}/${d.suggestedFilename()}`; await d.saveAs(p); dl = { name: d.suggestedFilename(), size: fs.statSync(p).size, head: fs.readFileSync(p, "utf8").split("\n")[0] };
    const [d2] = await Promise.all([page.waitForEvent("download"), page.getByRole("link", { name: /ledger_test\.csv\.gz/ }).click()]);
    dl.gz = d2.suggestedFilename();
  }
  res.push({ w, th, login: r.status(), ...info, dl }); console.log(JSON.stringify(res.at(-1)));
  await ctx.close();
}
console.log("errors", JSON.stringify(errs));
fs.writeFileSync(`${OUT}/results.json`, JSON.stringify({ res, errs }, null, 1));
await browser.close();
