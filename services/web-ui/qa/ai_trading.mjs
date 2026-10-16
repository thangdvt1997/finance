// QA trang AI Trading. MOCK=1: chặn /api/v1/ai-trading/* bằng fixture (CHỈ trong QA, không có trong bản chạy thật); MOCK=0: gọi backend thật (404 -> trạng thái rỗng).
// ROLE=client: đăng nhập client (BASE client-ui), kiểm trang #/ai-trading rút gọn. Kiểm: tràn ngang, không lộ tên nguồn, không có nút đặt lệnh.
import { chromium } from "playwright";
import fs from "node:fs";
const BASE = process.env.BASE || "http://127.0.0.1:8580", OUT = process.env.OUT || "out", MOCK = process.env.MOCK !== "0", ROLE = process.env.ROLE || "master";
fs.mkdirSync(OUT, { recursive: true });
const card = (o) => ({ status: "research", summary: "", warning: "", metrics: {}, ...o });
const FIX = {
  overview: { strategies: [
    card({ id: "kb-sell", name: "Kịch bản Sell KB-1..KB-4", module: "pattern", status: "paper", summary: "4 kịch bản nến và sóng, backtest trung thực walk-forward.", metrics: { expectancy_r: -0.1, p_vs_random: 0.62, trades: 412 }, verdict: "no_edge", warning: "Không có edge sau chi phí; test khoá -0,26R/lệnh." }),
    card({ id: "ml-meta", name: "Meta-labeling GBM", module: "ml", status: "research", summary: "Lọc tín hiệu pattern.", metrics: { expectancy_r: null, p_vs_random: null, trades: 0 }, verdict: "unproven", warning: "Chưa chạy." }),
    card({ id: "llm-an", name: "LLM analyst", module: "llm", status: "paused", verdict: "unproven" }),
  ], warnings: ["Mọi kết quả là backtest/paper, không đảm bảo tương lai.", "KB-1..4 không có edge."], arena: [{ id: "kb-sell", name: "Kịch bản Sell KB-1..KB-4", pnl_r: -12.4, trades: 38, since: "2026-10-01T00:00:00Z" }, { id: "ml-meta", name: "Meta-labeling GBM", pnl_r: 0, trades: 0, since: "2026-10-10T00:00:00Z" }], updated_at: "2026-10-15T04:00:00Z" },
  detail: { ...card({ id: "kb-sell", name: "Kịch bản Sell KB-1..KB-4", module: "pattern", status: "paper", summary: "4 kịch bản.", metrics: { expectancy_r: -0.1, p_vs_random: 0.62, trades: 412 }, verdict: "no_edge", warning: "Không có edge." }),
    backtest: { expectancy_r: -0.1, ci95: [-0.21, 0.01], p_vs_random: 0.62, max_dd_r: -48.2, trades: 412, splits: { dev: { expectancy_r: -0.05, trades: 200 }, val: { expectancy_r: -0.1, trades: 112 }, test: { expectancy_r: -0.26, trades: 100 } } },
    forward_paper: { trades: 38, pnl_r: -12.4 }, charts: ["/ai-trading/charts/equity.png"], examples: [{ id: "ex1", result: "win", image_url: "/ai-trading/ex1.png" }, { id: "ex2", result: "loss", image_url: "/ai-trading/ex2.png" }], honesty_note: "Test khoá đã mở một lần; kết quả âm." },
  lab: { experiments: [{ id: "E1", params: { tf: "H1", atr: 14 }, snapshot_sha: "abcdef1234567", result: "-0.10R", date: "2026-10-12" }], backlog: [{ id: "B1", idea: "Meta-labeling", module: "ml", status: "planned", doc: "docs/AI_TRADING.md" }] },
};
const PNG = Buffer.from("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg==", "base64");
const browser = await chromium.launch();
let STATE = null;
const media = {};
const res = []; const errs = [];
const sizes = [[1440, 900, "desktop"], [820, 1100, "tablet"], [390, 800, "mobile"]];
for (const [w, h, name] of sizes) for (const th of ["dark", "light"]) {
  const ctx = await browser.newContext({ viewport: { width: w, height: h }, colorScheme: th, baseURL: BASE, ...(ROLE === "client" && STATE ? { storageState: STATE } : {}) });
  const r = ROLE === "client" ? { status: () => 0 } : await ctx.request.post(`${BASE}${ROLE === "client" ? "/c" : ""}/auth/login`, { data: { platform: ROLE === "client" ? "mt5" : "master", login: process.env.QA_USER, secret: process.env.QA_PASS }, headers: { Origin: BASE, "Content-Type": "application/json" } });
  await ctx.addInitScript((t) => { try { const v = JSON.parse(localStorage.getItem("ts-ux") || "{}"); v.onboarded = 99; localStorage.setItem("ts-ux", JSON.stringify(v)); localStorage.setItem("ts-theme", t); } catch { /* bỏ */ } }, th);
  if (MOCK) {
    await ctx.route(/\/api\/v1\/ai-trading\/overview/, (rt) => rt.fulfill({ json: FIX.overview }));
    await ctx.route(/\/api\/v1\/ai-trading\/strategies\//, (rt) => rt.fulfill({ json: FIX.detail }));
    await ctx.route(/\/api\/v1\/ai-trading\/lab/, (rt) => rt.fulfill({ json: FIX.lab }));
    await ctx.route(/\/api\/v1\/ai-trading\/arena/, (rt) => rt.fulfill({ json: { arena: FIX.overview.arena } }));
    await ctx.route(/\/api\/ai-trading\/.*\.png/, (rt) => rt.fulfill({ body: PNG, contentType: "image/png" }));
  }
  const page = await ctx.newPage(); page.setDefaultTimeout(10000);
  page.on("response", (rs) => { if (/ai-trading\/media/.test(rs.url())) if (rs.status() === 404) (media.u ||= new Set()).add(rs.url().split("/media/")[1]); media[rs.status()] = (media[rs.status()] || 0) + 1; });
  page.on("pageerror", (e) => errs.push(String(e.message).slice(0, 200)));
  if (ROLE === "client" && !STATE) { // đăng nhập bằng fetch trong trang (cookie phiên), đổi mật khẩu bắt buộc một lần (ngẫu nhiên, chỉ trong bộ nhớ)
    await page.goto(`${BASE}/c/`);
    const post = (p, d) => page.evaluate(async ([u, b]) => { const x = await fetch(u, { method: "POST", credentials: "same-origin", headers: { "Content-Type": "application/json" }, body: JSON.stringify(b) }); let j = {}; try { j = await x.json(); } catch {} return { st: x.status, j }; }, [`${BASE}/c/auth/${p}`, d]);
    let pw = process.env.QA_PASS; let lr = await post("login", { platform: "mt5", login: process.env.QA_USER, secret: pw }); console.log("l1", lr.st, JSON.stringify(lr.j).slice(0,120));
    if (lr.j.must_change_password) { const np = `Qa-${Math.random().toString(36).slice(2)}-${Date.now()}`; const cp = await post("change-password", { current_password: pw, new_password: np }); console.log("cp", cp.st, JSON.stringify(cp.j).slice(0,120)); lr = await post("login", { platform: "mt5", login: process.env.QA_USER, secret: np }); }
    console.log("client login", lr.st, JSON.stringify(lr.j).slice(0, 160)); STATE = await ctx.storageState();
  }
  await page.goto(`${BASE}${ROLE === "client" ? "/c" : ""}/#/ai-trading`, { waitUntil: "load" }); await page.waitForTimeout(1500);
  const tabs = ROLE === "client" ? [null] : ["overview", "pattern", "models", "risk", "lab", "legal"];
  const path = ROLE === "client" ? "/c/#/ai-trading" : "/#/ai-trading";
  for (const tab of tabs) {
    if (tab !== tabs[0] || ROLE === "client") { /* tab đầu: mặc định */ }
    if (tab) await page.getByRole("tab").nth(tabs.indexOf(tab)).click();
    else if (!page.url().includes("ai-trading")) await page.goto(`${BASE}${path}`, { waitUntil: "load" });
    if (tab === tabs[0] || !tab) { if (tab === tabs[0] && !page.url().includes("ai-trading")) await page.goto(`${BASE}${path}`, { waitUntil: "load" }); }
    await page.waitForTimeout(1200); await page.evaluate(async () => { for (let y = 0; y < document.body.scrollHeight; y += 600) { window.scrollTo(0, y); await new Promise((r) => setTimeout(r, 120)); } window.scrollTo(0, 0); }); await page.waitForTimeout(1200);
    const info = await page.evaluate(() => {
      const txt = document.body.innerText;
      return {
        overflow: document.documentElement.scrollWidth > innerWidth + 1,
        offender: [...document.querySelectorAll("body *")].filter((e) => e.getBoundingClientRect().right > innerWidth + 1 && !e.closest("table,.scroll-x,[class*=overflow],nav,[role=tablist]")).slice(0, 3).map((e) => e.tagName + "." + String(e.className).slice(0, 40)),
        honest: /không có edge|no edge/i.test(txt), leak: /binance|yahoo|metaquotes|twelve|dukascopy/i.test(txt),
        orderBtn: [...document.querySelectorAll("button,a")].some((b) => /^(buy|sell|đặt lệnh|mua|bán|place order)$/i.test(b.textContent.trim())),
        broken: [...document.querySelectorAll("img")].filter((i) => i.complete && i.naturalWidth === 0).length,
      };
    });
    await page.screenshot({ path: `${OUT}/ai-${ROLE}-${name}-${th}-${tab || "main"}.png`, fullPage: true }).catch(() => {});
    res.push({ role: ROLE, mock: MOCK, w, th, tab, login: r.status(), ...info }); console.log(JSON.stringify(res.at(-1)));
  }
  await ctx.close();
}
console.log("media", JSON.stringify({ ...media, u: [...(media.u || [])].slice(0, 30) })); console.log("errors", JSON.stringify(errs));
fs.writeFileSync(`${OUT}/ai-results-${ROLE}-${MOCK ? "mock" : "real"}.json`, JSON.stringify({ res, errs }, null, 1));
await browser.close();
