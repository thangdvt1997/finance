// Demo đầu-cuối AI Training Class trên backend THẬT (master): giao kịch bản 3 câu -> AI hỏi -> /quet -> gắn nhãn -> /luu -> /test -> thẻ kết quả. KHÔNG mở test khoá.
import { chromium } from "playwright";
import fs from "node:fs";
const BASE = process.env.BASE || "http://127.0.0.1:8580", OUT = process.env.OUT || "out";
fs.mkdirSync(OUT, { recursive: true });
const PNG = Buffer.from("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg==", "base64");
fs.writeFileSync(`${OUT}/anh-mau.png`, PNG);
const browser = await chromium.launch(); const log = (...a) => console.log(new Date().toISOString().slice(11, 19), ...a); const errs = [];
const ctx = await browser.newContext({ viewport: { width: 1440, height: 1000 }, colorScheme: "dark", baseURL: BASE });
const lg = await ctx.request.post(`${BASE}/auth/login`, { data: { platform: "master", login: process.env.QA_USER, secret: process.env.QA_PASS }, headers: { Origin: BASE, "Content-Type": "application/json" } });
await ctx.addInitScript(() => { try { const v = JSON.parse(localStorage.getItem("ts-ux") || "{}"); v.onboarded = 99; localStorage.setItem("ts-ux", JSON.stringify(v)); localStorage.removeItem("cr-room"); } catch { /* bỏ */ } });
const page = await ctx.newPage(); page.setDefaultTimeout(20000);
page.on("pageerror", (e) => errs.push(String(e.message).slice(0, 200)));
page.on("response", (rs) => { if (/ai-trading\/class/.test(rs.url()) && rs.status() >= 400 && rs.request().method() !== "GET") log("HTTP", rs.request().method(), rs.url().split("/class")[1], rs.status()); });
const shot = (n) => page.screenshot({ path: `${OUT}/e2e-${n}.png` }).catch(() => {});
const ta = () => page.locator("textarea[aria-label='Tin nhắn']");
const say = async (t, wait = 150000) => { await ta().fill(t); await ta().press("Enter"); await page.locator(".cr-msg.ai[aria-busy]").waitFor({ state: "detached", timeout: wait }).catch(() => {}); await page.waitForTimeout(1500); };
log("login", lg.status());
await page.goto(`${BASE}/#/ai-trading`, { waitUntil: "load" });
await page.getByRole("tab", { name: /AI Training Class/ }).first().click(); await page.waitForTimeout(2500); await shot("0-vao");
const title = `QA demo ${Math.random().toString(36).slice(2, 6)}`;
await page.getByRole("button", { name: /Phòng mới/ }).click(); await page.getByLabel("Tên phòng").fill(title); await page.getByRole("button", { name: "Tạo phòng" }).click();
await page.getByRole("heading", { name: title }).waitFor(); log("room created"); await shot("1-phong");
await say("Kịch bản sell EURUSD khung H1. Sau đà tăng mạnh 6 nến liên tiếp, xuất hiện nến có bóng trên dài, thân nhỏ. Vào bán khi giá phá đáy nến đó, SL trên đỉnh bóng, TP 2R."); log("sent scenario"); await shot("2-ai-hoi");
await say("EURUSD, khung H1."); await say("Đà tăng ít nhất 2 ATR trong 6 nến, bóng trên dài ít nhất 40% của nến, thân giảm nhỏ."); await say("Vào lệnh bán khi giá phá đáy nến tín hiệu."); await say("SL trên đỉnh bóng trên cộng 0.5 ATR, TP 2R, giữ tối đa 60 nến."); await shot("3-hoi-tiep");
await say("/tom-tat"); await shot("4-tom-tat");
await page.getByRole("tab", { name: /Ví dụ/ }).click();
await say("/quet", 30000); log("quet requested");
const scan = await page.locator(".cr-thumbs img").first().waitFor({ timeout: 240000 }).then(() => true).catch(() => false); log("scan thumbs", scan); await shot("5-quet");
if (scan) {
  await page.waitForTimeout(1500);
  const btns = page.locator(".cr-ex");
  const cnt = await btns.count(); log("examples", cnt);
  for (let i = 0; i < Math.min(cnt, 6); i++) { const ex = btns.nth(i); await ex.locator("input").fill(i % 3 === 2 ? "Thân quá lớn, không phải pin bar" : "Đúng hình mẫu"); await ex.getByRole("button", { name: i % 3 === 2 ? "SAI" : i % 3 === 1 ? "GẦN ĐÚNG" : "ĐÚNG" }).click(); await page.waitForTimeout(500); }
  await page.waitForTimeout(1500); await shot("6-nhan");
}
await ta().setInputFiles?.call; await page.locator("input[type=file]").first().setInputFiles(`${OUT}/anh-mau.png`);
await page.locator(".cr-tray input").first().fill("Ảnh mẫu QA"); await page.getByRole("button", { name: "Gửi" }).click(); await page.waitForTimeout(2500); await shot("7-dinhkem");
await say("/luu bản QA", 30000); await shot("8-luu");
await say("/test", 30000); await shot("9-test-xacnhan");
const conf = page.getByRole("button", { name: /Xác nhận chạy/ });
if (await conf.count()) { await conf.first().click(); log("test confirmed"); await page.waitForTimeout(3000); await shot("10-test-chay"); }
const card = await page.getByText(/Kết quả test \(walk-forward/).first().waitFor({ timeout: 420000 }).then(() => true).catch(() => false); log("result card", card); await shot("11-ket-qua");
await page.getByRole("tab", { name: /Sổ tay/ }).click(); await page.waitForTimeout(1500); await shot("12-so-tay");
await page.getByRole("button", { name: /Xuất & kiểm tra/ }).click(); await page.waitForTimeout(2500); await shot("13-xuat-yaml");
const txt = await page.evaluate(() => document.body.innerText);
log("leak", /binance|yahoo|metaquotes|twelve|dukascopy|\bmt5\b/i.test(txt), "orderBtn", await page.evaluate(() => [...document.querySelectorAll("button,a")].some((b) => /^(buy|sell|đặt lệnh|mua|bán|place order)$/i.test(b.textContent.trim()))));
log("errors", JSON.stringify(errs)); await browser.close();
