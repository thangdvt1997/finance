// E2E với auth THẬT (chạy trong container tạm trên VPS qua qa/run.sh e2e.mjs).
// Cần tài khoản thử: docker exec -i tradingsys-auth python - create 99900001 < qa/auth_testacct.py  (xoá sau test).
// Biến môi trường: QA_USER (số login), QA_PASS (passcode ban đầu), BASE.
import { chromium } from "playwright";
import fs from "node:fs";

const BASE = process.env.BASE || "http://127.0.0.1:8581/c/";
const USER = process.env.QA_USER, PASS = process.env.QA_PASS;
const OUT = process.env.OUT || "out";
fs.mkdirSync(OUT, { recursive: true });
const NEWPW = `Qa-E2e-${Math.random().toString(36).slice(2, 8)}-${Date.now() % 1000}x!`;
const results = [];
const ok = (name, cond, extra = "") => { results.push({ name, pass: !!cond, extra }); console.log(`${cond ? "PASS" : "FAIL"}  ${name}${extra ? "  " + extra : ""}`); };

const browser = await chromium.launch();
const ctx = await browser.newContext({ viewport: { width: 390, height: 844 }, deviceScaleFactor: 2, isMobile: true, hasTouch: true, locale: "vi-VN" });
const page = await ctx.newPage();
const errs = [];
page.on("pageerror", (e) => errs.push(e.message));
const shot = (n) => page.screenshot({ path: `${OUT}/e2e-${n}.jpg`, type: "jpeg", quality: 72, fullPage: true });
const api = (p, init) => page.evaluate(async ([p, init]) => { const r = await fetch(p, init); let t = ""; try { t = await r.text(); } catch {} return { s: r.status, t: t.slice(0, 300) }; }, [p, init]);

await page.goto(BASE);
await page.waitForSelector("form");
// 1) đăng nhập sai
await page.fill('input[autocomplete="username"]', USER);
await page.fill('input[autocomplete="current-password"]', "sai-mat-khau-123");
await page.click('button[type="submit"]');
await page.waitForSelector('[role="alert"]');
ok("Đăng nhập sai -> thông báo chung", /không đúng/i.test(await page.textContent('[role="alert"]')), (await page.textContent('[role="alert"]')).trim().slice(0, 60));
await shot("1-login-sai");
// 2) passcode ban đầu -> bắt buộc đổi mật khẩu
await page.fill('input[autocomplete="current-password"]', PASS);
await page.click('button[type="submit"]');
await page.waitForSelector("text=Cần đổi mật khẩu cổng", { timeout: 10000 }).catch(() => {});
ok("Passcode ban đầu -> màn hình bắt buộc đổi mật khẩu", await page.isVisible("text=Cần đổi mật khẩu cổng"));
await shot("2-bat-buoc-doi-mk");
// chặn: API dữ liệu khi chưa đổi mật khẩu
const early = await api("/c/api/v1/accounts");
ok("Chưa đổi mật khẩu -> API dữ liệu bị từ chối", early.s === 401 || early.s === 403, `status ${early.s}`);
const pw = await page.$$('input[type="password"]');
await pw[0].fill(PASS); await pw[1].fill(NEWPW); await pw[2].fill(NEWPW);
await page.click('button:has-text("Đổi mật khẩu")');
await page.waitForSelector("main#main-content", { timeout: 15000 });
ok("Đổi mật khẩu thành công -> vào ứng dụng", true);
await page.waitForTimeout(1500);
await shot("3-tong-quan-tai-khoan-moi");
// 3) phạm vi dữ liệu
const mine = `mt5:${USER}`;
const acc = await api("/c/api/v1/accounts");
let list = []; try { list = JSON.parse(acc.t.length >= 300 ? "[]" : acc.t); } catch {}
ok("GET /accounts chỉ trả tài khoản của tôi", acc.s === 200 && list.every((x) => x.account_id === mine), `status ${acc.s} ${acc.t.slice(0, 80)}`);
const me = await api("/c/auth/me");
ok("GET /auth/me trả đúng tài khoản", me.s === 200 && me.t.includes(mine), me.t.slice(0, 100));
for (const other of ["mt5:12345678", "mt4:7654321", "demo-1"]) {
  for (const p of [`/c/api/v1/risk/accounts/${encodeURIComponent(other)}`, `/c/api/v1/journal/${encodeURIComponent(other)}/summary`, `/c/api/v1/equity-history?account_id=${encodeURIComponent(other)}`]) {
    const r = await api(p);
    const leaked = r.s === 200 && r.t.length > 5 && r.t !== "[]" && !/"items":\s*\[\]/.test(r.t);
    ok(`IDOR chặn: ${p.replace("/c/api/v1", "")}`, !leaked, `status ${r.s}`);
  }
}
for (const p of ["/c/api/v1/system", "/c/api/v1/paper/accounts", "/c/api/v1/reports", "/c/api/v1/data-sources", "/c/auth/admin/accounts", "/c/auth/verify"]) {
  const r = await api(p); ok(`Endpoint quản trị/hệ thống không lộ: ${p}`, r.s === 404 || r.s === 405 || r.s === 403, `status ${r.s}`);
}
const post = await api("/c/api/v1/accounts", { method: "POST", headers: { "Content-Type": "application/json" }, body: "{}" });
ok("Không có route ghi/đặt lệnh (POST /accounts)", post.s === 403 || post.s === 405, `status ${post.s}`);
// 4) các trang tải được với tài khoản thật (không lỗi JS)
for (const p of ["tong-quan", "vi-the", "rui-ro", "nhat-ky", "thi-truong", "tin-lich", "tin-hieu", "canh-bao", "ho-so"]) {
  await page.evaluate((x) => { location.hash = `#/${x}`; }, p);
  await page.waitForTimeout(1800);
  await page.waitForSelector('[role="status"][aria-label="Đang tải"]', { state: "detached", timeout: 12000 }).catch(() => {});
  await shot(`4-${p}`);
  ok(`Trang ${p} hiển thị`, await page.isVisible("main h1"), (await page.textContent("main h1").catch(() => "")) || "");
}
ok("Không có lỗi JS trang", errs.length === 0, errs.slice(0, 2).join(" | "));
// 5) phiên + đăng xuất
await page.evaluate(() => { location.hash = "#/ho-so"; }); await page.waitForTimeout(1500);
ok("Hồ sơ có danh sách phiên", await page.isVisible("text=thiết bị này").catch(() => false) || await page.isVisible("text=Máy chủ chưa hỗ trợ").catch(() => false));
await page.click('button:has-text("Đăng xuất thiết bị này")');
await page.waitForSelector("form", { timeout: 10000 });
ok("Đăng xuất -> về màn hình đăng nhập", true);
const after = await api("/c/api/v1/accounts");
ok("Sau đăng xuất API trả 401", after.s === 401, `status ${after.s}`);
// 6) đăng nhập bằng mật khẩu mới
await page.fill('input[autocomplete="username"]', USER);
await page.fill('input[autocomplete="current-password"]', PASS);
await page.click('button[type="submit"]'); await page.waitForSelector('[role="alert"]');
ok("Passcode cũ không còn dùng được", true);
await page.fill('input[autocomplete="current-password"]', NEWPW);
await page.click('button[type="submit"]');
await page.waitForSelector("main#main-content", { timeout: 15000 });
ok("Đăng nhập bằng mật khẩu mới", true);
// 7) không cookie -> 401
const ctx2 = await browser.newContext(); const p2 = await ctx2.newPage(); await p2.goto(BASE);
const nocookie = await p2.evaluate(async () => (await fetch("/c/api/v1/accounts")).status);
ok("Không có phiên -> /api trả 401", nocookie === 401, `status ${nocookie}`);
await ctx2.close();
// 8) logout-all
await page.evaluate(() => { location.hash = "#/ho-so"; }); await page.waitForTimeout(1200);
await page.click('button:has-text("Đăng xuất mọi thiết bị")'); await page.waitForSelector("form", { timeout: 10000 });
ok("Đăng xuất mọi thiết bị", true);
await browser.close();
fs.writeFileSync(`${OUT}/e2e-report.json`, JSON.stringify(results, null, 1));
const fail = results.filter((r) => !r.pass);
console.log(`\nTổng: ${results.length}, đạt: ${results.length - fail.length}, lỗi: ${fail.length}`);
process.exit(fail.length ? 1 : 0);
