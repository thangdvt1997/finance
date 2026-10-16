// QA trực quan Market Intelligence (agent C): chạy từng trang intel, chụp ảnh, thu lỗi console/pageerror, kiểm từ cấm (tên nguồn), tràn ngang.
// Chạy trong container Playwright tạm qa-ui-c-* TRÊN VPS qua qa/run-c.sh. Biến: ONLY=prefix1,prefix2 ; VIEWPORT=WxH ; THEME=dark|light
import { chromium } from "playwright";
import fs from "node:fs";

const BASE = process.env.BASE || "http://127.0.0.1:8580";
const OUT = process.env.OUT || "out";
const USER = process.env.QA_USER, PASS = process.env.QA_PASS;
const ONLY = process.env.ONLY ? process.env.ONLY.split(",") : null;
const [VW, VH] = (process.env.VIEWPORT || "1600x950").split("x").map(Number);
const THEME = process.env.THEME || "dark";
fs.mkdirSync(OUT, { recursive: true });
const results = [];
let errors = [];
const ok = (name, cond, extra = "") => { results.push({ name, pass: !!cond, extra }); console.log(`${cond ? "PASS" : "FAIL"}  ${name}${extra ? "  " + String(extra).slice(0, 260) : ""}`); return !!cond; };

const browser = await chromium.launch();
const ctx = await browser.newContext({ viewport: { width: VW, height: VH }, colorScheme: THEME, timezoneId: "Asia/Ho_Chi_Minh", locale: "vi-VN", baseURL: BASE, acceptDownloads: true });
const lr = await ctx.request.post(`${BASE}/auth/login`, { data: { platform: "master", login: USER, secret: PASS }, headers: { Origin: BASE, "Content-Type": "application/json" } });
console.log("login", lr.status());
const page = await ctx.newPage();
page.setDefaultTimeout(9000);
page.on("pageerror", (e) => errors.push(`pageerror: ${String(e.message).slice(0, 300)}`));
page.on("console", (m) => { if (m.type() === "error") errors.push(`console: ${m.text().slice(0, 300)}`); });
page.on("response", (r) => { if (r.status() >= 400 && /\/api\//.test(r.url())) errors.push(`http ${r.status()} ${r.url().replace(BASE, "").slice(0, 120)}`); });
const shot = (n) => page.screenshot({ path: `${OUT}/${n}.png` });
const sleep = (ms) => page.waitForTimeout(ms);
await page.addInitScript((t) => { try { localStorage.setItem("ts-theme", t); } catch {} }, THEME);

const BANNED = /\b(dukascopy|yahoo|frankfurter|vnstock|vndirect|binance|okx|kucoin|cftc|investinglive|vneconomy|forexfactory|faireconomy|gdelt|reuters|cafef)\b|\bCOT\b/i;
const PAGES = [
  ["suc-manh-tien-te", "Sức mạnh tiền tệ", /Sức mạnh|tiền tệ/],
  ["ban-do-nhiet", "Bản đồ nhiệt", /nhiệt/i],
  ["movers", "Movers", /Tăng mạnh|Movers/i],
  ["tuong-quan-rui-ro", "Tương quan & rủi ro", /tương quan/i],
  ["phien-giao-dich", "Phiên giao dịch", /Phiên/],
  ["nhip-thi-truong", "Nhịp thị trường", /khẩu vị|Nhịp/i],
  ["vi-the-lon", "Vị thế lớn", /Vị thế/],
  ["tin-tuc", "Terminal tin tức", /Dòng tin|tin tức/i],
  ["lich", "Lịch kinh tế", /Lịch kinh tế/],
];
for (const [path, name, re] of PAGES) {
  if (ONLY && !ONLY.some((o) => path.startsWith(o))) continue;
  errors = [];
  try {
    await page.goto(`${BASE}/#/${path}`, { waitUntil: "load" });
    await page.waitForSelector("main h1", { timeout: 15000 }).catch(() => {});
    for (let i = 0; i < 2; i++) { if (await page.getByText("Chào mừng đến Trạm thị trường").count()) { await page.keyboard.press("Escape"); await sleep(300); } }
    await sleep(Number(process.env.WAIT || 3500));
    const info = await page.evaluate(() => {
      const m = document.querySelector("#main");
      return { text: (m?.innerText || "").slice(0, 6000), len: (m?.innerText || "").length, h1: document.querySelector("main h1")?.textContent || "", overflowX: document.documentElement.scrollWidth > document.documentElement.clientWidth + 2,
        skeleton: document.querySelectorAll('[role="status"][aria-label="Đang tải"]').length, alerts: [...document.querySelectorAll('[role="alert"]')].map((a) => a.textContent.slice(0, 120)),
        canvas: document.querySelectorAll("#main canvas").length };
    });
    const cols = await page.evaluate(() => {
      const c = (sel, prop = "color") => { const e = document.querySelector(`#main ${sel}`); return e ? `${getComputedStyle(e)[prop]} "${e.textContent.trim().slice(0, 14)}"` : null; };
      return { up: c(".up"), down: c(".down"), huBg: c('[class*="hu-"]', "backgroundColor"), hdBg: c('[class*="hd-"]', "backgroundColor") };
    });
    console.log(`  colors ${path}: ${JSON.stringify(cols)}`);
    const tag = `${path}-${VW}-${THEME}`;
    await shot(tag);
    ok(`${path}: render`, info.len > 200 && re.test(info.text + info.h1), `h1="${info.h1}" len=${info.len} canvas=${info.canvas}`);
    ok(`${path}: không tràn ngang`, !info.overflowX);
    ok(`${path}: hết skeleton`, info.skeleton === 0, `skeleton=${info.skeleton}`);
    ok(`${path}: không alert lỗi`, info.alerts.length === 0, info.alerts.join(" | "));
    const bad = BANNED.exec(info.text);
    ok(`${path}: không lộ tên nguồn`, !bad, bad ? bad[0] : "");
    ok(`${path}: không lỗi JS/HTTP`, errors.length === 0, errors.slice(0, 3).join(" || "));
  } catch (e) {
    ok(`${path}: EXC`, false, String(e.message).split("\n")[0]);
    await shot(`fail-${path}`).catch(() => {});
  }
}
fs.writeFileSync(`${OUT}/results.json`, JSON.stringify(results, null, 1));
const bad = results.filter((r) => !r.pass);
console.log(`\n${results.length - bad.length}/${results.length} PASS`);
await browser.close();
process.exit(bad.length ? 1 : 0);
