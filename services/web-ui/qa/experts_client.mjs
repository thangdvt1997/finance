// QA trang "Chuyên gia & đồng thuận" của client-ui (chế độ mẫu ?mock=1&mockexp=1: đăng nhập mẫu, dữ liệu chuyên gia mẫu). Chạy bằng run_expert.sh experts_client.mjs
import { chromium } from "playwright";
import fs from "node:fs";

const BASE = process.env.CBASE || "http://127.0.0.1:8581/c/";
const OUT = process.env.OUT || "out";
fs.mkdirSync(OUT, { recursive: true });
const browser = await chromium.launch();
const errors = [];
for (const scheme of ["dark", "light"]) {
  for (const [vn, w, h] of [["mob", 375, 812], ["desk", 1366, 768]]) {
    const ctx = await browser.newContext({ viewport: { width: w, height: h }, colorScheme: scheme, ignoreHTTPSErrors: true });
    const page = await ctx.newPage();
    page.setDefaultTimeout(10000);
    page.on("pageerror", (e) => errors.push(`pageerror ${String(e.message).slice(0, 200)}`));
    page.on("console", (m) => { if (m.type() === "error") errors.push(`console ${m.text().slice(0, 160)}`); });
    await page.goto(`${BASE}?mock=1&mockexp=1`, { waitUntil: "networkidle" }).catch(() => {});
    await page.fill('input[autocomplete="username"]', "12345678");
    await page.fill('input[autocomplete="current-password"]', "demo-cong-1");
    await page.click('button[type="submit"]');
    await page.waitForSelector("main#main-content", { timeout: 15000 });
    await page.evaluate(() => { location.hash = "#/chuyen-gia"; });
    await page.waitForTimeout(2200);
    const name = `client-${scheme}-${vn}`;
    await page.screenshot({ path: `${OUT}/${name}.png`, fullPage: true });
    const a = await page.evaluate(() => {
      const vw = document.documentElement.clientWidth, t = document.body.innerText;
      return { overflowX: document.documentElement.scrollWidth > vw + 1, banned: /dukascopy|yahoo|binance|reuters|myfxbook|https?:\/\//i.test(t), h1: document.querySelector("h1")?.innerText, note: /không vượt ngẫu nhiên|do not beat chance/.test(t), cards: document.querySelectorAll(".xc-card").length, bars: document.querySelectorAll(".xc-bar").length };
    });
    console.log(name, JSON.stringify(a));
    await ctx.close();
  }
}
console.log("errors", JSON.stringify(errors.slice(0, 10)));
await browser.close();
