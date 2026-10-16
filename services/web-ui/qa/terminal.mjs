// QA trực quan trang Terminal (chạy trong container Playwright trên VPS qua run.sh). Ảnh -> out/, kết quả -> out/results.json
import { chromium } from "playwright";
import fs from "node:fs";

const BASE = process.env.BASE || "http://127.0.0.1:8580";
const OUT = process.env.OUT || "out";
const USER = process.env.QA_USER, PASS = process.env.QA_PASS;
const ONLY = process.env.ONLY ? process.env.ONLY.split(",") : null;
fs.mkdirSync(OUT, { recursive: true });
const results = { steps: [], errors: [], views: {} };
const log = (k, v) => { results.steps.push({ k, v }); console.log(k, JSON.stringify(v)); };

const browser = await chromium.launch();
const mk = async (w, h, scheme = "dark") => {
  const ctx = await browser.newContext({ viewport: { width: w, height: h }, colorScheme: scheme, deviceScaleFactor: 1, baseURL: BASE, ignoreHTTPSErrors: true, extraHTTPHeaders: {} });
  let r;
  for (let i = 0; i < 5; i++) {
    try { r = await ctx.request.post(`${BASE}/auth/login`, { data: { platform: "master", login: USER, secret: PASS }, headers: { Origin: BASE, "Content-Type": "application/json" } }); if (r.ok()) break; } catch { /* máy chủ đang khởi động lại: thử lại */ }
    await new Promise((res) => setTimeout(res, 4000));
  }
  log("login", [r.status(), (await r.text()).slice(0, 120)]);
  await ctx.addInitScript(() => { try { const k = "ts-ux"; const v = JSON.parse(localStorage.getItem(k) || "{}"); v.onboarded = 99; localStorage.setItem(k, JSON.stringify(v)); } catch { /* bỏ */ } });
  const page = await ctx.newPage();
  page.setDefaultTimeout(8000);
  page.on("pageerror", (e) => results.errors.push(`pageerror: ${String(e.stack || e.message).slice(0, 700)}`));
  page.on("response", (r) => { if (r.status() >= 400 && !/favicon/.test(r.url())) results.bad = [...(results.bad || []), `${r.status()} ${r.request().method()} ${r.url().replace(BASE, "").slice(0, 90)}`].slice(-30); });
  page.on("console", (m) => { if (m.type() === "error") results.errors.push(`console: ${m.text().slice(0, 300)} @${m.location().url.replace(BASE, "")}:${m.location().lineNumber}`); });
  return { ctx, page };
};

const AUDIT = () => {
  const vw = document.documentElement.clientWidth;
  const out = { overflowX: document.documentElement.scrollWidth > vw + 1, widgets: document.querySelectorAll(".tm-w").length, titles: [...document.querySelectorAll(".tm-wt")].map((e) => e.textContent.trim().slice(0, 40)), tabs: [...document.querySelectorAll(".tm-tab")].map((e) => e.textContent.trim()) };
  const banned = /dukascopy|yahoo|binance|frankfurter|vnstock|reuters|forexfactory|cafef|okx|bybit|tiingo/i;
  out.banned = banned.test(document.body.innerText) ? document.body.innerText.match(banned)[0] : null;
  out.wide = [...document.querySelectorAll("body *")].filter((e) => { const r = e.getBoundingClientRect(); return r.width > 0 && r.right > vw + 1 && !e.closest(".react-grid-layout") ; }).slice(0, 5).map((e) => `${e.tagName.toLowerCase()}.${String(e.className).slice(0, 50)} r=${Math.round(e.getBoundingClientRect().right)}`);
  out.overlap = 0;
  const items = [...document.querySelectorAll(".react-grid-item")].map((e) => e.getBoundingClientRect());
  for (let i = 0; i < items.length; i++) for (let j = i + 1; j < items.length; j++) { const a = items[i], b = items[j]; if (Math.min(a.right, b.right) - Math.max(a.left, b.left) > 2 && Math.min(a.bottom, b.bottom) - Math.max(a.top, b.top) > 2) out.overlap++; }
  return out;
};

// Tuỳ chọn người dùng (user_prefs) là DÙNG CHUNG cho mọi master -> QA phải khôi phục lại sau khi chạy (bỏ khoá `tm` do QA tạo)
let prefsBefore = null;
{
  const { ctx, page } = await mk(800, 600);
  await page.goto(`${BASE}/`, { waitUntil: "load" }).catch(() => {});
  for (let i = 0; i < 4 && !prefsBefore; i++) { prefsBefore = await page.evaluate(async () => { try { const r = await fetch("/api/v1/user/prefs", { credentials: "same-origin" }); return r.ok ? r.json() : null; } catch { return null; } }); if (!prefsBefore) await page.waitForTimeout(3000); }
  log("prefs-before", prefsBefore ? Object.keys(prefsBefore.prefs || {}) : null);
  await ctx.close();
}
const restorePrefs = async (tries = 0) => {
  if (!prefsBefore) return;
  const { ctx, page } = await mk(800, 600);
  await page.goto(`${BASE}/`, { waitUntil: "load" }).catch(() => {});
  const r = await page.evaluate(async (before) => {
    const cur = await (await fetch("/api/v1/user/prefs", { credentials: "same-origin" })).json();
    const t = (await (await fetch("/api/v1/user/csrf", { credentials: "same-origin" })).json()).token;
    const prefs = { ...before.prefs }; delete prefs.tm;
    const res = await fetch("/api/v1/user/prefs", { method: "PUT", credentials: "same-origin", headers: { "Content-Type": "application/json", "X-CSRF-Token": t }, body: JSON.stringify({ rev: cur.rev, prefs }) });
    return res.status;
  }, prefsBefore);
  if (r === 409 && tries < 5) { await ctx.close(); return restorePrefs(tries + 1); }
  log("prefs-restore", r);
  await ctx.close();
};

const views = [["1920x1080", 1920, 1080], ["1366x768", 1366, 768], ["768x1024", 768, 1024], ["375x812", 375, 812]].filter(([n]) => !ONLY || ONLY.includes(n));
try {
for (const [name, w, h] of views) {
  const { ctx, page } = await mk(w, h);
  await page.goto(`${BASE}/#/terminal`, { waitUntil: "networkidle" }).catch(() => {});
  await page.waitForTimeout(3500);
  log("url", [page.url(), (await page.evaluate(() => document.body.innerText)).slice(0, 160)]);
  await page.screenshot({ path: `${OUT}/terminal-${name}.png` });
  if (name === "1920x1080") log("prefs-api", await page.evaluate(async () => { try { const r = await fetch("/api/v1/user/prefs", { credentials: "same-origin" }); const t = await r.text(); return [r.status, t.slice(0, 160)]; } catch (e) { return String(e); } }));
  results.views[name] = await page.evaluate(AUDIT);
  log(`view-${name}`, results.views[name]);
  if (name === "1920x1080") {
    // ----- tương tác -----
    const step = async (label, fn) => { try { await fn(); log(label, "ok"); } catch (e) { log(label, `FAIL ${String(e.message).split("\n")[0].slice(0, 160)}`); await page.screenshot({ path: `${OUT}/fail-${label}.png` }).catch(() => {}); } };
    await step("tab-forex", async () => { await page.getByRole("tab", { name: "Forex" }).click(); await page.waitForTimeout(2500); await page.screenshot({ path: `${OUT}/ws-forex.png` }); log("forex", await page.evaluate(AUDIT)); });
    await step("tab-crypto", async () => { await page.getByRole("tab", { name: "Crypto" }).click(); await page.waitForTimeout(2500); await page.screenshot({ path: `${OUT}/ws-crypto.png` }); });
    await step("tab-vn", async () => { await page.getByRole("tab", { name: "Chứng khoán VN" }).click(); await page.waitForTimeout(2500); await page.screenshot({ path: `${OUT}/ws-vn.png` }); });
    await step("tab-news", async () => { await page.getByRole("tab", { name: "Tin & Lịch" }).click(); await page.waitForTimeout(2500); await page.screenshot({ path: `${OUT}/ws-news.png` }); });
    await step("tab-overview", async () => { await page.getByRole("tab", { name: "Tổng quan" }).click(); await page.waitForTimeout(1500); });
    await step("catalog", async () => { await page.getByRole("button", { name: "Thêm widget" }).first().click(); await page.waitForTimeout(600); await page.screenshot({ path: `${OUT}/catalog.png` }); await page.keyboard.press("Escape"); });
    await step("widget-menu", async () => { await page.locator('.tm-wh button[aria-label^="Menu widget"]').first().click(); await page.waitForTimeout(300); log("pop", await page.evaluate(() => { const e = document.querySelector(".tm-pop"); const r = e && e.getBoundingClientRect(); return { iw: innerWidth, cw: document.documentElement.clientWidth, rect: r && [r.left, r.top, r.width, r.height], style: e && e.getAttribute("style") }; })); await page.screenshot({ path: `${OUT}/widget-menu.png` }); await page.keyboard.press("Escape"); });
    await step("widget-config", async () => { await page.locator('.tm-wh button[aria-label^="Menu widget"]').first().click(); await page.getByRole("menuitem", { name: /Cấu hình/ }).click(); await page.waitForTimeout(500); await page.screenshot({ path: `${OUT}/config.png` }); await page.keyboard.press("Escape"); });
    await step("maximize", async () => { await page.locator('.tm-wh button[aria-label^="Menu widget"]').nth(1).click(); await page.getByRole("menuitem", { name: /Phóng to/ }).click(); await page.waitForTimeout(800); await page.screenshot({ path: `${OUT}/maximize.png` }); await page.keyboard.press("Escape"); await page.waitForTimeout(300); });
    await step("drag", async () => {
      const box = await page.locator(".tm-drag").nth(2).boundingBox();
      const before = await page.evaluate(() => [...document.querySelectorAll(".react-grid-item")].map((e) => e.style.transform).join("|"));
      await page.mouse.move(box.x + 60, box.y + 10); await page.mouse.down(); await page.mouse.move(box.x + 160, box.y + 90, { steps: 8 }); await page.mouse.up(); await page.waitForTimeout(600);
      const after = await page.evaluate(() => [...document.querySelectorAll(".react-grid-item")].map((e) => e.style.transform).join("|"));
      log("drag-changed", before !== after);
    });
    await step("lock", async () => { await page.getByRole("button", { name: /Khoá bố cục/ }).click(); await page.waitForTimeout(300); log("lock-state", await page.locator('button[aria-pressed="true"][aria-label*="Mở khoá"]').count()); await page.getByRole("button", { name: /Mở khoá bố cục/ }).click(); });
    await step("kiosk", async () => { await page.getByRole("button", { name: /toàn màn hình/i }).first().click(); await page.waitForTimeout(1200); await page.screenshot({ path: `${OUT}/kiosk.png` }); await page.keyboard.press("Escape"); await page.waitForTimeout(500); log("kiosk-exited", await page.evaluate(() => !document.documentElement.classList.contains("tm-kiosk"))); });
    await step("persist-reload", async () => { await page.reload({ waitUntil: "load" }); await page.waitForTimeout(2500); log("after-reload", await page.evaluate(AUDIT)); });
    await step("prefs-server", async () => { log("prefs-tm", await page.evaluate(async () => { try { const j = await (await fetch("/api/v1/user/prefs", { credentials: "same-origin" })).json(); const tm = j.prefs && j.prefs.tm; return tm ? { ws: tm.o, active: tm.a, widgets: Object.values(tm.w).map((w) => w.x.length) } : null; } catch (e) { return String(e); } })); });
    await step("all-widgets", async () => {
      await page.getByRole("button", { name: "Thêm workspace" }).click();
      await page.getByRole("menuitem", { name: /Trống/ }).click();
      await page.waitForTimeout(500);
      const n = await (async () => { await page.getByRole("button", { name: "Thêm widget" }).first().click(); await page.waitForTimeout(400); const c = await page.locator('[role="dialog"] ul li button').count(); await page.keyboard.press("Escape"); return c; })();
      log("catalog-count", n);
      for (let i = 0; i < n; i++) {
        await page.getByRole("button", { name: "Thêm widget" }).first().click();
        await page.waitForTimeout(250);
        await page.locator('[role="dialog"] ul li button').nth(i).click();
        await page.waitForTimeout(250);
      }
      await page.waitForTimeout(4000);
      await page.screenshot({ path: `${OUT}/all-widgets.png`, fullPage: false });
      log("all-widgets-audit", await page.evaluate(AUDIT));
      await page.evaluate(() => document.querySelector("#main")?.scrollTo(0, 99999));
      await page.waitForTimeout(500);
      await page.screenshot({ path: `${OUT}/all-widgets-2.png` });
    });
    await step("light", async () => { await page.emulateMedia({ colorScheme: "light" }); await page.evaluate(() => { document.documentElement.dataset.theme = "light"; }); await page.waitForTimeout(600); await page.screenshot({ path: `${OUT}/terminal-light.png` }); });
    await step("palette-nav", async () => { await page.keyboard.press("Control+k"); await page.waitForTimeout(400); await page.screenshot({ path: `${OUT}/palette.png` }); await page.keyboard.press("Escape"); });
    await step("sidebar-nav", async () => { await page.screenshot({ path: `${OUT}/sidebar.png`, clip: { x: 0, y: 0, width: 260, height: 800 } }); });
  }
  if (name === "1920x1080") { await ctx.close(); await restorePrefs(); continue; }
  await ctx.close();
}
} finally { try { await restorePrefs(); } catch (e) { log("prefs-restore-fail", String(e.message).slice(0, 100)); } }
fs.writeFileSync(`${OUT}/results.json`, JSON.stringify(results, null, 1));
console.log("ERRORS", JSON.stringify(results.errors.slice(0, 12)));
console.log("BAD", JSON.stringify(results.bad || []));
await browser.close();
