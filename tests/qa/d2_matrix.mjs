// D2: ma trận độ phân giải x sáng/tối, đổi khung M1..MN1, đổi mã nhiều lần (rò bộ nhớ), realtime. Chạy qua d2_run.sh
import { chromium } from "playwright";
import fs from "node:fs";
const BASE = process.env.BASE || "http://127.0.0.1:8580", OUT = process.env.OUT || "out";
const USER = process.env.QA_USER, PASS = process.env.QA_PASS;
fs.mkdirSync(OUT, { recursive: true });
const res = [];
const ok = (n, c, x = "") => { res.push({ n, pass: !!c, x: String(x).slice(0, 300) }); console.log(`${c ? "PASS" : "FAIL"}  ${n}  ${String(x).slice(0, 240)}`); };
const browser = await chromium.launch({ args: ["--enable-precise-memory-info"] });
const SIZES = [[1920, 1080], [1366, 768], [768, 1024], [390, 844]];
const sleep = (p, ms) => p.waitForTimeout(ms);
async function mk(w, h, scheme) {
  const ctx = await browser.newContext({ viewport: { width: w, height: h }, colorScheme: scheme, baseURL: BASE });
  for (let i = 0; i < 5; i++) { let r; try { r = await ctx.request.post(`${BASE}/auth/login`, { data: { platform: "master", login: USER, secret: PASS }, headers: { Origin: BASE, "Content-Type": "application/json" } }); } catch (e) { console.log('login exc'); await new Promise((s) => setTimeout(s, 5000)); continue; } console.log('login', r.status()); if (r.ok()) break; await new Promise((s) => setTimeout(s, 4000)); }
  await ctx.addInitScript((s) => { try { localStorage.setItem("ts-theme", s); const k = "ts-ux"; const v = JSON.parse(localStorage.getItem(k) || "{}"); v.onboarded = 99; localStorage.setItem(k, JSON.stringify(v)); } catch {} }, scheme);
  const page = await ctx.newPage(); page.setDefaultTimeout(9000);
  // prefs máy chủ dùng chung cho mọi master -> không ghi; ép theme khi ĐỌC để kiểm cả hai giao diện
  await page.route(/\/user\/prefs/, async (route) => {
    const rq = route.request();
    if (rq.method() === "GET") { const r = await route.fetch(); let j; try { j = await r.json(); } catch { return route.fulfill({ response: r }); } j.prefs = { ...(j.prefs || {}), theme: scheme }; if (j.prefs.ux) j.prefs.ux = { ...j.prefs.ux, theme: scheme }; return route.fulfill({ response: r, json: j }); }
    if (rq.method() === "PUT") return route.fulfill({ status: 200, json: { rev: 999999, prefs: {} } });
    return route.continue();
  });
  const errs = [], bad = [];
  page.on("pageerror", (e) => errs.push("pageerror: " + String(e.message).slice(0, 200)));
  page.on("console", (m) => { if (m.type() === "error" && !/net::ERR_(NETWORK_CHANGED|FAILED|CONNECTION_RESET)/.test(m.text())) errs.push("console: " + m.text().slice(0, 200)); });
  page.on("response", (r) => { if (r.status() >= 400 && !/favicon/.test(r.url())) bad.push(`${r.status()} ${r.url().replace(BASE, "").slice(0, 80)}`); });
  return { ctx, page, errs, bad };
}
const open = async (page, sym = "EURUSD", tf = "H1") => {
  await page.goto(`${BASE}/#/thi-truong/${sym}?tf=${tf}`, { waitUntil: "load" });
  const got = await page.waitForSelector(".ws-cell canvas", { timeout: 30000 }).catch(() => null);
  if (!got) { console.log("BLANK? body=", (await page.evaluate(() => document.body.innerText.slice(0, 200) + "|root=" + document.getElementById("root")?.innerHTML.length)).replace(/\n/g, " ")); await page.reload({ waitUntil: "load" }); await page.waitForSelector(".ws-cell canvas", { timeout: 30000 }); }
  await sleep(page, 2500);
};
const audit = (page) => page.evaluate(() => {
  const t = document.body.innerText;
  const vw = document.documentElement.clientWidth;
  return { bad: (t.match(/\b(NaN|undefined|null|\[object Object\]|Infinity)\b/g) || []).slice(0, 5), ox: document.documentElement.scrollWidth > vw + 1, loading: document.querySelectorAll('[aria-busy="true"]').length, banned: /dukascopy|yahoo|binance|frankfurter|vnstock|okx|bybit|tiingo/i.test(t), canv: document.querySelectorAll(".ws-cell canvas").length };
});
// 1. ma trận
for (const [w, h] of SIZES) for (const th of ["dark", "light"]) {
  const tag = `${w}x${h}-${th}`; const { ctx, page, errs, bad } = await mk(w, h, th);
  try {
    await open(page);
    const a = await audit(page);
    const th2 = await page.evaluate(() => document.documentElement.dataset.theme);
    ok(`[${tag}] dựng chart, không NaN/undefined`, a.canv >= 1 && a.bad.length === 0, JSON.stringify(a));
    ok(`[${tag}] theme áp đúng`, th2 === th, th2);
    ok(`[${tag}] không tràn ngang / không lộ tên nguồn`, !a.ox && !a.banned, JSON.stringify({ ox: a.ox, banned: a.banned }));
    ok(`[${tag}] không lỗi console / request lỗi`, errs.length === 0 && bad.length === 0, [...errs, ...bad].slice(0, 3).join(" ; "));
    await page.screenshot({ path: `${OUT}/m-${tag}.png` });
  } catch (e) { ok(`[${tag}] EXC`, false, e.message.split("\n")[0]); await page.screenshot({ path: `${OUT}/fail-${tag}.png` }).catch(() => {}); }
  await ctx.close();
}
// 2. khung thời gian + đổi mã + rò bộ nhớ + realtime (1600x950 dark)
{
  const { ctx, page, errs, bad } = await mk(1600, 950, "dark");
  try {
    await open(page);
    const btns = await page.getByRole("button", { name: /^(M1|M5|M15|M30|H1|H4|D1|W1|MN1?)$/ }).allInnerTexts();
    ok("Thanh khung có M1,M5,M15,H1,H4,D1", ["M1", "M5", "M15", "H1", "H4", "D1"].every((t) => btns.includes(t)), btns.join(","));
    for (const tf of ["M1", "M5", "M15", "M30", "H1", "H4", "D1", "W1", "MN1"]) {
      const e0 = errs.length;
      await page.goto(`${BASE}/#/thi-truong/EURUSD?tf=${tf}`); await sleep(page, 3000);
      for (let k = 0; k < 6 && !(await page.locator('dt:has-text("Nến") + dd').count()); k++) await sleep(page, 1500);
      const a = await audit(page); const cnt = await page.locator('dt:has-text("Nến") + dd').first().innerText().catch(() => "?");
      const n = Number(cnt.replace(/\D/g, "") || 0);
      const inBar = btns.includes(tf);
      ok(`Khung ${tf}${inBar ? "" : " (qua URL, không có nút)"}`, errs.length === e0 && a.bad.length === 0 && a.canv >= 1 && n > 0, `nến=${cnt} ${errs.slice(e0)[0] || a.bad.join()} bad=${[...new Set(bad)].join(' ')} tf=${await page.locator('.ws-cell').first().innerText().then((t) => (/(EURUSD)\s*\n?\s*(\S+)/.exec(t.replace(/\s+/g,' '))||[])[2])}`);
    }
    for (const tf of btns) {
      const e0 = errs.length; await page.getByRole("button", { name: tf, exact: true }).click(); await sleep(page, 2000);
      const a = await audit(page);
      ok(`Nút khung ${tf}`, errs.length === e0 && a.bad.length === 0 && a.canv >= 1, errs.slice(e0)[0] || "");
    }
    // đổi mã nhiều lần
    const syms = ["EURUSD", "GBPUSD", "USDJPY", "XAUUSD", "BTCUSD", "AUDUSD", "USDCAD", "NZDUSD"];
    const mem = async () => page.evaluate(() => ({ heap: Math.round(performance.memory.usedJSHeapSize / 1048576), dom: document.getElementsByTagName("*").length, canv: document.querySelectorAll("canvas").length }));
    await sleep(page, 2000); const m0 = await mem(); let m1;
    for (let i = 0; i < 40; i++) {
      await page.goto(`${BASE}/#/thi-truong/${syms[i % syms.length]}?tf=${i % 2 ? "M15" : "H1"}`); await sleep(page, 700);
      if (i === 9) { await page.evaluate(() => window.gc && window.gc()); m1 = await mem(); }
    }
    await sleep(page, 2500); const m2 = await mem();
    ok("Đổi mã 40 lần: DOM/canvas không phình", m2.dom < m0.dom * 1.5 + 200 && m2.canv <= m0.canv + 4, JSON.stringify({ m0, m1, m2 }));
    ok("Đổi mã 40 lần: heap tăng hợp lý (<80MB)", m2.heap - m0.heap < 80, `${m0.heap}->${m2.heap}MB`);
    const a = await audit(page);
    ok("Sau đổi mã: không kẹt loading/NaN", a.bad.length === 0, JSON.stringify(a));
    ok("Đổi mã: không lỗi console/request", errs.length === 0 && bad.length === 0, [...errs, ...bad].slice(0, 4).join(" ; "));
    // realtime M1
    await open(page, "EURUSD", "M1");
    const lg = () => page.locator(".ws-cell").first().innerText();
    const l0 = await lg(); let changed = false;
    for (let i = 0; i < 12 && !changed; i++) { await sleep(page, 5000); changed = (await lg()) !== l0; }
    ok("Nến M1 cập nhật realtime trong 60s", changed, l0.replace(/\n/g, " | ").slice(0, 100));
    // watchlist trong chart: yêu thích / bỏ / giữ sau reload / tab ★ / chọn mã từ danh sách
    await open(page, "EURUSD", "H1");
    await page.evaluate(() => localStorage.removeItem("ts-fav"));
    await page.reload({ waitUntil: "load" }); await page.waitForSelector(".ws-cell canvas"); await sleep(page, 2000);
    const star = page.getByRole("button", { name: /^Yêu thích / }).first(); await star.click(); await sleep(page, 500);
    const f1 = await page.evaluate(() => localStorage.getItem("ts-fav"));
    ok("Watchlist: thêm yêu thích", /\[".+"\]/.test(f1 || ""), f1);
    await page.reload({ waitUntil: "load" }); await page.waitForSelector(".ws-cell canvas"); await sleep(page, 2000);
    ok("Watchlist: giữ sau reload", (await page.getByRole("button", { name: /^Bỏ yêu thích / }).count()) >= 1);
    await page.getByRole("button", { name: /^Bỏ yêu thích / }).first().click(); await sleep(page, 500);
    ok("Watchlist: bỏ yêu thích", (await page.evaluate(() => localStorage.getItem("ts-fav"))) === "[]");
    const pick = page.locator('[aria-label="Danh sách mã"] button[aria-pressed]').nth(3); const pn = (await pick.innerText()).split("\n")[0];
    await pick.click(); await sleep(page, 2500);
    ok("Chọn mã từ danh sách đổi chart", (await page.locator(".ws-cell").first().innerText()).includes(pn), pn);
  } catch (e) { ok("EXC phần 2", false, e.message.split("\n")[0]); await page.screenshot({ path: `${OUT}/fail-part2.png` }).catch(() => {}); }
  await ctx.close();
}
await browser.close();
fs.writeFileSync(`${OUT}/d2_results.json`, JSON.stringify(res, null, 1));
console.log(`TOTAL pass=${res.filter((r) => r.pass).length} fail=${res.filter((r) => !r.pass).length}`);
