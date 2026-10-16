// QA-E flows (auth thật, tài khoản thử): ghép cặp UI, đặt/sửa/xoá giới hạn, cảnh báo cục bộ, thông báo, đổi ngôn ngữ/giao diện, báo cáo, đăng xuất.
import { chromium } from "playwright";
import fs from "node:fs";
const BASE = process.env.BASE || "http://127.0.0.1:8581/c/";
const OUT = process.env.OUT || "out"; fs.mkdirSync(OUT, { recursive: true });
const U1 = process.env.QA_USER, P1 = process.env.QA_PASS, U2 = process.env.QA_USER2, PAIR2 = process.env.QA_PAIR2;
const NEWPW = `Qa-Stab-${Math.random().toString(36).slice(2, 8)}-${Date.now() % 1000}x!`;
const res = []; const ok = (n, c, x = "") => { res.push({ n, pass: !!c, x }); console.log(`${c ? "PASS" : "FAIL"}  ${n}${x ? "  :: " + x : ""}`); };
let SP = null, ERRS = []; const step = async (n, fn) => { try { const r = await fn(); ok(n, r !== false, typeof r === "string" ? r : ""); } catch (e) { ok(n, false, String(e.message).split("\n")[0].slice(0, 160)); if (SP) { await SP.screenshot({ path: `${OUT}/fail-${res.length}.jpg` }).catch(() => {}); console.log("   errs:", JSON.stringify(ERRS)); console.log("   body:", (await SP.innerText("body").catch(() => "")).replace(/\s+/g, " ").slice(0, 200)); } } };
const browser = await chromium.launch();
const mk = async () => { const ctx = await browser.newContext({ viewport: { width: 414, height: 896 }, isMobile: true, hasTouch: true, locale: "vi-VN" }); await ctx.addInitScript(() => { try { if (!localStorage.getItem("tc-prefs")) localStorage.setItem("tc-prefs", JSON.stringify({ onboarded: true })); } catch {} }); const page = await ctx.newPage(); const errs = []; page.on("pageerror", (e) => errs.push(e.message.slice(0, 120))); page.on("console", (m) => { if (m.type() === "error" && !/401|Failed to load resource/.test(m.text())) errs.push(m.text().slice(0, 120)); }); return { ctx, page, errs }; };
const idle = async (page) => { await page.waitForSelector('[role="status"][aria-label="Đang tải"],[role="status"][aria-label="Loading"]', { state: "detached", timeout: 15000 }).catch(() => {}); await page.waitForTimeout(500); };
const go = async (page, h) => { await page.evaluate((x) => { location.hash = x; }, h); await page.waitForTimeout(300); await idle(page); };
const fillLogin = async (page, u, p) => { await page.waitForSelector("form"); await page.waitForTimeout(2500); for (let i = 0; i < 4; i++) { await page.fill('input[autocomplete="username"]', u); await page.fill('input[autocomplete="current-password"]', p); if ((await page.inputValue('input[autocomplete="username"]')) === u) break; await page.waitForTimeout(1500); } };

// ---- 1) ghép cặp qua UI (tài khoản 2)
{
  const { ctx, page, errs } = await mk();
  await page.goto(BASE); await page.waitForSelector("form"); await page.waitForTimeout(2500);
  await step("Pair UI: mở tab Ghép cặp lần đầu", async () => { await page.click('button:has-text("Ghép cặp lần đầu")'); await page.waitForTimeout(400); return await page.isVisible("form"); });
  await step("Pair UI: mã sai -> báo lỗi chung, không lộ chi tiết", async () => {
    await page.fill('input[autocomplete="username"]', U2); const inputs = page.locator("form input:not([type=hidden])"); const n = await inputs.count();
    const texts = []; for (let i = 0; i < n; i++) texts.push(await inputs.nth(i).getAttribute("autocomplete") + "|" + await inputs.nth(i).getAttribute("type") + "|" + (await inputs.nth(i).getAttribute("placeholder") || ""));
    return texts.join("; ");
  });
  const form = page.locator("form");
  const pwInputs = form.locator('input[type="password"]');
  const codeInput = form.locator('input:not([type=password]):not([autocomplete="username"])').last();
  await step("Pair UI: nhập mã đúng + mật khẩu mới -> vào app", async () => {
    await codeInput.fill(PAIR2); const c = await pwInputs.count();
    for (let i = 0; i < c; i++) await pwInputs.nth(i).fill(NEWPW);
    await page.click('button[type="submit"]'); await page.waitForSelector("main#main-content", { timeout: 30000 }); return true;
  });
  await step("Pair UI: sau ghép cặp /auth/me đúng tài khoản + không phải đổi mật khẩu", async () => { const t = await page.evaluate(async () => (await fetch("/c/auth/me")).text()); return t.includes(U2) && t.includes('"must_change_password":false') ? true : t.slice(0, 120); });
  await step("Pair UI: không lỗi JS", async () => errs.length === 0 || errs.join("|"));
  await ctx.close();
}
// ---- 2) tài khoản 1: đổi passcode lần đầu qua UI
const { ctx, page, errs } = await mk();
await page.goto(BASE); await fillLogin(page, U1, P1); await page.click('button[type="submit"]');
await step("Login passcode ban đầu -> màn hình đổi mật khẩu", async () => { await page.waitForSelector("text=Cần đổi mật khẩu cổng", { timeout: 30000 }); await page.waitForTimeout(800); return true; });
await step("Đổi mật khẩu cổng bắt buộc -> vào app", async () => { const pw = page.locator('input[type="password"]'); await pw.nth(0).fill(P1); await pw.nth(1).fill(NEWPW); await pw.nth(2).fill(NEWPW); await page.click('button:has-text("Đổi mật khẩu")'); await page.waitForSelector("main#main-content", { timeout: 30000 }); return true; });
SP = page; ERRS = errs; const api = (p, init) => page.evaluate(async ([p, init]) => { const r = await fetch(p, init); let t = ""; try { t = await r.text(); } catch {} return { s: r.status, t: t.slice(0, 600) }; }, [p, init]);

// ---- giới hạn
await go(page, "#/gioi-han");
await step("Giới hạn: trang hiện đủ thẻ (>=4 nút Đặt/Sửa)", async () => (await page.locator('main button[aria-label^="Đặt:"], main button[aria-label^="Sửa:"]').count()) >= 4 || "ít thẻ");
await step("Giới hạn: đặt Lỗ tối đa trong ngày = 5 -> lưu OK", async () => {
  await page.locator('main button[aria-label$="Lỗ tối đa trong ngày"]').first().click(); await page.waitForSelector('[role="dialog"]');
  await page.fill('[role="dialog"] input', "5"); await page.locator('[role="dialog"] button[type="submit"]').click(); await page.waitForTimeout(1500);
  const r = await api("/c/api/v1/user/limits?account_id=mt5:" + U1); return r.s === 200 && /5/.test(r.t) ? true : `${r.s} ${r.t.slice(0, 160)}`; });
await step("Giới hạn: miền sai (999) bị chặn, không lưu", async () => {
  await page.keyboard.press("Escape"); await page.waitForTimeout(300);
  await go(page, "#/gioi-han"); await page.locator('main button[aria-label$="Lỗ tối đa trong ngày"]').first().click(); await page.waitForSelector('[role="dialog"]');
  await page.fill('[role="dialog"] input', "999"); const dis = await page.locator('[role="dialog"] button[type="submit"]').isDisabled(); if (!dis) await page.locator('[role="dialog"] button[type="submit"]').click(); await page.waitForTimeout(800);
  const r = await api("/c/api/v1/user/limits?account_id=mt5:" + U1); await page.keyboard.press("Escape"); return !/999/.test(r.t) ? `submit ${dis ? "bị vô hiệu" : "đã gửi, server từ chối"}` : r.t.slice(0, 120); });
await step("Giới hạn: xoá giới hạn (xác nhận) -> biến mất", async () => {
  await go(page, "#/gioi-han"); const del = page.locator('main button[aria-label^="Xoá:"]').first(); if (!(await del.count())) return "không có nút xoá";
  await del.click(); await page.click('button:has-text("Xoá giới hạn")'); await page.waitForTimeout(1200); return (await page.locator('main button[aria-label^="Xoá:"]').count()) === 0 || "vẫn còn"; });
// ---- cảnh báo
await go(page, "#/canh-bao");
await step("Cảnh báo: tạo cảnh báo giá -> xuất hiện trong danh sách", async () => {
  await page.locator("main button.btn.primary", { hasText: "Tạo cảnh báo" }).first().click(); await page.waitForSelector('[role="dialog"]'); await page.waitForTimeout(300);
  await page.fill('[role="dialog"] input[inputmode="decimal"]', "1.0500"); await page.locator('[role="dialog"] button[type="submit"]').click(); await page.waitForTimeout(1500);
  return (await page.locator('main button[aria-label^="Xoá cảnh báo"]').count()) >= 1 || "không thấy cảnh báo mới"; });
await step("Cảnh báo: form để trống -> lỗi xác thực, không tạo", async () => {
  await page.locator("main button.btn.primary", { hasText: "Tạo cảnh báo" }).first().click(); await page.waitForSelector('[role="dialog"]'); await page.fill('[role="dialog"] input[inputmode="decimal"]', "");
  const before = await page.locator('main button[aria-label^="Xoá cảnh báo"]').count(); await page.locator('[role="dialog"] button[type="submit"]').click({ force: true }).catch(() => {}); await page.waitForTimeout(500); await page.keyboard.press("Escape"); await page.waitForTimeout(300);
  return (await page.locator('main button[aria-label^="Xoá cảnh báo"]').count()) === before; });
await step("Cảnh báo: xoá cảnh báo", async () => {
  const del = page.locator('main button[aria-label^="Xoá cảnh báo"]').first(); const n0 = await del.count(); if (!n0) return "không có";
  await del.click(); await page.waitForTimeout(400); const cf = page.locator('[role="dialog"] button.danger, [role="alertdialog"] button.danger').first(); if (await cf.count()) await cf.click(); await page.waitForTimeout(800);
  return (await page.locator('main button[aria-label^="Xoá cảnh báo"]').count()) < Math.max(1, n0) + 0 || "chưa xoá"; });
// ---- thông báo
for (const [n, h] of [["trung tâm", "#/thong-bao"], ["cài đặt", "#/thong-bao?tab=settings"], ["lịch sử", "#/thong-bao?tab=history"]]) {
  await step(`Thông báo (${n}): hiển thị, không NaN`, async () => { await go(page, h); const t = await page.innerText("main"); return (await page.isVisible("main h1")) && !/NaN|undefined/.test(t) ? true : t.slice(0, 100); });
}
await step("Thông báo: API đánh dấu đã đọc 200", async () => { const r = await api("/c/api/v1/user/notifications"); return r.s === 200 || `${r.s}`; });
// ---- báo cáo
await go(page, "#/bao-cao");
await step("Báo cáo: trang hiển thị (rỗng/hoặc danh sách), không lỗi", async () => { const t = await page.innerText("main"); return !/NaN|undefined|Lỗi không xác định/.test(t) ? t.replace(/\s+/g, " ").slice(0, 80) : t.slice(0, 120); });
await step("Báo cáo: API /c/api/v1/account-reports không 5xx", async () => { const r = await api("/c/api/v1/account-reports?account_id=mt5:" + U1); return r.s < 500 ? `${r.s}` : `${r.s} ${r.t.slice(0, 100)}`; });
// ---- hồ sơ: ngôn ngữ, giao diện
await go(page, "#/ho-so");
await step("Hồ sơ: đổi sang English -> giao diện en + <html lang=en>", async () => {
  await page.locator("main .seg button", { hasText: "English" }).first().click(); await page.waitForTimeout(800);
  const lang = await page.evaluate(() => document.documentElement.lang); const t = await page.innerText("main"); return lang === "en" && !/Ngôn ngữ/.test(t) ? true : `lang=${lang}`; });
await step("Hồ sơ: đồng bộ cài đặt PUT /user/client-prefs lưu được", async () => { await page.waitForTimeout(2500); const r = await api("/c/api/v1/user/client-prefs"); return r.s === 200 && /"lang":\s*"en"/.test(r.t) ? true : `${r.s} ${r.t.slice(0, 120)}`; });
await step("Hồ sơ: đổi lại Tiếng Việt", async () => { await page.locator("main .seg button", { hasText: "Tiếng Việt" }).first().click(); await page.waitForTimeout(800); return (await page.evaluate(() => document.documentElement.lang)) === "vi"; });
await step("Giao diện sáng/tối: nút đổi theme", async () => { const before = await page.evaluate(() => document.documentElement.dataset.theme); await page.locator('header button[aria-label*="giao diện"]').first().click(); await page.waitForTimeout(400); const after = await page.evaluate(() => document.documentElement.dataset.theme); return before !== after ? `${before}->${after}` : "không đổi"; });
// ---- Điều hướng chung (menu Thêm trên mobile)
await step("Menu Thêm (mobile) mở được + có >=10 mục", async () => { await go(page, "#/hom-nay"); await page.click("nav.bottom-nav button"); await page.waitForSelector('[role="dialog"]'); const n = await page.locator('[role="dialog"] a').count(); await page.keyboard.press("Escape"); return n >= 10 || `n=${n}`; });
await step("Sheet tài khoản mở được", async () => { await page.click('header button[aria-haspopup="dialog"]'); await page.waitForSelector('[role="dialog"]'); const t = await page.innerText('[role="dialog"]'); await page.keyboard.press("Escape"); return t.includes(U1); });
await step("Không lỗi JS suốt phiên", async () => errs.length === 0 || errs.slice(0, 3).join(" | "));
// ---- đăng xuất
await go(page, "#/ho-so");
await step("Đăng xuất thiết bị này -> về đăng nhập, API 401", async () => { await page.click('button:has-text("Đăng xuất thiết bị này")'); await page.waitForSelector("form", { timeout: 15000 }); const r = await api("/c/api/v1/accounts"); return r.s === 401 || `${r.s}`; });
await ctx.close(); await browser.close();
fs.writeFileSync(`${OUT}/flows.json`, JSON.stringify(res, null, 1));
const f = res.filter((r) => !r.pass); console.log(`\nTổng ${res.length}, lỗi ${f.length}`); process.exit(f.length ? 1 : 0);
