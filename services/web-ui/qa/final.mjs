// QA GIAO DIEN CUOI (master + client) - chay TRONG container Playwright tam tren VPS (qa/final.sh), KHONG chay o laptop.
//  APP=master|client  VPS=375x812,768x1024,...  THEMES=dark,light  LANGS=vi,en (client)  ONLY=route1,route2  OUT=out  SHOTS=all|none
//  Dang nhap: master thu QA_USER/QA_PASS | client thu QA_USER/QA_PASS (tu doi mat khau lan dau).
import { chromium } from "playwright";
import fs from "node:fs";
import crypto from "node:crypto";
import { createRequire } from "node:module";
const require = createRequire(import.meta.url);

const APP = process.env.APP || "master";
const BASE = process.env.BASE || (APP === "client" ? "http://127.0.0.1:8581" : "http://127.0.0.1:8580");
const AUTH = APP === "client" ? `${BASE}/c/auth` : `${BASE}/auth`;
const ROOT = APP === "client" ? `${BASE}/c/` : `${BASE}/`;
const OUT = process.env.OUT || "out";
const ALLVP = { "375x812": [375, 812, true], "768x1024": [768, 1024, true], "1366x768": [1366, 768, false], "1920x1080": [1920, 1080, false], "2560x1440": [2560, 1440, false] };
const VPS = (process.env.VPS || Object.keys(ALLVP).join(",")).split(",");
const THEMES = (process.env.THEMES || "dark,light").split(",");
const LANGS = (process.env.LANGS || (APP === "client" ? "vi,en" : "vi")).split(",");
const ONLY = process.env.ONLY ? process.env.ONLY.split(",") : null;
const SHOTS = process.env.SHOTS || "all";
const USER = process.env.QA_USER, PASS = process.env.QA_PASS;
fs.mkdirSync(OUT, { recursive: true });
const axeSrc = fs.readFileSync(require.resolve("axe-core/axe.min.js"), "utf8");

const CLIENT_ROUTES = ["hom-nay", "tong-quan", "vi-the", "rui-ro", "nhat-ky", "thi-truong", "tin-lich", "tin-hieu", "chuyen-gia", "canh-bao", "gioi-han", "thong-bao", "bao-cao", "ban-tin", "danh-muc", "ho-so", "tro-giup"];
const H = { Origin: BASE, "Content-Type": "application/json" };

function b32dec(s) { const A = "ABCDEFGHIJKLMNOPQRSTUVWXYZ234567"; let bits = ""; for (const c of s.replace(/=+$/, "").toUpperCase()) bits += A.indexOf(c).toString(2).padStart(5, "0"); const out = []; for (let i = 0; i + 8 <= bits.length; i += 8) out.push(parseInt(bits.slice(i, i + 8), 2)); return Buffer.from(out); }
function totp(secret, t = Date.now()) {
  const c = Buffer.alloc(8); c.writeBigUInt64BE(BigInt(Math.floor(t / 30000)));
  const h = crypto.createHmac("sha1", b32dec(secret)).update(c).digest(); const o = h[19] & 15;
  return String(((h[o] & 127) << 24 | h[o + 1] << 16 | h[o + 2] << 8 | h[o + 3]) % 1e6).padStart(6, "0");
}
async function bootstrap(browser) {
  const jar = {};
  const take = (r) => { for (const h of r.headersArray()) if (h.name.toLowerCase() === "set-cookie") for (const line of h.value.split("\n")) { const [kv] = line.split(";"); const i = kv.indexOf("="); const k = kv.slice(0, i).trim(), v = kv.slice(i + 1).trim(); if (v) jar[k] = v; else delete jar[k]; } };
  const rc = await browser.newContext();
  const post = async (p, d) => { const r = await rc.request.post(`${AUTH}${p}`, { data: d, headers: { ...H, Cookie: Object.entries(jar).map(([k, v]) => `${k}=${v}`).join("; ") } }); take(r); return r; };
  let pass = PASS;
  let r = await post("/login", { platform: APP === "client" ? "mt5" : "master", login: USER, secret: pass });
  if (r.status() !== 200) throw new Error(`login ${r.status()} ${(await r.text()).slice(0, 120)}`);
  if (APP === "client") {
    pass = PASS + "-Qa9!xZ";
    const c = await post("/change-password", { current_password: PASS, new_password: pass });
    if (c.status() === 200) {
      r = await post("/login", { platform: "mt5", login: USER, secret: pass });
      if (r.status() !== 200) throw new Error(`relogin ${r.status()}`);
    } else console.log(`change-pw ${c.status()}`);
  } else {
    // bat TOTP cho master thu (cac trang quan tri doi tai khoan yeu cau); secret chi nam trong bo nho tien trinh
    const a = await post("/totp/setup", {});
    const secret = (await a.json().catch(() => ({}))).secret;
    if (secret) {
      let b = await post("/totp/enable", { code: totp(secret) });
      if (b.status() !== 200) { await new Promise((x) => setTimeout(x, 31000)); b = await post("/totp/enable", { code: totp(secret) }); }
      if (b.status() !== 200) console.log("totp enable fail", b.status());
    } else console.log("totp setup fail", a.status());
  }
  await rc.close();
  return { cookies: Object.entries(jar).map(([name, value]) => ({ name, value, domain: "127.0.0.1", path: "/", httpOnly: true, secure: false, sameSite: "Lax", expires: -1 })), origins: [] };
}

const AUDIT = ({ mobile }) => {
  const vw = document.documentElement.clientWidth, issues = [];
  const vis = (el) => { const r = el.getBoundingClientRect(), cs = getComputedStyle(el); return r.width > 0 && r.height > 0 && cs.visibility !== "hidden" && cs.display !== "none"; };
  const desc = (el) => `${el.tagName.toLowerCase()}${el.id ? "#" + el.id : ""}${el.className && typeof el.className === "string" ? "." + el.className.trim().split(/\s+/).slice(0, 3).join(".") : ""} "${(el.getAttribute("aria-label") || el.textContent || "").trim().replace(/\s+/g, " ").slice(0, 30)}"`;
  const inScroller = (el) => { for (let p = el.parentElement; p; p = p.parentElement) { const o = getComputedStyle(p).overflowX; if ((o === "auto" || o === "scroll") && p.scrollWidth > p.clientWidth) return true; } return false; };
  if (document.documentElement.scrollWidth > vw + 1) issues.push({ k: "page-overflow-x", d: `scrollWidth ${document.documentElement.scrollWidth} > ${vw}` });
  const main = document.querySelector("main, #main") || document.body;
  let n = 0;
  for (const el of main.querySelectorAll("*")) {
    if (!vis(el) || inScroller(el) || el.closest("svg, canvas, .tm-chart, .tape, .tape-track, [data-allow-wide]")) continue;
    const r = el.getBoundingClientRect();
    if (r.right > vw + 1 || r.left < -1) { issues.push({ k: "out-of-viewport", d: `${desc(el)} [${Math.round(r.left)}..${Math.round(r.right)}] vw=${vw}` }); if (++n > 6) break; }
  }
  const groups = new Map();
  for (const el of main.querySelectorAll(".panel, .kpi, .pos-card, .card")) { if (!vis(el)) continue; const p = el.parentElement; if (!groups.has(p)) groups.set(p, []); groups.get(p).push(el); }
  for (const [, els] of groups) for (let i = 0; i < els.length; i++) for (let j = i + 1; j < els.length; j++) {
    const a = els[i].getBoundingClientRect(), b = els[j].getBoundingClientRect();
    if (els[i].contains(els[j]) || els[j].contains(els[i])) continue;
    const ox = Math.min(a.right, b.right) - Math.max(a.left, b.left), oy = Math.min(a.bottom, b.bottom) - Math.max(a.top, b.top);
    if (ox > 3 && oy > 3) { const pos = (e) => getComputedStyle(e).position; if (["absolute", "fixed", "sticky"].includes(pos(els[i])) || ["absolute", "fixed", "sticky"].includes(pos(els[j]))) continue; issues.push({ k: "overlap", d: `${desc(els[i])} x ${desc(els[j])} (${Math.round(ox)}x${Math.round(oy)})` }); }
  }
  if (mobile) {
    let t = 0;
    for (const el of document.querySelectorAll("a,button,input:not([type=hidden]):not([type=checkbox]):not([type=radio]),select,textarea,[role=tab],[role=switch],summary")) {
      if (!vis(el) || el.closest(".sr-only") || el.classList.contains("sr-only-skip") || el.classList.contains("skip") || el.id === "tv-attr-logo") continue;
      const cs = getComputedStyle(el); if (cs.display === "inline" && el.tagName === "A") continue;
      const r = el.getBoundingClientRect();
      if (Math.min(r.width, r.height) < 43.5) { issues.push({ k: "touch<44", d: `${desc(el)} ${Math.round(r.width)}x${Math.round(r.height)}` }); if (++t > 12) break; }
    }
  }
  n = 0;
  for (const el of document.querySelectorAll("main button, main h1, main h2, main h3, main .btn, main .chip, main [role=tab], main th, main td, header *, nav *, .bottom-nav *")) {
    if (!vis(el) || el.children.length > 3 || el.closest(".sr-only, .tape")) continue;
    const cs = getComputedStyle(el);
    if (el.scrollWidth > el.clientWidth + 2 && cs.textOverflow !== "ellipsis" && (cs.overflowX === "hidden" || cs.overflowX === "clip")) { issues.push({ k: "clipped-text", d: desc(el) }); if (++n > 6) break; }
  }
  n = 0;
  for (const el of main.querySelectorAll("p, span, div, b, li, td, small, label")) {
    if (!vis(el) || el.children.length || !el.textContent.trim()) continue;
    if (parseFloat(getComputedStyle(el).fontSize) < 9.9) { issues.push({ k: "tiny-font", d: `${desc(el)} ${getComputedStyle(el).fontSize}` }); if (++n > 3) break; }
  }
  return issues;
};

const TEXTSCAN = ({ banned, bannedUp, lang }) => {
  const out = [];
  const txt = document.body.innerText || "";
  const bad = txt.match(/\bNaN\b|\bundefined\b|Invalid Date|\[object|\bInfinity\b|\$\{|\{\{/g);
  if (bad) out.push({ k: "bad-value", d: [...new Set(bad)].join(",") + " :: " + (txt.match(/.{0,30}(NaN|undefined|Invalid Date|\[object|Infinity).{0,20}/) || [""])[0].replace(/\s+/g, " ") });
  const attrs = [...document.querySelectorAll("[title],[aria-label],[placeholder],img[alt]")].map((e) => (e.getAttribute("title") || "") + " " + (e.getAttribute("aria-label") || "") + " " + (e.getAttribute("placeholder") || "")).join(" \n ");
  const all = txt + "\n" + attrs;
  const re = new RegExp("(?<![\\p{L}\\p{N}])(" + banned.join("|") + ")(?![\\p{L}\\p{N}])", "giu");
  const reU = new RegExp("(?<![\\p{L}\\p{N}])(" + bannedUp.join("|") + ")(?![\\p{L}\\p{N}])", "gu");
  const hit = [...(all.match(re) || []), ...(all.match(reU) || [])];
  if (hit.length) out.push({ k: "source-name", d: [...new Set(hit)].join(",") });
  const stuck = document.querySelectorAll('[role="status"][aria-label*="ang tải" i], [role="status"][aria-label*="oading" i]');
  if (stuck.length) out.push({ k: "stuck-loading", d: `${stuck.length} skeleton con lai` });
  const errs = [...document.querySelectorAll('[role="alert"]')].map((e) => e.textContent.trim().replace(/\s+/g, " ").slice(0, 90)).filter(Boolean);
  for (const e of errs.slice(0, 4)) out.push({ k: "alert", d: e });
  const m = txt.match(/.{0,25}(Không kết nối|Không tải được|Lỗi tải|Failed to load|Could not load|Not connected|No connection).{0,50}/i);
  if (m) out.push({ k: "error-text", d: m[0].replace(/\s+/g, " ") });
  if (lang === "en") {
    const VI = /[àáảãạăằắẳẵặâầấẩẫậèéẻẽẹêềếểễệìíỉĩịòóỏõọôồốổỗộơờớởỡợùúủũụưừứửữựỳýỷỹỵđĐ]/;
    const seen = new Set(); const w = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
    while (w.nextNode()) { const nd = w.currentNode, s = nd.nodeValue.trim(); if (!s || !VI.test(s) || nd.parentElement.closest("[data-server-text], script, style")) continue; const r = nd.parentElement.getBoundingClientRect(); if (r.width === 0) continue; seen.add(s.slice(0, 70)); }
    for (const el of document.querySelectorAll("[aria-label],[title],[placeholder]")) for (const a of ["aria-label", "title", "placeholder"]) { const v = el.getAttribute(a); if (v && VI.test(v)) seen.add(`@${a}@${el.tagName.toLowerCase()}${typeof el.className === "string" ? "." + el.className.slice(0, 24) : ""}: ${v.slice(0, 60)}`); }
    for (const s of [...seen].slice(0, 12)) out.push({ k: "vi-left", d: s });
  }
  return out;
};

const BANNED = ["dukascopy", "frankfurter", "yahoo", "vnstock", "vndirect", "finfo", "okx", "kucoin", "binance", "bybit", "coinbase", "kraken", "ccxt", "alpaca", "tiingo", "oanda", "truefx", "gdelt", "reuters", "cafef", "vnexpress", "myfxbook", "actionforex", "fair\\s+economy", "faireconomy", "forexfactory", "investinglive", "oilprice", "mql5", "kbs", "stooq", "twelvedata", "finnhub", "alphavantage"];
const BANNED_UP = ["BLS", "CFTC", "FRED", "FMP"];

async function runAxe(page) {
  return page.evaluate(async (src) => {
    if (!window.axe) (0, eval)(src);
    const r = await window.axe.run(document, { runOnly: { type: "tag", values: ["wcag2a", "wcag2aa"] }, resultTypes: ["violations"] });
    return r.violations.map((v) => ({ id: v.id, impact: v.impact, n: v.nodes.length, sample: v.nodes.slice(0, 2).map((n) => (n.target || []).join(" ").slice(0, 80) + " | " + ((n.any[0] && n.any[0].message) || n.failureSummary || "").replace(/\s+/g, " ").slice(0, 110)) }));
  }, axeSrc).catch((e) => [{ id: "axe-error", impact: "n/a", n: 0, sample: [String(e.message).slice(0, 100)] }]);
}

// ảnh JPEG <= 150KB: giảm chất lượng dần
async function shotSmall(page, path) {
  for (const q of [62, 48, 36, 26, 18]) { const b = await page.screenshot({ type: "jpeg", quality: q, fullPage: true }).catch(() => null); if (!b) return; if (b.length <= 150000 || q === 18) { fs.writeFileSync(path, b); return; } }
}
const browser = await chromium.launch();
const state = await bootstrap(browser);
console.log(`[${APP}] login ok`);

// Tuỳ chọn người dùng (user_prefs) có thể DÙNG CHUNG giữa các master -> chụp trước, khôi phục sau khi chạy
const prefsApi = async (st, mode, before) => {
  const c = await browser.newContext({ storageState: st, bypassCSP: true });
  const p = await c.newPage();
  await p.goto(ROOT, { waitUntil: "domcontentloaded" }).catch(() => {});
  const r = await p.evaluate(async ([mode, before]) => {
    try {
      const cur = await (await fetch("/api/v1/user/prefs", { credentials: "same-origin" })).json();
      if (mode === "get") return cur;
      const t = (await (await fetch("/api/v1/user/csrf", { credentials: "same-origin" })).json()).token;
      const res = await fetch("/api/v1/user/prefs", { method: "PUT", credentials: "same-origin", headers: { "Content-Type": "application/json", "X-CSRF-Token": t }, body: JSON.stringify({ rev: cur.rev, prefs: before.prefs || {} }) });
      return { restored: res.status };
    } catch (e) { return { err: String(e) }; }
  }, [mode, before]);
  await c.close();
  return r;
};
let prefsBefore = null;
if (APP === "master") { prefsBefore = await prefsApi(state, "get"); console.log("prefs-before keys:", Object.keys((prefsBefore && prefsBefore.prefs) || {}).join(",")); }
let ROUTES;
if (APP === "client") ROUTES = CLIENT_ROUTES;
else {
  const c = await browser.newContext({ viewport: { width: 1366, height: 768 }, storageState: state, bypassCSP: true });
  const p = await c.newPage();
  await p.addInitScript(() => { try { localStorage.setItem("ts-ux", JSON.stringify({ onboarded: 99 })); } catch {} });
  await p.goto(ROOT, { waitUntil: "load" }); await p.waitForTimeout(3500);
  ROUTES = await p.evaluate(() => [...new Set([...document.querySelectorAll('a[href^="#/"]')].map((a) => a.getAttribute("href").replace(/^#\//, "").split("?")[0].split("/")[0]).filter(Boolean))]);
  await c.close();
  console.log("routes:", ROUTES.join(","));
  fs.writeFileSync(`${OUT}/routes-master.json`, JSON.stringify(ROUTES));
}
const routes = ONLY ? ROUTES.filter((r) => ONLY.includes(r)) : ROUTES;

const results = [];
for (const vp of VPS) {
  const [w, h, mobile] = ALLVP[vp];
  for (const lang of LANGS) for (const theme of THEMES) {
    const ctx = await browser.newContext({ viewport: { width: w, height: h }, deviceScaleFactor: 1, isMobile: mobile, hasTouch: mobile, colorScheme: theme, locale: lang === "en" ? "en-GB" : "vi-VN", timezoneId: "Asia/Ho_Chi_Minh", storageState: state, bypassCSP: true });
    await ctx.addInitScript(([t, l, app]) => { try { if (app === "client") localStorage.setItem("tc-prefs", JSON.stringify({ theme: t, lang: l, onboarded: true })); else localStorage.setItem("ts-ux", JSON.stringify({ onboarded: 99, theme: t })); } catch {} }, [theme, lang, APP]);
    const page = await ctx.newPage();
    let errs = [], bad = [];
    page.on("pageerror", (e) => errs.push(`pageerror: ${String(e.message).slice(0, 200)}`));
    page.on("console", (m) => { if (m.type() === "error") errs.push(`console: ${m.text().slice(0, 200)}`); });
    page.on("response", (r) => { const s = r.status(); if (s >= 400 && !/favicon|\/sw\.js/.test(r.url())) bad.push(`${s} ${r.request().method()} ${r.url().replace(BASE, "").slice(0, 90)}`); });
    page.on("requestfailed", (r) => { const f = (r.failure() && r.failure().errorText) || ""; if (!/ABORTED|abort/i.test(f)) bad.push(`FAIL ${f} ${r.url().replace(BASE, "").slice(0, 90)}`); });
    if (APP === "client") {
      // ngôn ngữ/giao diện của client được đồng bộ từ máy chủ -> đặt qua API prefs (như người dùng đổi ở Hồ sơ) rồi tải lại
      await page.goto(ROOT, { waitUntil: "domcontentloaded" }).catch(() => {});
      const put = await page.evaluate(async ([lang, theme]) => {
        try {
          const g = await (await fetch("/c/api/v1/user/client-prefs", { credentials: "same-origin" })).json();
          const t = (await (await fetch("/c/api/v1/user/csrf", { credentials: "same-origin" })).json()).token;
          const r = await fetch("/c/api/v1/user/client-prefs", { method: "PUT", credentials: "same-origin", headers: { "Content-Type": "application/json", "X-CSRF-Token": t }, body: JSON.stringify({ rev: g.rev, data: { ...(g.data || {}), lang, theme } }) });
          return r.status;
        } catch (e) { return String(e); }
      }, [lang, theme]);
      if (put !== 200) console.log("prefs PUT", put);
      await page.reload({ waitUntil: "domcontentloaded" }).catch(() => {});
    }
    for (const route of routes) {
      errs = []; bad = [];
      const t0 = Date.now();
      try {
        await page.goto(ROOT + "#/", { waitUntil: "domcontentloaded" }).catch(() => {});
        await page.goto(`${ROOT}#/${route}`, { waitUntil: "domcontentloaded" });
        await page.evaluate(([t]) => { document.documentElement.dataset.theme = t; }, [theme]).catch(() => {});
        await page.waitForLoadState("networkidle", { timeout: 6000 }).catch(() => {});
        await page.waitForTimeout(1500);
        for (let i = 0; i < 6; i++) { const n = await page.locator('[role="status"][aria-label*="ang tải"], [role="status"][aria-label*="oading"]').count().catch(() => 0); if (!n) break; await page.waitForTimeout(1000); }
        const issues = [...(await page.evaluate(AUDIT, { mobile })), ...(await page.evaluate(TEXTSCAN, { banned: BANNED, bannedUp: BANNED_UP, lang }))];
        const axe = await runAxe(page);
        if (SHOTS !== "none") await shotSmall(page, `${OUT}/${vp}-${theme}-${lang}-${route}.jpg`);
        results.push({ app: APP, vp, theme, lang, route, issues, errs: [...new Set(errs)].slice(0, 6), bad: [...new Set(bad)].slice(0, 8), axe, ms: Date.now() - t0 });
        if (APP === "master" && route === "terminal") {
          // các workspace còn lại của Terminal (tab): chụp + kiểm tra riêng
          const tabs = page.locator('[role="tablist"][aria-label="Workspace"] [role="tab"]');
          const n = await tabs.count().catch(() => 0);
          for (let i = 1; i < n; i++) {
            errs = []; bad = [];
            const name = ((await tabs.nth(i).textContent().catch(() => "")) || `ws${i}`).trim();
            await tabs.nth(i).click().catch(() => {});
            await page.waitForTimeout(3000);
            const is2 = [...(await page.evaluate(AUDIT, { mobile })), ...(await page.evaluate(TEXTSCAN, { banned: BANNED, bannedUp: BANNED_UP, lang }))];
            const ax2 = await runAxe(page);
            if (SHOTS !== "none") await shotSmall(page, `${OUT}/${vp}-${theme}-${lang}-terminal-ws${i}.jpg`);
            results.push({ app: APP, vp, theme, lang, route: `terminal-ws${i}(${name})`, issues: is2, errs: [...new Set(errs)].slice(0, 6), bad: [...new Set(bad)].slice(0, 8), axe: ax2, ms: 0 });
          }
        }
      } catch (e) { results.push({ app: APP, vp, theme, lang, route, issues: [{ k: "nav-fail", d: String(e.message).slice(0, 150) }], errs: [], bad: [], axe: [], ms: 0 }); }
    }
    await ctx.close();
    fs.writeFileSync(`${OUT}/results-${APP}-${process.env.TAG || "x"}.json`, JSON.stringify(results));
    console.log(`done ${APP} ${vp} ${theme} ${lang} (${results.length})`);
  }
}
if (APP === "master" && prefsBefore && prefsBefore.prefs) console.log("prefs-restore", JSON.stringify(await prefsApi(state, "put", prefsBefore)));
await browser.close();
