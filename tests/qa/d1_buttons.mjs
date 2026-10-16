// D1: bấm thử các nút an toàn trên mọi trang master; ghi nút KHÔNG phản hồi (không đổi DOM/hash/request/dialog).
// Mọi request ghi (POST/PUT/PATCH/DELETE) bị chặn => không thay đổi dữ liệu thật. Kèm kiểm form Cài đặt lưu qua tải lại.
import { chromium } from "playwright";
import fs from "node:fs";
const BASE = process.env.BASE || "http://127.0.0.1:8580", OUT = process.env.OUT || "out";
fs.mkdirSync(OUT, { recursive: true });
const PAGES = ["tong-quan","chung-khoan-vn","danh-sach","phan-tich","ban-tin","tin-tuc","lich","chuyen-gia","tai-khoan","mo-phong","nhat-ky","canh-bao","bao-cao","khach-hang","he-thong","doi-tai-khoan","luat","su-co","vai-tro","phien-thiet-bi","kiem-toan","bao-cao-khach","cai-dat","tro-giup","du-lieu","phien-giao-dich","suc-manh-tien-te","movers","ban-do-nhiet","nhip-thi-truong","vi-the-lon","tuong-quan-rui-ro","kich-ban"];
const only = process.env.ONLY ? process.env.ONLY.split(",") : null;
const DANGER = /xo[aá]|delete|remove|reset|đăng xuất|logout|sign out|thu hồi|revoke|gửi|send|đặt lệnh|order|buy|sell|mua|bán|đóng|close|tắt|disable|khoá|khóa|lock|tạo|create|thêm|add|lưu|save|nhập|import|đổi mật|password|totp|2fa|kill|đăng xuất/i;
const ctx0 = await chromium.launch();
const ctx = await ctx0.newContext({ viewport: { width: 1366, height: 800 }, baseURL: BASE });
await ctx.addInitScript(() => { try { if (!localStorage.getItem("ts-ux")) localStorage.setItem("ts-ux", JSON.stringify({ onboarded: 99, theme: "dark", t: 0 })); } catch {} });
const H = { Origin: BASE, "Content-Type": "application/json" };
let lr; for (let i = 0; i < 5; i++) { try { lr = await ctx.request.post(`${BASE}/auth/login`, { data: { platform: "master", login: process.env.QA_USER, secret: process.env.QA_PASS }, headers: H }); break; } catch { await new Promise((z) => setTimeout(z, 4000)); } }
if (!lr || lr.status() !== 200) { console.log("LOGIN FAIL"); process.exit(2); }
await ctx.route("**/*", (r) => { const q = r.request(); if (["POST","PUT","PATCH","DELETE"].includes(q.method()) && !/\/auth\/login|\/rt\//.test(q.url())) { blocked++; return r.fulfill({ status: 200, contentType: "application/json", body: "{}" }); } return r.continue(); });
let blocked = 0;
const page = await ctx.newPage(); page.setDefaultTimeout(6000);
let reqs = 0; page.on("request", () => reqs++); page.on("dialog", (d) => { dlg++; d.dismiss().catch(() => {}); }); let dlg = 0;
const errs = []; page.on("pageerror", (e) => errs.push(String(e.message).slice(0, 160)));
const res = [];
await page.goto(`${BASE}/#/tong-quan`, { waitUntil: "domcontentloaded" }); await page.waitForTimeout(1500);
for (const p of PAGES) {
  if (only && !only.includes(p)) continue;
  await page.evaluate((x) => { location.hash = "#/" + x; }, p); await page.waitForTimeout(3000);
  const labels = await page.evaluate(() => [...document.querySelectorAll("main button, main [role=tab], main summary")].filter((b) => { const r = b.getBoundingClientRect(); return r.width > 0 && r.height > 0 && !b.disabled; }).map((b, i) => ({ i, t: (b.innerText || b.getAttribute("aria-label") || b.title || "").trim().slice(0, 40) })).slice(0, 25));
  const noop = [];
  for (const { i, t } of labels) {
    if (DANGER.test(t)) continue;
    const before = await page.evaluate(() => ({ h: location.hash, n: document.body.innerHTML.length, s: document.body.innerHTML.slice(0, 0) }));
    const r0 = reqs, d0 = dlg, e0 = errs.length;
    try {
      const ok = await page.evaluate((idx) => { const b = [...document.querySelectorAll("main button, main [role=tab], main summary")].filter((x) => { const r = x.getBoundingClientRect(); return r.width > 0 && r.height > 0 && !x.disabled; })[idx]; if (!b) return false; window.__m = 0; const mo = new MutationObserver((l) => { window.__m += l.length; }); mo.observe(document.body, { subtree: true, childList: true, attributes: true, characterData: true }); window.__mo = mo; b.click(); return true; }, i);
      if (!ok) continue;
      await page.waitForTimeout(700);
      const after = await page.evaluate(() => { window.__mo?.disconnect(); return { h: location.hash, m: window.__m || 0, ae: document.activeElement?.tagName }; });
      if (after.m === 0 && after.h === before.h && reqs === r0 && dlg === d0) noop.push(t || "(không nhãn)");
      if (errs.length > e0) noop.push("JS-ERR sau khi bấm '" + t + "': " + errs[errs.length - 1]);
    } catch (e) { noop.push("lỗi bấm '" + t + "': " + String(e.message).slice(0, 80)); }
    if ((await page.evaluate(() => location.hash)) !== "#/" + p) { await page.evaluate((x) => { location.hash = "#/" + x; }, p); await page.waitForTimeout(1500); }
  }
  res.push({ page: p, buttons: labels.length, noop });
  console.log(p, "buttons", labels.length, noop.length ? "NOOP/ERR: " + JSON.stringify(noop) : "ok");
}
// Form Cài đặt: đổi mật độ + tuỳ chọn, tải lại, kiểm vẫn giữ
if (!only || only.includes("cai-dat")) {
  await page.evaluate(() => { location.hash = "#/cai-dat"; }); await page.waitForTimeout(2500);
  await page.evaluate(() => { const s = JSON.parse(localStorage.getItem("ts-ux") || "{}"); s.density = "compact"; s.accent = "blue"; s.t = Date.now(); localStorage.setItem("ts-ux", JSON.stringify(s)); });
  await page.reload({ waitUntil: "domcontentloaded" }); await page.waitForTimeout(2500);
  const kept = await page.evaluate(() => ({ d: document.documentElement.dataset.density, ls: JSON.parse(localStorage.getItem("ts-ux") || "{}").density }));
  console.log("settings-persist", JSON.stringify(kept));
  res.push({ page: "cai-dat-persist", kept });
}
console.log("blocked-writes", blocked);
fs.writeFileSync(`${OUT}/d1_buttons.json`, JSON.stringify(res, null, 1));
await ctx0.close();
