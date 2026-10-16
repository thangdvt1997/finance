// QA trực quan trang Chuyên gia (track record) + widget + (tuỳ chọn) client-ui. Chạy bằng qa/run_expert.sh trên VPS.
// MOCK=1 (mặc định): dùng dữ liệu mẫu (?mockexp=1). MOCK=0: gọi API thật qua gateway. Ảnh -> out/
import { chromium } from "playwright";
import fs from "node:fs";

const BASE = process.env.BASE || "http://127.0.0.1:8580";
const OUT = process.env.OUT || "out";
const MOCK = process.env.MOCK !== "0";
const TAG = process.env.TAG || (MOCK ? "mock" : "live");
const USER = process.env.QA_USER, PASS = process.env.QA_PASS;
fs.mkdirSync(OUT, { recursive: true });
const results = { steps: [], errors: [], audits: {} };
const log = (k, v) => { results.steps.push({ k, v }); console.log(k, JSON.stringify(v)); };
const browser = await chromium.launch();

async function mk(w, h, scheme) {
  const ctx = await browser.newContext({ viewport: { width: w, height: h }, colorScheme: scheme, baseURL: BASE, ignoreHTTPSErrors: true });
  let r;
  for (let i = 0; i < 5; i++) {
    try { r = await ctx.request.post(`${BASE}/auth/login`, { data: { platform: "master", login: USER, secret: PASS }, headers: { Origin: BASE, "Content-Type": "application/json" } }); if (r.ok()) break; } catch { /* thử lại */ }
    await new Promise((res) => setTimeout(res, 3000));
  }
  log("login", r.status());
  await ctx.addInitScript(() => { try { const k = "ts-ux"; const v = JSON.parse(localStorage.getItem(k) || "{}"); v.onboarded = 99; localStorage.setItem(k, JSON.stringify(v)); } catch { /* bỏ */ } });
  const page = await ctx.newPage();
  page.setDefaultTimeout(8000);
  await page.route("**/api/v1/user/prefs", (route) => (route.request().method() === "PUT" ? route.abort() : route.continue())); // không ghi prefs dùng chung
  page.on("pageerror", (e) => results.errors.push(`pageerror: ${String(e.stack || e.message).slice(0, 500)}`));
  page.on("console", (m) => { if (m.type() === "error") results.errors.push(`console: ${m.text().slice(0, 240)}`); });
  page.on("response", (x) => { if (x.status() >= 400 && /experts/.test(x.url())) results.errors.push(`http ${x.status()} ${x.url().replace(BASE, "").slice(0, 100)}`); });
  return { ctx, page };
}

const AUDIT = () => {
  const vw = document.documentElement.clientWidth;
  const banned = /dukascopy|yahoo|binance|frankfurter|vnstock|reuters|forexfactory|cafef|okx|bybit|tiingo|myfxbook|zulutrade|tradingview|investing\.com|https?:\/\//i;
  const t = document.body.innerText;
  return {
    overflowX: document.documentElement.scrollWidth > vw + 1,
    banned: banned.test(t) ? t.match(banned)[0] : null,
    wide: [...document.querySelectorAll("body *")].filter((e) => { const r = e.getBoundingClientRect(); return r.width > 0 && r.right > vw + 1 && !e.closest(".scroll-x,.react-grid-layout,.tm-scroll,[class*=overflow]"); }).slice(0, 6).map((e) => `${e.tagName.toLowerCase()}.${String(e.className).slice(0, 40)} r=${Math.round(e.getBoundingClientRect().right)}`),
    small: [...document.querySelectorAll("button,a,[role=tab],select")].filter((e) => { const r = e.getBoundingClientRect(); return r.width > 0 && (r.height < 24 || r.width < 24); }).length,
    unlabeledBtn: [...document.querySelectorAll("button")].filter((e) => !(e.innerText || e.getAttribute("aria-label") || e.title || "").trim()).length,
  };
};

const url = (hash) => `${BASE}/${MOCK ? "?mockexp=1" : ""}#/${hash}`;
const setTheme = (page, th) => page.evaluate((x) => { document.documentElement.dataset.theme = x; }, th);

const VIEWS = [["desk", 1440, 900], ["mob", 375, 812]];
for (const scheme of ["dark", "light"]) {
  for (const [vn, w, h] of VIEWS) {
    const { ctx, page } = await mk(w, h, scheme);
    const name = `${TAG}-${scheme}-${vn}`;
    await page.goto(url("chuyen-gia"), { waitUntil: "networkidle" }).catch(() => {});
    await setTheme(page, scheme);
    await page.waitForTimeout(1800);
    log(`${name}-text`, (await page.evaluate(() => document.body.innerText)).slice(0, 260).replace(/\n+/g, " | "));
    await page.screenshot({ path: `${OUT}/${name}-board.png` });
    results.audits[`${name}-board`] = await page.evaluate(AUDIT);
    // chi tiết chuyên gia
    const link = page.locator(".xp-link").first();
    if (await link.count()) {
      await link.click();
      await page.waitForTimeout(1500);
      await page.hover('[role="dialog"] .xp-chart svg').catch(() => {});
      await page.screenshot({ path: `${OUT}/${name}-detail-top.png` });
      await page.evaluate(() => { const d = document.querySelector('[role="dialog"] .overflow-y-auto'); if (d) d.scrollTop = 700; });
      await page.waitForTimeout(500);
      await page.screenshot({ path: `${OUT}/${name}-detail-mid.png` });
      await page.evaluate(() => { const d = document.querySelector('[role="dialog"] .overflow-y-auto'); if (d) d.scrollTop = 99999; });
      await page.waitForTimeout(500);
      await page.screenshot({ path: `${OUT}/${name}-detail-end.png` });
      results.audits[`${name}-detail`] = await page.evaluate(AUDIT);
      await page.keyboard.press("Escape");
      await page.waitForTimeout(300);
    } else log(`${name}-no-expert-link`, true);
    // bộ lọc: ẩn chưa đủ mẫu
    await page.getByLabel("Hiện nhóm chưa đủ mẫu").uncheck().catch(() => {});
    await page.waitForTimeout(900);
    await page.screenshot({ path: `${OUT}/${name}-board-hide-insuf.png` });
    await page.getByLabel("Hiện nhóm chưa đủ mẫu").check().catch(() => {});
    // đồng thuận
    await page.getByRole("button", { name: "Bản đồ đồng thuận" }).click().catch(() => {});
    await page.waitForTimeout(1200);
    await page.locator(".xp-cs-btn").first().click().catch(() => {});
    await page.waitForTimeout(400);
    await page.screenshot({ path: `${OUT}/${name}-consensus.png` });
    results.audits[`${name}-consensus`] = await page.evaluate(AUDIT);
    // quan điểm mới
    await page.getByRole("button", { name: "Quan điểm mới" }).click().catch(() => {});
    await page.waitForTimeout(1200);
    await page.screenshot({ path: `${OUT}/${name}-feed.png` });
    // phương pháp
    await page.getByRole("button", { name: "Phương pháp" }).first().click().catch(() => {});
    await page.waitForTimeout(900);
    await page.screenshot({ path: `${OUT}/${name}-method.png` });
    await ctx.close();
  }
}

// widget trong Terminal (prefs chỉ lưu cục bộ vì chặn PUT)
{
  const { ctx, page } = await mk(1440, 900, "dark");
  await page.goto(url("terminal"), { waitUntil: "networkidle" }).catch(() => {});
  await page.waitForTimeout(2500);
  for (const nm of ["Đồng thuận chuyên gia", "Quan điểm chuyên gia"]) {
    try {
      await page.getByRole("button", { name: "Thêm widget" }).first().click();
      await page.waitForTimeout(400);
      await page.getByRole("dialog").getByText(nm, { exact: false }).first().click();
      await page.waitForTimeout(1800);
      log(`widget-${nm}`, "added");
    } catch (e) { log(`widget-${nm}`, `FAIL ${String(e.message).split("\n")[0].slice(0, 140)}`); await page.keyboard.press("Escape"); }
  }
  await page.screenshot({ path: `${OUT}/${TAG}-widgets.png` });
  for (const [i, nm] of ["Đồng thuận chuyên gia", "Quan điểm chuyên gia"].entries()) {
    const el = page.locator(".tm-w", { hasText: nm }).first();
    if (await el.count()) { await el.scrollIntoViewIfNeeded(); await page.waitForTimeout(400); await el.screenshot({ path: `${OUT}/${TAG}-widget-${i}.png` }); }
  }
  const w = await page.evaluate(() => [...document.querySelectorAll(".tm-w")].filter((e) => /Đồng thuận chuyên gia|Quan điểm chuyên gia/.test(e.innerText)).map((e) => e.innerText.slice(0, 160).replace(/\n+/g, " | ")));
  log("widgets", w);
  await ctx.close();
}

log("errors", results.errors.slice(0, 12));
fs.writeFileSync(`${OUT}/results-${TAG}.json`, JSON.stringify(results, null, 1));
await browser.close();
