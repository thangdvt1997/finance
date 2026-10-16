// QA trang Kịch bản: MOCK=1 -> chặn /api/v1/patterns/* bằng dữ liệu mẫu theo hợp đồng SCAN (chỉ trong QA, không vào bundle).
import { chromium } from "playwright";
import fs from "node:fs";
const BASE = process.env.BASE || "http://127.0.0.1:8580";
const OUT = process.env.OUT || "out"; fs.mkdirSync(OUT, { recursive: true });
const MOCK = process.env.MOCK === "1";
const USER = process.env.QA_USER, PASS = process.env.QA_PASS;
const H = { Origin: BASE, "Content-Type": "application/json" };

async function login(browser) {
  const rc = await browser.newContext();
  const r = await rc.request.post(`${BASE}/auth/login`, { data: { platform: "master", login: USER, secret: PASS }, headers: H });
  if (r.status() !== 200) throw new Error("login " + r.status());
  const st = await rc.storageState(); await rc.close(); return st;
}
const svg = (label, dark) => `<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="675" viewBox="0 0 1200 675"><rect width="1200" height="675" fill="${dark ? "#0e141c" : "#fff"}"/>${Array.from({ length: 60 }, (_, i) => { const x = 40 + i * 18, y = 120 + Math.abs(Math.sin(i / 6)) * 300 + i * 3, h = 20 + (i * 37) % 60, up = (i * 7) % 3 === 0; return `<rect x="${x}" y="${y}" width="10" height="${h}" fill="${up ? "#2bd08f" : "#ff5c7a"}"/>`; }).join("")}<text x="40" y="60" font-size="34" fill="${dark ? "#e6edf3" : "#111"}" font-family="sans-serif">${label}</text></svg>`;

function mkSetups(px, now) {
  const t = (m) => new Date(now - m * 60000).toISOString();
  const lv = (e, r) => ({ entry: e, sl: e + r, tp_1r: e - r, tp_2r: e - 2 * r, tp_3r: e - 3 * r, r, atr: r / 1.5 });
  const steps = (n, ok) => Array.from({ length: n }, (_, i) => ({ id: i + 1, label: `(${i + 1}) Bước ${i + 1} của kịch bản`, ok: i < ok, detail: i < ok ? `đạt: tỉ lệ ${(0.3 + i * 0.1).toFixed(2)}` : "chưa thoả" }));
  const S = [
    ["kb1", "XAUUSD", "M15", "triggered", 82, 6, 6], ["kb2", "XAUUSD", "H1", "armed", 71, 4, 3], ["kb3", "EURUSD", "H1", "forming", 44, 4, 2],
    ["kb4", "CRYPTO:BTCUSDT", "H4", "armed", 66, 6, 5], ["kb2", "GBPUSD", "M15", "forming", 38, 4, 1], ["kb1", "USDJPY", "H1", "triggered", 77, 6, 6],
  ];
  return S.map(([p, sym, tf, state, score, n, ok], i) => {
    const base = sym === "XAUUSD" ? px : sym === "EURUSD" ? 1.09 : sym === "GBPUSD" ? 1.31 : sym === "USDJPY" ? 149.2 : 64000;
    const r = base * 0.0025;
    const id = `${p}-${sym}-${tf}-${i}`;
    return { setup_id: id, pattern: p, name: `${p.toUpperCase()}: kịch bản Sell mẫu`, symbol: sym, tf, side: "sell", state, score, first_ts: t(600 + i * 40), last_ts: t(20 + i * 30), bar_ts: t(20 + i * 30),
      levels: state === "forming" ? {} : lv(base, r), steps: steps(n, ok), image: `/v1/patterns/media/${i + 1}.png`,
      events: [{ id: i * 10 + 1, state: "forming", ts: t(600), bar_ts: t(600), score: score - 20, image: null }, ...(state !== "forming" ? [{ id: i * 10 + 2, state: "armed", ts: t(200), bar_ts: t(200), score: score - 5, image: `/v1/patterns/media/${i + 1}.png` }] : []), ...(state === "triggered" ? [{ id: i * 10 + 3, state: "triggered", ts: t(20), bar_ts: t(20), score, image: `/v1/patterns/media/${i + 1}.png` }] : [])],
      trade: state === "triggered" ? { id: i + 100, setup_id: id, pattern: p, symbol: sym, tf, side: "sell", opened_at: t(20), entry: base, sl: base + r, r, tp: [base - r, base - 2 * r, base - 3 * r], status: "open", closed_at: null, legs: [{ tp: base - r, status: "tp", exit: base - r, exit_ts: t(5), r: 1 }, { tp: base - 2 * r, status: "open" }, { tp: base - 3 * r, status: "open" }], result_r: null, cost_r: 0.02, mfe_r: 1.3, mae_r: -0.4, bars_held: 4, replay: false, hash: "ab" } : null };
  });
}

(async () => {
  const browser = await chromium.launch();
  const st = await login(browser);
  const res = {};
  for (const [vp, w, h, mob] of [["1366", 1366, 900, false], ["375", 375, 812, true]]) for (const theme of ["dark", "light"]) {
    const ctx = await browser.newContext({ viewport: { width: w, height: h }, isMobile: mob, hasTouch: mob, colorScheme: theme, locale: "vi-VN", timezoneId: "Asia/Ho_Chi_Minh", storageState: st });
    await ctx.addInitScript(([t]) => { try { localStorage.setItem("ts-ux", JSON.stringify({ onboarded: 99, theme: t })); localStorage.setItem("ts-theme", t); } catch {} }, [theme]);
    const page = await ctx.newPage();
    const errs = []; page.on("pageerror", (e) => errs.push(String(e))); page.on("console", (m) => { if (m.type() === "error") errs.push(m.text().slice(0, 200)); });
    let setups = [];
    if (MOCK) {
      await page.goto(`${BASE}/#/gioi-thieu`, { waitUntil: "domcontentloaded" });
      const px = await page.evaluate(async () => { try { const r = await fetch("/api/v1/bars?symbol=XAUUSD&tf=M15&limit=5&order=desc"); const j = await r.json(); return j.items?.[0]?.c ?? 2650; } catch { return 2650; } });
      console.log("px", px);
      const now = Date.now(); setups = mkSetups(px, now);
      const trades = [...setups.filter((s) => s.trade).map((s) => s.trade), ...Array.from({ length: 12 }, (_, i) => ({ id: 200 + i, setup_id: `old-${i}`, pattern: `kb${(i % 4) + 1}`, symbol: ["XAUUSD", "EURUSD", "GBPUSD"][i % 3], tf: ["M15", "H1"][i % 2], side: "sell", opened_at: new Date(now - (i + 2) * 86400e3).toISOString(), entry: 2600 + i, sl: 2610 + i, r: 10, tp: [], status: "closed", closed_at: new Date(now - (i + 1.5) * 86400e3).toISOString(), legs: [], result_r: [1.6, -1, 2.1, -1, 0.4, -1, 1, 3, -1, -0.2, 1.4, -1][i], cost_r: 0.03, mfe_r: 2, mae_r: -0.6, bars_held: 10 + i, replay: i > 8, hash: "x" }))];
      let cum = 0; const eq = trades.filter((t) => t.status === "closed").sort((a, b) => a.closed_at.localeCompare(b.closed_at)).map((t) => ({ t: t.closed_at, cum_r: +(cum += t.result_r).toFixed(2) }));
      const bp = (k) => [...new Set(trades.map((t) => t[k]))].map((v) => ({ key: v, n_closed: 3, winrate: 0.5, avg_r: 0.3, sum_r: 0.9, pf: 1.4 }));
      const examples = Array.from({ length: 5 }, (_, i) => ({ id: `ex${i}`, pattern: `kb${(i % 3) + 1}`, title: i < 3 ? `Ảnh mẫu KB-${(i % 3) + 1} (golden)` : "Setup đã kích hoạt", symbol: "XAUUSD", tf: "M15", ts: new Date(now - i * 86400e3).toISOString(), note: i < 3 ? "Ví dụ chuẩn dùng để kiểm thử detector" : null, image: `/v1/patterns/examples/ex${i}.png` }));
      const spec = { items: ["KB-1", "KB-2", "KB-3", "KB-4"].map((k, i) => ({ id: k, name: `${k}: kịch bản Sell số ${i + 1}`, side: "sell", summary: "Sóng giảm mạnh -> hồi -> cấu trúc phân phối -> nến kích hoạt khi ĐÓNG.", steps: [1, 2, 3, 4, 5].map((n) => ({ id: n, label: `(${n}) bước ${n}` })), invalidation: ["Đóng cửa vượt đỉnh cấu trúc + 0.25 ATR", "Quá hạn"], params: { retr_min: 0.15, retr_max: 0.6, equal_tol: 0.25, trigger_window: 8 } })) };
      await page.route(/\/api\/v1\/patterns\//, async (route) => {
        const u = new URL(route.request().url()); const p = u.pathname.replace("/api/v1/patterns", "");
        const J = (o) => route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(o) });
        if (p.endsWith(".png")) return route.fulfill({ status: 200, contentType: "image/svg+xml", body: svg(p.split("/").pop(), theme === "dark") });
        if (p === "/live") { const v = u.searchParams.get("view"); return J({ items: v === "history" ? setups.map((s, i) => ({ ...s, state: i % 2 ? "invalid" : "triggered" })) : setups }); }
        if (p === "/setup") { const s = setups.find((x) => x.setup_id === u.searchParams.get("setup_id")) || setups[0]; const m = s.symbol === "XAUUSD" ? { marks: [{ t: s.first_ts, p: s.levels.sl, label: "(1)", kind: "high" }, { t: s.bar_ts, p: s.levels.entry, label: "Kích hoạt", kind: "trigger" }] } : {}; return J({ ...s, ...m }); }
        if (p === "/trades") return J({ items: trades });
        if (p === "/stats") return J({ as_of: new Date(now).toISOString(), overall: { n_closed: 12, n_open: 2, wins: 6, losses: 6, winrate: 0.5, avg_r: 0.31, sum_r: 3.7, pf: 1.52, max_dd_r: -3 }, by_pattern: bp("pattern"), by_tf: bp("tf"), by_symbol: bp("symbol"), equity: eq, ledger: { ok: true, n: 26, head: "9f1c0e7a55aa" }, note: "Chi phí giả định đã trừ vào R." });
        if (p === "/examples") return J({ items: examples });
        if (p === "/spec") return J(spec);
        return route.fulfill({ status: 404, body: "{}" });
      });
    }
    const full = async (path) => {
      const hh = await page.evaluate(() => { let m = innerHeight; for (const el of document.querySelectorAll("main, [class*=scroll], div")) { if (el.scrollHeight > el.clientHeight + 4 && getComputedStyle(el).overflowY !== "visible" && el.clientHeight > innerHeight * 0.5) m = Math.max(m, el.scrollHeight + (innerHeight - el.clientHeight)); } return Math.min(m, 6000); });
      if (!mob && hh > h) { await page.setViewportSize({ width: w, height: hh }); await page.waitForTimeout(600); }
      await page.screenshot({ path, fullPage: true });
      if (!mob) await page.setViewportSize({ width: w, height: h });
    };
    const tag = `${vp}-${theme}${MOCK ? "" : "-live"}`;
    await page.goto(`${BASE}/#/kich-ban`, { waitUntil: "domcontentloaded" });
    const force = () => page.evaluate((t) => { document.documentElement.dataset.theme = t; }, theme);
    await page.waitForSelector("text=Kịch bản Sell", { timeout: 20000 }).catch(() => {});
    await page.waitForTimeout(2500); await force();
    await full(`${OUT}/scenarios-${tag}-live.png`);
    const body = (await page.textContent("body")).toLowerCase();
    const banned = ["dukascopy", "yahoo", "binance", "ccxt", "frankfurter", "mt5", "oanda"].filter((x) => body.includes(x));
    const hscroll = await page.evaluate(() => document.documentElement.scrollWidth > innerWidth + 1);
    if ((await page.locator(".sc-card").count()) > 0) {
      await page.locator(".sc-card").first().click(); await page.waitForSelector(".sc-chart canvas", { timeout: 40000 }).catch(() => {}); await page.waitForTimeout(1500); console.log("dbg", await page.evaluate(() => [document.querySelectorAll(".sc-chart canvas").length, document.querySelector(".sc-drawer")?.innerText.slice(0, 50)])); await force();
      await page.screenshot({ path: `${OUT}/scenarios-${tag}-detail.png`, fullPage: false });
      const dlg = page.locator('[role="dialog"]').first();
      await dlg.evaluate((el) => { const s = el.querySelector(".overflow-y-auto"); if (s) s.scrollTop = 900; });
      await page.waitForTimeout(500);
      await page.screenshot({ path: `${OUT}/scenarios-${tag}-detail2.png`, fullPage: false });
      await page.keyboard.press("Escape"); await page.waitForTimeout(300);
    }
    for (const [name, label] of [["history", "Lịch sử & paper"], ["examples", "Thư viện ví dụ"], ["spec", "Mô tả KB-1..KB-4"]]) {
      await page.getByRole("tab", { name: label }).click(); await page.waitForTimeout(1800); await force();
      await full(`${OUT}/scenarios-${tag}-${name}.png`);
    }
    res[tag] = { errs: errs.slice(0, 8), banned, hscroll };
    await ctx.close();
  }
  fs.writeFileSync(`${OUT}/results.json`, JSON.stringify(res, null, 2));
  console.log(JSON.stringify(res, null, 2));
  await browser.close();
})().catch((e) => { console.error(e); process.exit(1); });
