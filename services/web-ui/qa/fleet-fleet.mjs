// QA trực quan trang Đội tài khoản (lead). Chạy: sh /root/trading-system/services/web-ui/qa/fleet-pw.sh fleet-fleet.mjs lead
// Luồng: (1) chưa bật TOTP -> banner + trình hướng dẫn (quét QR bằng cách đọc chuỗi bí mật) -> bật TOTP; (2) nhập CSV 3 dòng -> thẻ onboarding (+ giả lập in);
// (3) danh sách, KPI, lọc, saved views, chọn nhiều + hàng loạt 2 bước (gắn tag), nhóm, hồ sơ khách (4 tab), xem-như-khách (banner đếm ngược + kết thúc); sáng/tối, desktop/mobile.
import { session, shot, go, checks, fin, totp, setTheme, OUT } from "./fleet-lib.mjs";
import fs from "node:fs";

const RUN = Math.floor(Math.random() * 90000);
const L = [97000000 + RUN, 97100000 + RUN, 97200000 + RUN];
const results = [];
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const step = async (name, fn) => { try { await fn(); results.push([name, "ok"]); } catch (e) { const m = String(e.message).split(String.fromCharCode(10)).slice(0, 3).join(" | ").slice(0, 300); results.push([name, "FAIL " + m]); console.log("FAIL", name, m); await shot(s, "fail-" + name).catch(() => {}); } };

const s = await session({ theme: "dark", w: 1366, h: 820 });
const { page } = s;
let secret = null;
const created = [];

await step("totp-banner", async () => {
  await go(s, "doi-tai-khoan", 2500);
  await page.waitForSelector(".fl-banner:has-text('xác thực hai bước')");
  await shot(s, "01-fleet-totp-banner-dark");
});
await step("totp-wizard", async () => {
  await page.getByRole("button", { name: "Bật TOTP" }).first().click();
  await page.getByRole("button", { name: /Tạo mã QR/ }).click();
  await page.waitForSelector(".fl-secret-v");
  await page.waitForSelector("svg[role='img'] , .rounded-md.bg-white svg", { timeout: 6000 });
  await page.waitForTimeout(500);
  await shot(s, "02-totp-qr-dark");
  secret = ((await page.locator(".fl-secret-v").first().innerText()) || "").replace(/\s+/g, "");
  await page.fill("#totp-code", totp(secret));
  await page.getByRole("button", { name: /Xác nhận & bật TOTP/ }).click();
  await page.waitForSelector("text=Đã bật xác thực hai bước", { timeout: 8000 });
  await shot(s, "03-totp-done-dark");
  await page.getByRole("button", { name: "Đóng" }).last().click();
});

// ---- dữ liệu thử qua API (nhóm) ----
let g1 = null;
await step("api-group", async () => {
  const r = await s.req("POST", "/auth/admin/groups", { name: "qa-fleet-vip", color: "#3b82f6" });
  g1 = r.json?.id;
  if (!g1) throw new Error("tạo nhóm lỗi " + r.status + JSON.stringify(r.json));
  await s.req("POST", "/auth/admin/groups", { name: "qa-fleet-scalp", color: "#f59e0b" });
});

await step("import-flow", async () => {
  await go(s, "doi-tai-khoan", 2000);
  await page.reload({ waitUntil: "load" }); await page.waitForTimeout(1800);
  await page.getByRole("button", { name: /Nhập CSV/ }).click();
  await shot(s, "04-import-step1-dark");
  const csv = ["platform,login,server,label,group,tags,notes", `mt5,${L[0]},QA-Server,qa-fleet-A,qa-fleet-vip,vip;qa,thử nghiệm`, `mt4,${L[1]},QA-Server,qa-fleet-B,qa-fleet-scalp,qa,`, `mt5,abc,QA-Server,dòng lỗi,,,`].join("\n");
  await page.fill("#imp-csv", csv);
  await page.getByRole("button", { name: "Xem trước" }).click();
  await page.waitForSelector("text=Bước 2/3", { timeout: 8000 });
  await shot(s, "05-import-preview-dark");
  await page.getByRole("button", { name: /Tạo \d+ tài khoản hợp lệ/ }).click();
  await page.waitForSelector("text=Bước 3/3", { timeout: 20000 });
  await page.waitForTimeout(600);
  await shot(s, "06-import-cards-dark");
  const ids = await page.locator(".fl-obcard h3").allInnerTexts();
  console.log("cards", ids.length);
  // giả lập in A4
  await page.evaluate(() => document.querySelector("[role=dialog]")?.setAttribute("data-x", "1"));
  await page.evaluate(() => { window.print = () => {}; });
  await page.getByRole("button", { name: /In \/ Lưu PDF/ }).click();
  await page.waitForTimeout(400);
  await page.emulateMedia({ media: "print" });
  await page.waitForTimeout(300);
  await page.screenshot({ path: `${OUT}/07-print-a4.png`, fullPage: false });
  await page.emulateMedia({ media: "screen" });
  await page.keyboard.press("Escape");
  await page.locator("input[type=checkbox]").last().check().catch(() => {});
  await page.getByRole("button", { name: "Đóng" }).last().click();
});

await step("list-dark", async () => {
  await go(s, "doi-tai-khoan", 2500);
  await shot(s, "10-fleet-list-dark");
  await checks(s, "fleet-dark");
});
await step("kpi-filter", async () => {
  await page.getByRole("button", { name: /Chờ|Tài khoản/ }).first().click().catch(() => {});
  await page.selectOption("select[aria-label='Lọc theo nhóm']", { index: 1 });
  await page.waitForTimeout(900);
  await shot(s, "11-fleet-filter-group-dark");
  await page.getByRole("button", { name: "Xoá hết" }).click();
});
await step("saved-view", async () => {
  await page.selectOption("select[aria-label='Lọc theo trạng thái tài khoản']", "pending");
  await page.waitForTimeout(700);
  await page.getByRole("button", { name: /Bộ lọc đã lưu/ }).click();
  await page.getByRole("menuitem", { name: /Lưu bộ lọc hiện tại/ }).click();
  await page.fill("#sv-name", "qa-fleet chờ duyệt");
  await page.getByRole("button", { name: "Lưu" }).last().click();
  await page.waitForTimeout(800);
  await page.getByRole("button", { name: /Bộ lọc đã lưu/ }).click();
  await shot(s, "12-saved-views-dark");
  await page.keyboard.press("Escape");
  await page.getByRole("button", { name: "Xoá hết" }).click();
});
await step("bulk", async () => {
  const boxes = page.locator("tbody .fl-chk");
  const n = Math.min(await boxes.count(), 3);
  for (let i = 0; i < n; i++) await boxes.nth(i).check();
  await shot(s, "13-bulk-bar-dark");
  await page.getByRole("button", { name: /Thao tác hàng loạt/ }).click();
  await page.getByRole("radio", { name: "Gắn tag" }).click();
  await page.fill("#bk-tag", "qa-bulk");
  await shot(s, "14-bulk-step1-dark");
  await page.getByRole("button", { name: /Chuẩn bị/ }).click();
  await page.waitForSelector("#bk-phrase", { timeout: 8000 });
  await shot(s, "15-bulk-step2-dark");
  const phrase = (await page.locator("label[for=bk-phrase] b").innerText()).trim();
  await page.fill("#bk-phrase", phrase);
  await page.getByRole("button", { name: /Thực hiện/ }).click();
  await page.waitForSelector("text=Thành công", { timeout: 10000 });
  await shot(s, "16-bulk-result-dark");
  await page.getByRole("button", { name: "Đóng" }).last().click();
});
await step("groups-manager", async () => {
  await page.getByRole("button", { name: /Quản lý nhóm/ }).click();
  await page.waitForSelector("text=Quản lý nhóm");
  await page.waitForTimeout(800);
  await shot(s, "17-groups-dark");
  await page.getByRole("tab", { name: /Chính sách/ }).click();
  await page.waitForTimeout(700);
  await shot(s, "18-group-policy-dark");
  await page.keyboard.press("Escape");
});
await step("profile", async () => {
  await page.locator("tbody tr").first().click();
  await page.waitForSelector("[role=tablist][aria-label='Mục hồ sơ']");
  await page.waitForTimeout(1200);
  await shot(s, "20-profile-overview-dark");
  for (const [t, f] of [["Rủi ro & luật", "21-profile-rules"], ["Ghi chú CRM", "22-profile-notes"], ["Kiểm toán", "23-profile-audit"]]) {
    await page.getByRole("tab", { name: t }).click(); await page.waitForTimeout(700); await shot(s, `${f}-dark`);
  }
  await page.getByRole("tab", { name: "Ghi chú CRM" }).click();
  await page.fill("#pd-note", "qa-fleet: đã gọi khách, hẹn cập nhật EA");
  await page.getByRole("button", { name: /Lưu ghi chú/ }).click();
  await page.waitForTimeout(900);
  await shot(s, "22b-profile-notes-added-dark");
  await page.getByRole("tab", { name: "Tổng quan" }).click();
});
await step("view-as", async () => {
  await page.keyboard.press("Escape");
  const act = await s.req("POST", `/auth/admin/accounts/mt5:${L[0]}/activate`, {});
  console.log("activate", act.status);
  await go(s, "doi-tai-khoan", 800); await page.reload({ waitUntil: "load" }); await page.waitForTimeout(2200);
  await page.locator("tbody tr", { hasText: "qa-fleet-A" }).first().click();
  await page.waitForSelector("[role=tablist][aria-label='Mục hồ sơ']");
  await page.getByRole("button", { name: /Xem như khách/ }).click();
  await shot(s, "24-viewas-dialog-dark");
  await page.fill("#va-reason", "qa-fleet kiểm tra giao diện xem như khách");
  await page.getByRole("button", { name: "Bắt đầu xem" }).click();
  await page.waitForSelector(".fl-va", { timeout: 8000 });
  await page.waitForTimeout(1500);
  await shot(s, "25-viewas-banner-dark");
  await go(s, "doi-tai-khoan", 1500);
  const locked = await page.getByRole("button", { name: /Nhập CSV/ }).isDisabled();
  if (!locked) throw new Error("nút ghi chưa bị khoá khi xem như khách");
  await shot(s, "26-viewas-locked-fleet-dark");
  await page.getByRole("button", { name: "Kết thúc" }).click();
  await page.waitForSelector(".fl-va", { state: "detached", timeout: 8000 });
  await page.keyboard.press("Escape");
});

// ---- sáng + di động ----
await step("light-desktop", async () => {
  await setTheme(s, "light"); await page.reload({ waitUntil: "load" }); await page.waitForTimeout(2200);
  await shot(s, "30-fleet-list-light");
  await page.locator("tbody tr").first().click(); await page.waitForTimeout(1200);
  await shot(s, "31-profile-light");
  await page.keyboard.press("Escape");
});
await step("mobile", async () => {
  await setTheme(s, "light");
  await page.setViewportSize({ width: 390, height: 800 });
  await page.waitForTimeout(800);
  await shot(s, "40-fleet-mobile-light");
  await checks(s, "fleet-mobile");
  await setTheme(s, "dark"); await page.reload({ waitUntil: "load" }); await page.waitForTimeout(2000);
  await shot(s, "41-fleet-mobile-dark");
  await page.locator(".fl-card").first().locator("button").first().click().catch(() => {});
  await page.waitForTimeout(1200);
  await shot(s, "42-profile-mobile-dark");
});

// ---- dọn dẹp ----
await step("cleanup", async () => {
  const r = await s.req("GET", "/auth/admin/fleet?q=qa-fleet&limit=50");
  for (const a of r.json?.items || []) { const d = await s.req("DELETE", `/auth/admin/accounts/${encodeURIComponent(a.account_id)}`); created.push(`${a.account_id}:${d.status}`); await sleep(3300); }
  const gs = await s.req("GET", "/auth/admin/groups");
  for (const g of gs.json?.items || []) if (g.name.startsWith("qa-fleet")) { await s.req("DELETE", `/auth/admin/groups/${g.id}`); await sleep(3300); }
  const vs = await s.req("GET", "/auth/admin/views");
  for (const v of vs.json?.items || []) if (v.name.startsWith("qa-fleet")) { await s.req("DELETE", `/auth/admin/views/${v.id}`); await sleep(3300); }
});
console.log("created-deleted", JSON.stringify(created));
fin(s);
console.log("RESULTS\n" + results.map((r) => r.join(" : ")).join("\n"));
fs.writeFileSync(`${OUT}/results.json`, JSON.stringify(results));
await s.close();
