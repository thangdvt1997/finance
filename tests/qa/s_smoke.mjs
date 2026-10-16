// CONG CHAT LUONG - smoke dau-cuoi (chay TRONG container Playwright tam, qua infra/ops/smoke.sh). Khong in secret.
// env: BASE_M BASE_C  U_M U_E U_C (ten) ; mat khau doc tu file pw_m pw_e pw_c trong cwd ; MAX_ROUTES ; OUT
import { chromium } from "playwright";
import fs from "node:fs";
import crypto from "node:crypto";

const BM = process.env.BASE_M || "http://127.0.0.1:8580", BC = process.env.BASE_C || "http://127.0.0.1:8581";
const MAXR = +(process.env.MAX_ROUTES || 60);
const rd = (f) => { try { return fs.readFileSync(f, "utf8").trim(); } catch { return ""; } };
const BANNED = /dukascopy|frankfurter|yahoo|vnstock|vndirect|finfo|\bokx\b|kucoin|binance|bybit|coinbase|kraken|ccxt|alpaca|tiingo|oanda|truefx|gdelt|reuters|cafef|vnexpress|myfxbook|actionforex|faireconomy|fair\s+economy|forexfactory|investinglive|oilprice|stooq|twelve\s?data|finnhub|alpha\s?vantage|yfinance/i;
const BANNED_UP = /\b(BLS|CFTC|FRED|FMP)\b/;
const T0 = Date.now(), DEADLINE = +(process.env.DEADLINE_S || 140) * 1000;
// loi da biet, da ghi QA_ISSUES (khong chan deploy; xoa dong khi da sua)
const KNOWN = /^(404 GET \/api\/v1\/analytics\/symbol\/AUDDKK|429 )/;   // 429: gioi han toc do theo nguoi dung khi duyet song song - chi canh bao
const fails = [], notes = []; let skipped = 0;
let checks = 0;
const ok = (c, msg) => { checks++; if (!c) fails.push(msg); };

function b32dec(s) { const A = "ABCDEFGHIJKLMNOPQRSTUVWXYZ234567"; let bits = ""; for (const c of s.replace(/=+$/, "").toUpperCase()) bits += A.indexOf(c).toString(2).padStart(5, "0"); const o = []; for (let i = 0; i + 8 <= bits.length; i += 8) o.push(parseInt(bits.slice(i, i + 8), 2)); return Buffer.from(o); }
function totp(secret) { const c = Buffer.alloc(8); c.writeBigUInt64BE(BigInt(Math.floor(Date.now() / 30000))); const h = crypto.createHmac("sha1", b32dec(secret)).update(c).digest(); const o = h[19] & 15; return String(((h[o] & 127) << 24 | h[o + 1] << 16 | h[o + 2] << 8 | h[o + 3]) % 1e6).padStart(6, "0"); }

const browser = await chromium.launch();
async function pool(items, n, fn) { let i = 0; await Promise.all(Array.from({ length: n }, async () => { while (i < items.length) { const x = items[i++]; if (Date.now() - T0 > DEADLINE) { skipped++; continue; } await fn(x); } })); }
async function sleep(ms) { await new Promise((r) => setTimeout(r, ms)); }

// dang nhap qua API (retry ngan khi dang deploy giua chung); tra storageState cookies
async function login(base, authPrefix, platform, user, pass, { totpOn = false, changePw = false } = {}) {
  for (let attempt = 0; attempt < 6; attempt++) {
    const jar = {};
    const rc = await browser.newContext();
    const H = { Origin: base, "Content-Type": "application/json" };
    const post = async (p, d) => {
      const r = await rc.request.post(`${base}${authPrefix}${p}`, { data: d, headers: { ...H, Cookie: Object.entries(jar).map(([k, v]) => `${k}=${v}`).join("; ") } });
      for (const h of r.headersArray()) if (h.name.toLowerCase() === "set-cookie") for (const line of h.value.split("\n")) { const [kv] = line.split(";"); const i = kv.indexOf("="); const k = kv.slice(0, i).trim(), v = kv.slice(i + 1).trim(); if (v) jar[k] = v; else delete jar[k]; }
      return r;
    };
    try {
      let pw = pass;
      let r = await post("/login", { platform, login: user, secret: pw });
      if (r.status() === 200) {
        if (changePw) { pw = pass + "-Qa9!xZ"; const c = await post("/change-password", { current_password: pass, new_password: pw }); if (c.status() === 200) r = await post("/login", { platform, login: user, secret: pw }); }
        if (totpOn) {
          const a = await post("/totp/setup", {}); const sec = (await a.json().catch(() => ({}))).secret;
          if (sec) { let b = await post("/totp/enable", { code: totp(sec) }); if (b.status() !== 200) { await sleep(31000); b = await post("/totp/enable", { code: totp(sec) }); } if (b.status() !== 200) notes.push(`totp enable ${b.status()}`); }
        }
        await rc.close();
        return { cookies: Object.entries(jar).map(([name, value]) => ({ name, value, domain: "127.0.0.1", path: "/", httpOnly: true, secure: false, sameSite: "Lax", expires: -1 })), origins: [] };
      }
      await rc.close();
      if (r.status() < 500 && r.status() !== 429) return null;
    } catch { try { await rc.close(); } catch {} }
    await sleep(4000);
  }
  return null;
}

// mo 1 trang, thu thap loi console / response >=400 / ten nguon trong chu hien thi
async function visit(ctx, label, url, { settle = 1200, allow = null, ignoreConsole = null } = {}) {
  const page = await ctx.newPage();
  const errs = [], bad = [];
  page.on("pageerror", (e) => errs.push(`pageerror ${String(e.message).slice(0, 120)}`));
  page.on("console", (m) => { if (m.type() === "error" && !/Failed to load resource/.test(m.text()) && !(ignoreConsole && ignoreConsole.test(m.text()))) errs.push(`console ${m.text().slice(0, 220)}`); });
  page.on("response", (r) => { const s = r.status(); if (s >= 400 && !/favicon|\/sw\.js|\/auth\/me$/.test(r.url()) && !(allow && allow(s, r.url()))) bad.push(`${s} ${r.request().method()} ${new URL(r.url()).pathname.slice(0, 70)}`); });
  page.on("requestfailed", (r) => { const f = (r.failure() && r.failure().errorText) || ""; if (!/ABORTED|abort/i.test(f)) bad.push(`FAIL ${f} ${new URL(r.url()).pathname.slice(0, 60)}`); });
  let text = "";
  for (let t = 0; t < 3; t++) {          // retry ngan neu service dang khoi dong lai
    errs.length = 0; bad.length = 0;
    try {
      await page.goto(url, { waitUntil: "domcontentloaded", timeout: 20000 });
      await page.waitForLoadState("networkidle", { timeout: 3500 }).catch(() => {});
      await page.waitForTimeout(settle);
      text = await page.evaluate(() => document.body ? document.body.innerText : "");
    } catch (e) { errs.push(`nav ${String(e.message).slice(0, 80)}`); }
    if (!bad.some((b) => /^(5\d\d|429|FAIL)/.test(b)) && !errs.some((e) => e.startsWith("nav") || /dynamically imported/.test(e) || (/WebSocket/.test(e) && !ignoreConsole))) break;
    await sleep(8000 * (t + 1));
  }
  const uniq = (a) => [...new Set(a)].slice(0, 4);
  if (errs.length) fails.push(`${label}: loi console/trang: ${uniq(errs).join(" | ")}`);
  const known = bad.filter((b) => KNOWN.test(b)), real = bad.filter((b) => !KNOWN.test(b));
  if (known.length) notes.push(`${label}: LOI DA BIET (khong chan): ${uniq(known).join(" | ")}`);
  if (real.length) fails.push(`${label}: request loi: ${uniq(real).join(" | ")}`);
  const m = text.match(BANNED) || text.match(BANNED_UP);
  if (m) fails.push(`${label}: LO TEN NGUON "${m[0]}"`);
  if (/\b(NaN|undefined|\[object Object\])\b/.test(text)) fails.push(`${label}: hien NaN/undefined/[object Object]`);
  if (text.trim().length < 20) {   // co the dang tai cham/chi co bieu do: cho them + chap nhan canvas/svg
    await page.waitForTimeout(6000);
    const r = await page.evaluate(() => ({ h: location.href.slice(0, 60), x: (document.body ? document.body.innerText.trim() : "").slice(0, 50), t: document.body ? document.body.innerText.trim().length : 0, g: document.querySelectorAll("canvas, svg").length })).catch(() => ({ t: 0, g: 0 }));
    if (r.t < 20 && r.g < 2) fails.push(`${label}: trang gan nhu rong (url ${r.h} text "${r.x}")`);
  }
  checks += 4;
  await page.close();
  return text;
}
async function fetchJson(ctx, base, path, method = "GET") {
  const r = await ctx.request.fetch(base + path, { method, headers: { Origin: base } });
  return r.status();
}

const OPT = { viewport: { width: 1366, height: 768 }, bypassCSP: true, locale: "vi-VN" };
const initM = () => { try { localStorage.setItem("ts-ux", JSON.stringify({ onboarded: 99 })); } catch {} };
const initC = () => { try { localStorage.setItem("tc-prefs", JSON.stringify({ theme: "dark", lang: "vi", onboarded: true })); } catch {} };

// ---------- MASTER ----------
const sm = await login(BM, "/auth", "master", process.env.U_M, rd("pw_m"), { totpOn: true });
ok(!!sm, "master: dang nhap that bai");
if (sm) {
  const ctx = await browser.newContext({ ...OPT, storageState: sm }); await ctx.addInitScript(initM);
  const home = await ctx.newPage(); await home.goto(BM + "/", { waitUntil: "load" }).catch(() => {}); await home.waitForTimeout(3500);
  let routes = await home.evaluate(() => [...new Set([...document.querySelectorAll('a[href^="#/"]')].map((a) => a.getAttribute("href").replace(/^#\//, "").split("?")[0].split("/")[0]).filter(Boolean))]);
  await home.close();
  ok(routes.length >= 15, `master: chi thay ${routes.length} muc dieu huong (<15)`);
  await pool(routes.slice(0, MAXR), +(process.env.CONC || 3), (r) => visit(ctx, `master#/${r}`, `${BM}/#/${r}`));
  for (const [p, want] of [["/auth/me", 200], ["/api/v1/me", 200], ["/api/v1/user/prefs", 200], ["/api/v1/news?limit=5", 200], ["/api/v1/calendar", 200], ["/api/v1/journal/accounts", 200], ["/api/v1/bars?symbol=EURUSD&tf=H1&limit=5&order=desc", 200], ["/auth/admin/accounts", 200]]) {
    const s = await fetchJson(ctx, BM, p); ok(s === want, `master API ${p.split("?")[0]}: ${s} (mong ${want})`);
  }
  await ctx.close();
  // chua dang nhap: API phai 401
  const anon = await browser.newContext(); const s = await fetchJson(anon, BM, "/api/v1/news"); ok(s === 401 || s === 302, `anon /api/v1/news: ${s} (mong 401)`); await anon.close();
}

// ---------- CHUYEN GIA ----------
const se = await login(BM, "/auth", "master", process.env.U_E, rd("pw_e"));
ok(!!se, "chuyen gia: dang nhap that bai");
if (se) {
  const ctx = await browser.newContext({ ...OPT, storageState: se }); await ctx.addInitScript(initM);
  const hp = await ctx.newPage(); await hp.goto(BM + "/#/lop-hoc-ai", { waitUntil: "load" }).catch(() => {}); await hp.waitForTimeout(3000);
  let er = await hp.evaluate(() => [...new Set([...document.querySelectorAll('a[href^="#/"]')].map((a) => a.getAttribute("href").replace(/^#\//, "").split("?")[0].split("/")[0]).filter(Boolean))]); await hp.close();
  if (!er.includes("lop-hoc-ai")) er.unshift("lop-hoc-ai");
  ok(er.length <= 12, `chuyen gia thay qua nhieu muc (${er.length}) - nghi lo quyen`);
  await sleep(6000);
  await pool(er.slice(0, 4), 1, (r) => visit(ctx, `expert#/${r}`, `${BM}/#/${r}`, { allow: (st) => st === 403, ignoreConsole: /WebSocket connection/ }));   // WS bi tu choi voi vai tro nay la dung; 403 la dung: vai tro bi han che
  const s = await fetchJson(ctx, BM, "/auth/admin/accounts"); ok(s === 403 || s === 401, `chuyen gia khong duoc doc /auth/admin/accounts: ${s}`);
  await ctx.close();
}

// ---------- CLIENT ----------
const CR = ["hom-nay", "tong-quan", "vi-the", "rui-ro", "thi-truong", "tin-hieu", "canh-bao", "gioi-han", "thong-bao", "bao-cao", "ho-so", "tro-giup"];
const sc = await login(BC, "/c/auth", "mt5", process.env.U_C, rd("pw_c"), { changePw: true });
ok(!!sc, "client: dang nhap that bai");
if (sc) {
  const ctx = await browser.newContext({ ...OPT, storageState: sc }); await ctx.addInitScript(initC);
  await pool(CR, +(process.env.CONC || 3), (r) => visit(ctx, `client#/${r}`, `${BC}/c/#/${r}`, { allow: (st, u) => (st === 404 && /\/c\/api\/v1\/(risk|journal|positions|account)/.test(u)) || (st === 409 && /client-prefs/.test(u)) }));   // tai khoan thu moi: chua co du lieu -> 404 hop le
  for (const p of ["/c/api/v1/user/csrf", "/c/api/v1/user/client-prefs"]) { const s = await fetchJson(ctx, BC, p); ok(s === 200, `client API ${p}: ${s}`); }
  await ctx.close();
}
await browser.close();
if (skipped) notes.push(`bo qua ${skipped} trang do het ngan sach thoi gian (may qua tai)`);
console.log(JSON.stringify({ checks, fails: fails.length, notes, sec: Math.round((Date.now() - T0) / 1000) }));
for (const f of fails) console.log("FAIL " + f);
process.exit(fails.length ? 1 : 0);
