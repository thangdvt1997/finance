// QA lưu trữ workspace Terminal phía máy chủ: sửa -> đọc /v1/user/prefs thấy `tm` -> xoá localStorage -> tải lại -> bố cục vẫn còn (nguồn = máy chủ).
// Luôn khôi phục prefs (bỏ khoá tm) khi xong vì user_prefs dùng chung.
import { chromium } from "playwright";
import fs from "node:fs";

const BASE = process.env.BASE || "http://127.0.0.1:8580";
const OUT = process.env.OUT || "out";
fs.mkdirSync(OUT, { recursive: true });
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const browser = await chromium.launch();
const ctx = await browser.newContext({ viewport: { width: 1600, height: 900 }, baseURL: BASE });
await ctx.addInitScript(() => { try { const k = "ts-ux"; const v = JSON.parse(localStorage.getItem(k) || "{}"); v.onboarded = 99; localStorage.setItem(k, JSON.stringify(v)); } catch { /* bỏ */ } });
for (let i = 0; i < 6; i++) {
  try { const r = await ctx.request.post(`${BASE}/auth/login`, { data: { platform: "master", login: process.env.QA_USER, secret: process.env.QA_PASS }, headers: { Origin: BASE, "Content-Type": "application/json" } }); if (r.ok()) break; } catch { /* thử lại */ }
  await sleep(3000);
}
const page = await ctx.newPage();
page.setDefaultTimeout(10000);
const api = (fn, arg) => page.evaluate(fn, arg);
const getPrefs = () => api(async () => { for (let i = 0; i < 4; i++) { try { const r = await fetch("/api/v1/user/prefs", { credentials: "same-origin" }); if (r.ok) return r.json(); } catch { /* thử lại */ } await new Promise((x) => setTimeout(x, 2000)); } return null; });
let before = null, ok = true;
const check = (name, v) => { console.log(v ? "PASS" : "FAIL", name); if (!v) ok = false; };
try {
  await page.goto(`${BASE}/#/terminal`, { waitUntil: "load" });
  await sleep(3000);
  before = await getPrefs();
  console.log("prefs-before-keys", before && Object.keys(before.prefs));
  // 1) đổi: khoá bố cục + đổi tên workspace hiện tại
  await page.getByRole("tab", { name: "Forex" }).dblclick();
  const inp = page.locator('input[aria-label="Tên workspace"]');
  await inp.fill("Forex QA");
  await inp.press("Enter");
  await page.getByRole("button", { name: /Khoá bố cục/ }).click();
  await sleep(2500);
  const mid = await getPrefs();
  const tm = mid?.prefs?.tm;
  check("server có prefs.tm", !!tm && Array.isArray(tm.o) && tm.o.length >= 5);
  check("tên workspace lưu trên máy chủ", !!tm && Object.values(tm.w || {}).some((w) => w.n === "Forex QA" && w.l === true));
  // 2) xoá localStorage rồi tải lại: phải khôi phục từ máy chủ
  await page.evaluate(() => localStorage.removeItem("ts-tm1"));
  await page.reload({ waitUntil: "load" });
  await sleep(3500);
  const names = await page.evaluate(() => [...document.querySelectorAll(".tm-tab")].map((e) => e.textContent.trim()));
  console.log("tabs-after-reload", names);
  check("khôi phục từ máy chủ sau khi xoá localStorage", names.includes("Forex QA"));
  await page.screenshot({ path: `${OUT}/persist.png` });
} catch (e) {
  ok = false;
  console.log("ERROR", String(e.message).split("\n")[0]);
}
// khôi phục prefs
try {
  const r = await api(async (b) => {
    const cur = await (await fetch("/api/v1/user/prefs", { credentials: "same-origin" })).json();
    const t = (await (await fetch("/api/v1/user/csrf", { credentials: "same-origin" })).json()).token;
    const prefs = { ...(b ? b.prefs : cur.prefs) }; delete prefs.tm;
    const res = await fetch("/api/v1/user/prefs", { method: "PUT", credentials: "same-origin", headers: { "Content-Type": "application/json", "X-CSRF-Token": t }, body: JSON.stringify({ rev: cur.rev, prefs }) });
    return res.status;
  }, before);
  console.log("prefs-restore", r);
} catch (e) { console.log("restore-fail", String(e.message).split("\n")[0]); }
await browser.close();
process.exit(ok ? 0 : 1);
