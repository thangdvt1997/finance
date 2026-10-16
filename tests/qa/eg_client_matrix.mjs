// QA E (client-ui PWA): ma trận trang x 4 độ phân giải x sáng/tối x vi/en với auth THẬT (tài khoản thử). Chạy bằng eg_client_matrix.sh.
// Kiểm: lỗi console/pageerror, request /c/api|/c/auth 4xx/5xx (trừ 401/404 có chủ đích), NaN/undefined/[object, tên nguồn dữ liệu, panel kẹt loading, tràn ngang.
import { chromium } from "playwright";
import fs from "node:fs";

const BASE = process.env.BASE || "http://127.0.0.1:8581/c/";
const OUT = process.env.OUT || "out";
const USER = process.env.QA_USER, PASS = process.env.QA_PASS;
const VIEWS_ALL = [["375x812", 375, 812, true], ["414x896", 414, 896, true], ["768x1024", 768, 1024, true], ["1366x768", 1366, 768, false]];
const VIEWS = process.env.VIEWS ? VIEWS_ALL.filter((v) => process.env.VIEWS.split(",").includes(v[0])) : VIEWS_ALL;
const THEMES = (process.env.THEMES || "light,dark").split(",");
const LANGS = (process.env.LANGS || "vi,en").split(",");
const PAGES = ["hom-nay", "vi-the", "thi-truong", "nhat-ky", "tong-quan", "gioi-han", "rui-ro", "danh-muc", "tin-lich", "ban-tin", "tin-hieu", "kich-ban", "ai-trading", "chuyen-gia", "bao-cao", "canh-bao", "thong-bao", "ho-so", "tro-giup"];
fs.mkdirSync(OUT, { recursive: true });
const BANNED = /(?<![\p{L}\p{N}_])(dukascopy|frankfurter|yahoo|vnstock|vndirect|okx|kucoin|binance|bybit|coinbase|kraken|ccxt|alpaca|tiingo|oanda|truefx|gdelt|reuters|cafef|vnexpress|myfxbook|forexfactory|stooq|twelvedata|finnhub|alphavantage|polygon|faireconomy)(?![\p{L}\p{N}_])/iu;
const NEWPW = `Qa-Stab-${Math.random().toString(36).slice(2, 8)}-${Date.now() % 1000}x!`;

const AUDIT = (mobile) => {
  const vw = document.documentElement.clientWidth; const issues = [];
  if (document.documentElement.scrollWidth > vw + 1) issues.push({ k: "page-overflow-x", d: `scrollWidth ${document.documentElement.scrollWidth} > ${vw}` });
  const txt = (document.querySelector("main") || document.body).innerText || "";
  for (const m of txt.matchAll(/\b(NaN|undefined|\[object Object\]|Infinity)\b/g)) issues.push({ k: "bad-text", d: m[0] });
  if (document.querySelector('[role="status"][aria-label="Đang tải"],[role="status"][aria-label="Loading"]')) issues.push({ k: "stuck-loading", d: "còn skeleton/đang tải sau chờ" });
  if (!document.querySelector("main h1, main h2")) issues.push({ k: "no-heading", d: "không có tiêu đề trang" });
  const inScroller = (el) => { for (let p = el.parentElement; p; p = p.parentElement) { const o = getComputedStyle(p).overflowX; if ((o === "auto" || o === "scroll") && p.scrollWidth > p.clientWidth) return true; } return false; };
  let n = 0;
  for (const el of document.querySelectorAll("main *")) {
    const r = el.getBoundingClientRect(); const cs = getComputedStyle(el);
    if (!(r.width > 0 && r.height > 0) || cs.visibility === "hidden" || cs.display === "none" || inScroller(el)) continue;
    if ((r.right > vw + 1 || r.left < -1) && n++ < 6) issues.push({ k: "out-of-viewport", d: `${el.tagName.toLowerCase()}.${String(el.className).slice(0, 30)} [${Math.round(r.left)}..${Math.round(r.right)}] vw=${vw}` });
  }
  return { issues, txt };
};
const waitIdle = async (page) => {
  await page.waitForSelector('[role="status"][aria-label="Đang tải"], [role="status"][aria-label="Loading"]', { state: "detached", timeout: 15000 }).catch(() => {});
  await page.waitForTimeout(600);
};

const report = []; let state = null;
const browser = await chromium.launch();
// 0) đăng nhập lần đầu, đổi passcode, lưu phiên
{
  const ctx = await browser.newContext({ viewport: { width: 1366, height: 768 }, locale: "vi-VN" });
  const page = await ctx.newPage();
  await page.goto(BASE); await page.waitForSelector("form"); await page.waitForTimeout(2500);
  for (let i = 0; i < 4; i++) {
    await page.fill('input[autocomplete="username"]', USER); await page.fill('input[autocomplete="current-password"]', PASS);
    if ((await page.inputValue('input[autocomplete="username"]')) === USER) break; await page.waitForTimeout(1500);
  }
  await page.click('button[type="submit"]');
  await page.waitForSelector("text=Cần đổi mật khẩu cổng", { timeout: 40000 }).catch(async (e) => { await page.screenshot({ path: `${OUT}/login-fail.jpg` }); console.log("ALERT:", await page.locator('[role="alert"]').allInnerTexts(), "LOGIN FAIL:", (await page.innerText("body")).slice(300, 900), "PWLEN", PASS.length); throw e; });
  await page.waitForTimeout(800);
  const pw = page.locator('input[type="password"]'); await pw.nth(0).fill(PASS); await pw.nth(1).fill(NEWPW); await pw.nth(2).fill(NEWPW);
  await page.click('button:has-text("Đổi mật khẩu")');
  await page.waitForSelector("main#main-content", { timeout: 40000 });
  state = await ctx.storageState(); await ctx.close();
  console.log("PASS login + đổi passcode lần đầu");
}
for (const lang of LANGS) for (const [vname, w, h, mobile] of VIEWS) for (const theme of THEMES) {
  const ctx = await browser.newContext({ storageState: state, viewport: { width: w, height: h }, deviceScaleFactor: 1, isMobile: mobile, hasTouch: mobile, colorScheme: theme, locale: lang === "en" ? "en-GB" : "vi-VN", timezoneId: "Asia/Ho_Chi_Minh" });
  await ctx.addInitScript(([t, l]) => { try { localStorage.setItem("tc-theme", t); localStorage.setItem("tc-prefs", JSON.stringify({ theme: t, lang: l, onboarded: true })); } catch {} }, [theme, lang]);
  const page = await ctx.newPage(); let cur = "boot"; const errs = [];
  page.on("console", (m) => { if (m.type() === "error") errs.push(`[${cur}] console: ${m.text().slice(0, 160)}`); });
  page.on("pageerror", (e) => errs.push(`[${cur}] pageerror: ${e.message.slice(0, 160)}`));
  page.on("response", (r) => { const u = r.url(); const s = r.status(); if (/\/c\/(api|auth)\//.test(u) && s >= 400 && ![401].includes(s)) errs.push(`[${cur}] HTTP ${s} ${u.replace(/^https?:\/\/[^/]+/, "").slice(0, 90)}`); });
  await page.goto(BASE); await page.waitForSelector("main#main-content", { timeout: 20000 }).catch(() => errs.push("[boot] không vào được app"));
  for (const p of PAGES) {
    cur = p;
    await page.evaluate((x) => { location.hash = `#/${x}`; }, p); await page.waitForTimeout(300); await waitIdle(page);
    const { issues, txt } = await page.evaluate(AUDIT, mobile);
    const bm = txt.match(BANNED); if (bm) issues.push({ k: "source-name", d: bm[0] });
    if (/\/c\/#\/|login/i.test(page.url()) && await page.isVisible("form").catch(() => false)) issues.push({ k: "logged-out", d: "bị đẩy ra đăng nhập" });
    if (process.env.SHOTS === "1" || issues.length) await page.screenshot({ path: `${OUT}/${lang}-${vname}-${theme}-${p}.jpg`, type: "jpeg", quality: 60, fullPage: false }).catch(() => {});
    report.push({ lang, view: vname, theme, page: p, issues });
  }
  report.push({ lang, view: vname, theme, page: "_console", issues: errs.map((d) => ({ k: "console", d })) });
  console.log(`done ${lang} ${vname} ${theme}`);
  await ctx.close();
}
// menu Thêm / sheet tài khoản (mobile) + đổi ngôn ngữ trực tiếp từ Hồ sơ
await browser.close();
fs.writeFileSync(`${OUT}/matrix.json`, JSON.stringify(report, null, 1));
const bad = report.filter((r) => r.issues.length);
console.log(`Trang kiểm tra: ${report.length}; có vấn đề: ${bad.length}`);
const agg = new Map();
for (const r of bad) for (const i of r.issues) { const key = `${i.k} | ${r.page} | ${String(i.d).replace(/\d+/g, "N").slice(0, 100)}`; agg.set(key, (agg.get(key) || 0) + 1); }
for (const [k, n] of [...agg].sort((a, b) => b[1] - a[1])) console.log(`${n}x ${k}`);
