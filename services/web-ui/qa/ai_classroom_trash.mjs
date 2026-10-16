// E2E thùng rác phòng (backend THẬT, master, qua gateway): tạo 3 phòng QA -> xoá 1 (toast Hoàn tác) -> chọn nhiều + lọc demo -> bulk -> thùng rác -> khôi phục -> xoá vĩnh viễn. Dọn sạch phòng QA cuối.
import { chromium } from "playwright";
import fs from "node:fs";
const BASE = process.env.BASE || "http://127.0.0.1:8580", OUT = process.env.OUT || "out";
fs.mkdirSync(OUT, { recursive: true });
const browser = await chromium.launch(); const errs = []; let fails = 0;
const log = (...a) => console.log(new Date().toISOString().slice(11, 19), ...a);
const ok = (c, m) => { log(c ? "OK  " : "FAIL", m); if (!c) fails++; };
const ctx = await browser.newContext({ viewport: { width: 1440, height: 1000 }, colorScheme: "dark", baseURL: BASE });
const lg = await ctx.request.post(`${BASE}/auth/login`, { data: { platform: "master", login: process.env.QA_USER, secret: process.env.QA_PASS }, headers: { Origin: BASE, "Content-Type": "application/json" } });
await ctx.addInitScript(() => { try { const v = JSON.parse(localStorage.getItem("ts-ux") || "{}"); v.onboarded = 99; localStorage.setItem("ts-ux", JSON.stringify(v)); localStorage.setItem("cr-tour-done", "1"); localStorage.removeItem("cr-room"); } catch { /* bỏ */ } });
const page = await ctx.newPage(); page.setDefaultTimeout(20000);
page.on("pageerror", (e) => errs.push(String(e.message).slice(0, 200)));
page.on("response", async (rs) => { if (/ai-trading\/class/.test(rs.url()) && rs.status() >= 400 && rs.request().method() !== "GET") log("HTTP", rs.request().method(), rs.url().split("/class")[1], rs.status(), (await rs.text().catch(() => "")).slice(0, 160)); });
const shot = (n) => page.screenshot({ path: `${OUT}/trash-${n}.png` }).catch(() => {});
log("login", lg.status());
await page.goto(`${BASE}/#/ai-trading`, { waitUntil: "load" });
await page.waitForTimeout(3000); await shot("0-pre");
await page.getByRole("tab", { name: /AI Training Class/ }).first().click(); await page.waitForTimeout(2000);
const tag = Math.random().toString(36).slice(2, 6), names = [1, 2, 3].map((i) => `QA demo xoa ${tag} ${i}`);
for (const n of names) { await page.getByRole("button", { name: /Phòng mới/ }).click(); await page.getByLabel("Tên phòng").fill(n); await page.getByRole("button", { name: "Tạo phòng" }).click(); await page.getByRole("heading", { name: n }).waitFor(); }
ok(true, "tạo 3 phòng"); await shot("1-list");
// 1) xoá từ danh sách + hoàn tác
await page.getByRole("button", { name: `Xoá phòng ${names[0]}` }).click();
await page.getByTestId("confirm-delete").click();
await page.getByRole("status").filter({ hasText: /thùng rác/ }).waitFor(); await shot("2-toast");
await page.waitForTimeout(1500);
ok(await page.getByRole("button", { name: `Xoá phòng ${names[0]}` }).count() === 0, "phòng biến khỏi danh sách");
await page.getByRole("button", { name: "Hoàn tác" }).click(); await page.waitForTimeout(2500);
ok(await page.getByRole("button", { name: `Xoá phòng ${names[0]}` }).count() === 1, "hoàn tác khôi phục phòng");
// 2) menu phòng: xoá phòng đang mở rồi khôi phục từ Thùng rác
await page.getByRole("button", { name: new RegExp(names[2]) }).first().click(); await page.getByTestId("head-delete").click(); await page.getByTestId("confirm-delete").click(); await page.waitForTimeout(2500);
await page.getByTestId("trash-open").click(); await page.getByRole("dialog").waitFor(); await shot("3-trash");
ok(await page.getByRole("dialog").getByText(names[2]).count() === 1, "phòng nằm trong thùng rác");
await page.getByRole("dialog").getByRole("button", { name: "Khôi phục" }).first().click(); await page.waitForTimeout(2000);
await page.keyboard.press("Escape");
// 3) chọn nhiều + lọc demo
await page.getByRole("button", { name: /Chọn nhiều/ }).click(); await page.getByRole("button", { name: /Phòng demo\/thử/ }).click(); await shot("4-select");
const nsel = await page.locator(".cr-chk:checked").count(); ok(nsel >= 3, `lọc demo chọn ${nsel} phòng`);
await page.getByTestId("bulk-delete").click(); await page.getByTestId("confirm-delete").waitFor(); await shot("5-bulk-dialog");
// loại bớt phòng thật: chỉ xoá nếu mọi phòng chọn là phòng QA của lần chạy này
await page.keyboard.press("Escape");
// chọn đúng 3 phòng QA bằng checkbox
await page.getByRole("button", { name: /Bỏ chọn/ }).click();
for (const n of names) await page.getByLabel(`Chọn phòng ${n}`).check();
await page.getByTestId("bulk-delete").click(); await page.getByTestId("confirm-delete").click(); await page.waitForTimeout(2500); await shot("6-bulk-done");
ok(await page.getByText(names[1]).count() === 0, "bulk: phòng QA đã vào thùng rác");
// 4) xoá vĩnh viễn (master)
await page.getByTestId("trash-open").click(); await page.getByRole("dialog").waitFor();
for (const n of names) {
  const li = page.getByRole("dialog").locator("li", { hasText: n });
  await li.getByRole("button", { name: /Xoá vĩnh viễn/ }).click(); await li.getByRole("button", { name: /Chắc chắn xoá/ }).click(); await page.waitForTimeout(1500);
}
ok(await page.getByRole("dialog").getByText(`QA demo xoa ${tag}`).count() === 0, "purge xong, thùng rác sạch phòng QA"); await shot("7-purged");
await page.keyboard.press("Escape");
// 5) không tràn ngang ở mobile
await page.setViewportSize({ width: 375, height: 800 }); await page.waitForTimeout(500);
await page.getByRole("button", { name: /Danh sách phòng/ }).first().click().catch(() => {});
await page.getByTestId("trash-open").click().catch(() => {}); await page.waitForTimeout(500); await shot("8-mobile");
ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1), "không tràn ngang 375px");
log("errors", JSON.stringify(errs)); ok(!errs.length, "không lỗi JS");
await browser.close(); process.exit(fails ? 1 : 0);
