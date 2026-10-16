// Dọn dữ liệu do QA biểu đồ để lại trong user_prefs.chart (bản vẽ của các mã QA, mẫu qa-b-*) và quy tắc cảnh báo QA-B*.
import { chromium } from "playwright";
const BASE = process.env.BASE || "http://127.0.0.1:8080";
const browser = await chromium.launch();
const page = await (await browser.newContext({ baseURL: BASE })).newPage();
await page.goto(`${BASE}/`, { waitUntil: "load" }).catch(() => {});
const api = (m, p, body) => page.evaluate(async ([m, p, body]) => {
  const tk = m === "GET" ? null : (await (await fetch("/api/v1/user/csrf", { credentials: "same-origin" })).json()).token;
  const r = await fetch(`/api/v1${p}`, { method: m, credentials: "same-origin", headers: { "Content-Type": "application/json", ...(tk ? { "X-CSRF-Token": tk } : {}) }, body: body ? JSON.stringify(body) : undefined });
  let j = null; try { j = await r.json(); } catch {}
  return { s: r.status, j };
}, [m, p, body]);
for (let k = 0; k < 4; k++) {
  const p = await api("GET", "/user/prefs");
  const pr = p.j?.prefs || {};
  const draw = pr.chart?.draw || {}, tpl = pr.chart?.tpl || {};
  console.log("before keys", Object.keys(draw), Object.keys(tpl), "size", JSON.stringify(pr).length);
  for (const key of Object.keys(draw)) if (/^(EURUSD|GBPUSD|XAUUSD|AUDUSD|CRYPTO:BTCUSDT)\|/.test(key)) delete draw[key];
  for (const key of Object.keys(tpl)) if (/^qa-b/.test(key)) delete tpl[key];
  if (pr.chart && !Object.keys(draw).length && !Object.keys(tpl).length) delete pr.chart;
  const r = await api("PUT", "/user/prefs", { rev: p.j.rev, prefs: pr });
  console.log("PUT", r.s);
  if (r.s === 200) break;
}
const rules = await api("GET", "/user/rules");
for (const r of (rules.j?.items || []).filter((x) => /^QA-B/.test(x.name))) console.log("rule del", r.name, (await api("DELETE", `/user/rules/${r.id}`)).s);
const after = await api("GET", "/user/prefs");
console.log("after", JSON.stringify(after.j?.prefs?.chart || null).slice(0, 200));
await browser.close();
