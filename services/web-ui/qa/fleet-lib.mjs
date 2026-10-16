// Thư viện QA trực quan cho các trang quản trị đội tài khoản (chạy TRONG container Playwright trên VPS qua qa/fleet-pw.sh; KHÔNG chạy ở laptop).
// Dùng:  import { session, shot, totpEnable, checks } from "./fleet-lib.mjs";
import { chromium } from "playwright";
import crypto from "node:crypto";
import fs from "node:fs";

export const BASE = process.env.BASE || "http://127.0.0.1:8580";
export const OUT = process.env.OUT || "out";
export const USER = process.env.QA_USER;
export const PASS = process.env.QA_PASS;
fs.mkdirSync(OUT, { recursive: true });

function b32dec(s) { const A = "ABCDEFGHIJKLMNOPQRSTUVWXYZ234567"; let bits = ""; for (const c of s.replace(/=+$/, "").toUpperCase()) bits += A.indexOf(c).toString(2).padStart(5, "0"); const out = []; for (let i = 0; i + 8 <= bits.length; i += 8) out.push(parseInt(bits.slice(i, i + 8), 2)); return Buffer.from(out); }
export function totp(secret, t = Date.now()) {
  const c = Buffer.alloc(8); c.writeBigUInt64BE(BigInt(Math.floor(t / 30000)));
  const h = crypto.createHmac("sha1", b32dec(secret)).update(c).digest(); const o = h[19] & 15;
  return String(((h[o] & 127) << 24 | h[o + 1] << 16 | h[o + 2] << 8 | h[o + 3]) % 1e6).padStart(6, "0");
}
const H = { Origin: BASE, "Content-Type": "application/json" };

/** Đăng nhập master thử, trả {browser, ctx, page, errors, forbidden, req(method,path,body), close}. theme: "dark"|"light"; w,h: cỡ khung nhìn. */
export async function session({ theme = "dark", w = 1366, h = 800, mobile = false, user = USER, pass = PASS, secret = null } = {}) {
  const browser = await chromium.launch();
  const ctx = await browser.newContext({ viewport: { width: w, height: h }, baseURL: BASE, deviceScaleFactor: 1, ...(mobile ? { isMobile: true, hasTouch: true } : {}) });
  await ctx.addInitScript((t) => { try { localStorage.setItem("ts-ux", JSON.stringify({ onboarded: 99, theme: t })); } catch { /* bỏ */ } }, theme);
  const body = { platform: "master", login: user, secret: pass };
  if (secret) body.totp = totp(secret);
  const r = await ctx.request.post(`${BASE}/auth/login`, { data: body, headers: H });
  if (r.status() !== 200) console.log("LOGIN FAIL", r.status(), (await r.text()).slice(0, 200));
  const page = await ctx.newPage();
  page.setDefaultTimeout(9000);
  const errors = [], bad = [];
  page.on("pageerror", (e) => errors.push("pageerror: " + String(e.message).slice(0, 240)));
  page.on("console", (m) => { if (m.type() === "error") errors.push("console: " + m.text().slice(0, 240)); });
  page.on("response", (res) => { const s = res.status(); if (s >= 400 && !/\/(sw\.js|favicon)/.test(res.url())) bad.push(`${s} ${res.request().method()} ${res.url().replace(BASE, "").slice(0, 100)}`); });
  // gọi API NGAY TRONG trang (cookie phiên đúng như trình duyệt; tránh lệch cookie giữa ctx.request và trang sau khi bật TOTP)
  const req = async (method, path, data) => {
    if (page.url() === "about:blank") await page.goto(`${BASE}/auth/login`, { waitUntil: "domcontentloaded" }).catch(() => {});
    return page.evaluate(async ([m, p, d]) => {
      const r = await fetch(p, { method: m, credentials: "same-origin", headers: { Accept: "application/json", "Content-Type": "application/json" }, body: d === undefined ? undefined : JSON.stringify(d) });
      let j = null; try { j = await r.json(); } catch { /* không JSON */ }
      return { status: r.status, json: j };
    }, [method, path, data]);
  };
  return { browser, ctx, page, errors, bad, req, theme, close: () => browser.close() };
}

/** Bật TOTP cho phiên hiện tại (cần cho thao tác nhạy cảm). Trả secret base32 (chỉ giữ trong bộ nhớ tiến trình QA). */
export async function totpEnable(s) {
  const a = await s.req("POST", "/auth/totp/setup", {});
  const secret = a.json?.secret;
  if (!secret) throw new Error("totp setup lỗi " + a.status);
  let b = await s.req("POST", "/auth/totp/enable", { code: totp(secret) });
  if (b.status !== 200) { await new Promise((r) => setTimeout(r, 31000)); b = await s.req("POST", "/auth/totp/enable", { code: totp(secret) }); }
  if (b.status !== 200) throw new Error("totp enable lỗi " + b.status + JSON.stringify(b.json));
  return secret;
}

/** Ép giao diện sáng/tối (prefs lưu ở máy chủ dùng chung có thể ghi đè theme lúc tải). */
export async function setTheme(s, t) { s.theme = t; await s.page.evaluate((x) => { document.documentElement.dataset.theme = x; }, t).catch(() => {}); }
export async function go(s, hash, wait = 1800) { await s.page.goto(`${BASE}/#/${hash.replace(/^#?\/?/, "")}`, { waitUntil: "load" }).catch(() => {}); await s.page.waitForTimeout(wait); await setTheme(s, s.theme || "dark"); }
export async function shot(s, name) { await setTheme(s, s.theme || "dark"); await s.page.screenshot({ path: `${OUT}/${name}.png` }); console.log("shot", name); }

const BANNED = /dukascopy|yahoo|frankfurter|vnstock|vndirect|cafef|reuters|forexfactory|okx|kucoin|binance|bybit|coinbase|kraken|ccxt|alpaca|tiingo|polygon|finnhub/i;
/** Kiểm nhanh: tên nguồn trong DOM, tràn ngang trang, ảnh/nút thiếu nhãn. */
export async function checks(s, label) {
  const r = await s.page.evaluate((re) => {
    const txt = document.body.innerText;
    const m = new RegExp(re, "i").exec(txt);
    const doc = document.documentElement;
    const unl = [...document.querySelectorAll("button,a[href],input,select,textarea")].filter((e) => { const n = e.getAttribute("aria-label") || e.textContent?.trim() || e.getAttribute("title") || e.labels?.[0]?.textContent || e.getAttribute("placeholder"); return !n && e.offsetParent !== null; }).length;
    return { banned: m ? m[0] : null, hOverflow: doc.scrollWidth > doc.clientWidth + 2, unlabeled: unl };
  }, BANNED.source);
  console.log("check", label, JSON.stringify(r), "errors:", s.errors.length);
  return r;
}
export const fin = (s) => { console.log("errors", JSON.stringify(s.errors)); console.log("bad-http", JSON.stringify(s.bad)); };
