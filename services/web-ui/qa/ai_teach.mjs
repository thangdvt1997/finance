// QA khung "Dạy kịch bản mới" (master, backend thật): nạp YAML + ảnh mẫu, chạy detector + backtest nền, chụp 3 độ phân giải x sáng/tối.
// KHÔNG mở test khoá trong QA. Kiểm: không tràn ngang, không lộ tên nguồn, không nút đặt lệnh, ảnh không hỏng.
import { chromium } from "playwright";
import fs from "node:fs";
const BASE = process.env.BASE || "http://127.0.0.1:8580", OUT = process.env.OUT || "out";
fs.mkdirSync(OUT, { recursive: true });
const PNG = Buffer.from("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg==", "base64");
fs.writeFileSync(`${OUT}/mau1.png`, PNG);
const ID = `SC-QA-${Math.random().toString(36).slice(2, 7)}`;
const YAML = `id: ${ID}
name: "QA ${ID}"
summary: "Kịch bản thử QA giao diện"
side: sell
symbols: [EURUSD]
tfs: [H1]
detector:
  cooldown_bars: 8
  rules:
    - {rule: move_atr, dir: up, bars: 6, min: 2.0}
    - {rule: upper_wick, min_ratio: 0.4}
levels:
  sl: {type: swing_high, bars: 6, buffer_atr: [0.25, 0.5]}
  tp_r: [1.0, 2.0]
  max_hold: 60
golden:
  - {symbol: EURUSD, tf: H1, bar_ts: "2024-08-23T18:00", expect: true, image: mau1.png}
`;
const browser = await chromium.launch();
const res = [], errs = [];
const sizes = [[1440, 900, "desktop"], [820, 1100, "tablet"], [390, 800, "mobile"]];
let first = true;
for (const [w, h, name] of sizes) for (const th of ["dark", "light"]) {
  const ctx = await browser.newContext({ viewport: { width: w, height: h }, colorScheme: th, baseURL: BASE });
  const r = await ctx.request.post(`${BASE}/auth/login`, { data: { platform: "master", login: process.env.QA_USER, secret: process.env.QA_PASS }, headers: { Origin: BASE, "Content-Type": "application/json" } });
  await ctx.addInitScript((t) => { try { const v = JSON.parse(localStorage.getItem("ts-ux") || "{}"); v.onboarded = 99; localStorage.setItem("ts-ux", JSON.stringify(v)); localStorage.setItem("ts-theme", t); } catch { /* bỏ */ } }, th);
  const page = await ctx.newPage(); page.setDefaultTimeout(15000);
  page.on("pageerror", (e) => errs.push(String(e.message).slice(0, 200)));
  page.on("response", (rs) => { if (/ai-trading\/scenarios/.test(rs.url()) && rs.request().method() === "POST") console.log("POST", rs.url().split("/api")[1], rs.status()); });
  await page.goto(`${BASE}/#/ai-trading`, { waitUntil: "load" });
  await page.waitForTimeout(2500);
  console.log("url", page.url(), "login", r.status());
  await page.getByRole("tab").nth(1).click().catch(async (e) => { await page.screenshot({ path: `${OUT}/teach-debug.png` }); console.log("tab fail", (await page.locator("body").innerText()).slice(0, 300)); throw e; });
  await page.waitForTimeout(1200);
  if (first) {
    await page.locator("textarea").fill(YAML);
    await page.locator('input[type=file][accept^="image"]').setInputFiles(`${OUT}/mau1.png`);
    await page.getByRole("button", { name: /Kiểm tra & lưu/ }).click();
    await page.getByText(/Đã lưu kịch bản/).waitFor();
    await page.getByText("Quy trình trung thực").first().waitFor({ timeout: 20000 }).catch(async () => { await page.screenshot({ path: `${OUT}/teach-debug.png`, fullPage: true }); console.log("flow missing", await page.evaluate(() => [...document.querySelectorAll(".seg button")].map((b) => b.textContent.slice(0, 30) + (b.getAttribute("aria-pressed") || b.className.includes("on") ? "*" : "")).join(" | "))); });
    for (const lab of [/1\. Detector/, /2\. Backtest/]) {
      await page.getByText(lab).locator("xpath=ancestor::div[contains(@class,'flex')][1]").getByRole("button", { name: /Chạy/ }).click();
      await page.getByText(/Xong/).first().waitFor({ timeout: 120000 }).catch(() => {});
      await page.waitForFunction(() => !document.querySelector("[role=progressbar]") || document.body.innerText.includes("Xong"), null, { timeout: 120000 }).catch(() => {});
      await page.waitForTimeout(4000);
    }
    first = false;
  } else {
    await page.getByRole("button", { name: new RegExp(`QA ${ID}`) }).click().catch(() => {});
    await page.waitForTimeout(2500);
  }
  await page.evaluate(async () => { for (let y = 0; y < document.body.scrollHeight; y += 600) { window.scrollTo(0, y); await new Promise((r) => setTimeout(r, 120)); } window.scrollTo(0, 0); });
  const info = await page.evaluate(() => {
    const txt = document.body.innerText;
    return {
      overflow: document.documentElement.scrollWidth > innerWidth + 1,
      offender: [...document.querySelectorAll("body *")].filter((e) => e.getBoundingClientRect().right > innerWidth + 1 && !e.closest("table,.scroll-x,[class*=overflow],nav,[role=tablist],textarea")).slice(0, 3).map((e) => e.tagName + "." + String(e.className).slice(0, 40)),
      flow: /Quy trình trung thực/.test(txt), leak: /binance|yahoo|metaquotes|twelve|dukascopy|mt5/i.test(txt),
      orderBtn: [...document.querySelectorAll("button,a")].some((b) => /^(buy|sell|đặt lệnh|mua|bán|place order)$/i.test(b.textContent.trim())),
      broken: [...document.querySelectorAll("img")].filter((i) => i.complete && i.naturalWidth === 0).length,
      labelled: !!document.querySelector("textarea[aria-label]"),
    };
  });
  await page.screenshot({ path: `${OUT}/teach-${name}-${th}.png`, fullPage: true }).catch(() => {});
  res.push({ w, th, login: r.status(), ...info }); console.log(JSON.stringify(res.at(-1)));
  await ctx.close();
}
console.log("scenario", ID, "errors", JSON.stringify(errs));
