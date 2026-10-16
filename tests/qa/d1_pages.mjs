// D1: quét MỌI trang master bằng Playwright (chạy qua tests/qa/d1_run.sh). Ma trận: 4 độ phân giải x (tối+vi | sáng+en).
// Kiểm: lỗi console/pageerror, request 4xx/5xx, tràn ngang, NaN/undefined, kẹt loading, lộ tên nguồn dữ liệu.
import { chromium } from "playwright";
import fs from "node:fs";
const BASE = process.env.BASE || "http://127.0.0.1:8580", OUT = process.env.OUT || "out";
fs.mkdirSync(OUT, { recursive: true });
const PAGES = ["tong-quan","chung-khoan-vn","danh-sach","phan-tich","ban-tin","tin-tuc","lich","chuyen-gia","tai-khoan","mo-phong","nhat-ky","canh-bao","bao-cao","khach-hang","he-thong","doi-tai-khoan","luat","su-co","vai-tro","phien-thiet-bi","kiem-toan","bao-cao-khach","cai-dat","tro-giup","du-lieu","phien-giao-dich","suc-manh-tien-te","movers","ban-do-nhiet","nhip-thi-truong","vi-the-lon","tuong-quan-rui-ro","kich-ban","gioi-thieu","design"];
const RES = (process.env.RES ? process.env.RES.split(",").map((s) => s.split("x").map(Number)) : [[1920,1080],[1366,768],[768,1024],[390,844]]);
const COMBOS = process.env.COMBO ? [process.env.COMBO.split("-")] : [["dark","vi"],["light","en"]];
const only = process.env.ONLY ? process.env.ONLY.split(",") : null;
const SRC = /binance|yahoo|twelve ?data|finnhub|alpha ?vantage|stooq|coingecko|fred\b|polygon|investing\.com|vnstock|tcbs/i;
const results = [];
const BAD_TXT = /\bNaN\b|\bundefined\b|\[object Object\]|\bInfinity\b|\bnull\b(?!\s*:)/;
const H = { Origin: BASE, "Content-Type": "application/json" };
const browser = await chromium.launch();
for (const [w, h] of RES) for (const [theme, loc] of COMBOS) {
  const ctx = await browser.newContext({ viewport: { width: w, height: h }, baseURL: BASE, ...(w < 500 ? { isMobile: true, hasTouch: true } : {}) });
  await ctx.addInitScript(([t, l]) => { try { localStorage.setItem("ts-ux", JSON.stringify({ onboarded: 99, theme: t, numFmt: l, dateFmt: l, t: 0 })); } catch {} }, [theme, loc]);
  let r; for (let i = 0; i < 20; i++) { try { r = await ctx.request.post(`${BASE}/auth/login`, { data: { platform: "master", login: process.env.QA_USER, secret: process.env.QA_PASS }, headers: H }); if (r.status() === 429) { await new Promise((z) => setTimeout(z, 30000)); continue; } break; } catch { await new Promise((z) => setTimeout(z, 4000)); } }
  if (r.status() !== 200) { console.log("LOGIN FAIL", r.status()); process.exit(2); }
  const page = await ctx.newPage(); page.setDefaultTimeout(9000);
  let errs = [], bad = [];
  page.on("pageerror", (e) => errs.push("pageerror: " + String(e.message).slice(0, 200)));
  page.on("console", (m) => { if (m.type() === "error") errs.push("console: " + m.text().slice(0, 200)); });
  page.on("response", (x) => { const s = x.status(); if (s >= 400 && !/sw\.js|favicon/.test(x.url())) bad.push(`${s} ${x.request().method()} ${x.url().replace(BASE, "").slice(0, 90)}`); });
  await page.goto(`${BASE}/#/tong-quan`, { waitUntil: "domcontentloaded" }).catch(() => {});
  await page.waitForTimeout(1500);
  for (const p of PAGES) {
    if (only && !only.includes(p)) continue;
    errs = []; bad = [];
    const t0 = Date.now();
    await page.evaluate((x) => { location.hash = "#/" + x; }, p);
    await page.waitForTimeout(3500);
    const info = await page.evaluate(() => {
      const de = document.documentElement, vw = de.clientWidth;
      const main = document.querySelector("main") || document.body;
      const txt = main.innerText || "";
      const over = [];
      for (const el of main.querySelectorAll("*")) {
        const b = el.getBoundingClientRect(); if (!b.width || !b.height) continue;
        if (b.right > vw + 2 && !el.closest("[class*=scroll],[class*=overflow],table,pre,.recharts-wrapper,svg,canvas")) { over.push((el.tagName + "." + String(el.className).slice(0, 40))); if (over.length > 4) break; }
      }
      const loading = [...main.querySelectorAll("[class*=skeleton],[aria-busy=true],[class*=spinner]")].filter((e) => e.getBoundingClientRect().height > 0).length;
      return { hscroll: de.scrollWidth - vw, over, txt, loading, title: document.title, boundary: !!document.querySelector("[role=alert]") && /Không hiển thị được/.test(txt), len: txt.length };
    }).catch((e) => ({ txt: "", err: String(e) }));
    const issues = [];
    if (info.boundary) issues.push("ErrorBoundary");
    if (info.hscroll > 2) issues.push("hscroll+" + info.hscroll);
    if (info.over?.length) issues.push("overflow:" + info.over.join("|"));
    const m = info.txt.match(BAD_TXT); if (m) issues.push("bad-text:" + m[0] + "@" + info.txt.slice(Math.max(0, info.txt.search(BAD_TXT) - 30), info.txt.search(BAD_TXT) + 30).replace(/\s+/g, " "));
    const sm = info.txt.match(SRC); if (sm) issues.push("source-name:" + sm[0]);
    if (info.loading > 0) { await page.waitForTimeout(5000); const still = await page.evaluate(() => [...document.querySelectorAll("[class*=skeleton],[aria-busy=true],[class*=spinner]")].filter((e) => e.getBoundingClientRect().height > 0).length); if (still) issues.push("stuck-loading:" + still); }
    if (info.len < 40) issues.push("empty-page");
    for (const e of errs) issues.push(e); for (const b of bad) issues.push("http " + b);
    const key = `${p}@${w}x${h}-${theme}-${loc}`;
    results.push({ key, issues });
    if (issues.length) { console.log("ISSUE", key, JSON.stringify(issues)); await page.screenshot({ path: `${OUT}/${key}.png` }).catch(() => {}); }
  }
  await ctx.close();
  console.log("done combo", w, h, theme, loc);
}
await browser.close();
fs.writeFileSync(`${OUT}/d1_results.json`, JSON.stringify(results, null, 1));
console.log("TOTAL", results.length, "WITH_ISSUES", results.filter((x) => x.issues.length).length);
