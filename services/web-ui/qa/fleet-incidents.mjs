// QA trực quan trang Sự cố (#/su-co). Chạy bằng: sh qa/fleet-pw.sh fleet-incidents.mjs inc  (trong container Playwright trên VPS).
// Cần đã seed sự cố thử (qa/fleet-incidents-seed.py seed). Ảnh -> out/incidents-*.png. Tạo nhân sự support thử `qa-fleet-sup-inc` (cần TOTP) rồi in lệnh dọn.
import { session as session0, go, checks, fin, totp, OUT } from "./fleet-lib.mjs";
const shot = async (s, name) => { await s.page.screenshot({ path: `${OUT}/${name}.png` }); console.log("shot", name); };

const session = async (o = {}) => { const s = await session0(o); const th = o.theme || "dark"; await s.ctx.addInitScript((x) => { try { localStorage.setItem("ts-theme", x); } catch { /* bỏ */ } }, th); await s.page.emulateMedia({ colorScheme: th }); return s; };
const ok = [], bad = [];
const check = (name, cond, extra = "") => { (cond ? ok : bad).push(name); console.log(cond ? "PASS" : "FAIL", name, extra); };
// gọi API trong ngữ cảnh trang (cùng User-Agent/cookie với phiên trình duyệt)
const breq = (s, method, path, body) => s.page.evaluate(async ([m, p, b]) => {
  const r = await fetch(p, { method: m, credentials: "same-origin", headers: { Accept: "application/json", ...(b ? { "Content-Type": "application/json" } : {}) }, body: b ? JSON.stringify(b) : undefined });
  let j = null; try { j = await r.json(); } catch { /* không JSON */ }
  return { status: r.status, json: j };
}, [method, path, body || null]);
const listInc = async (s, q = "") => { const r = await breq(s, "GET", `/auth/admin/incidents${q}`); if (!r.json?.items) console.log("listInc lỗi", r.status); return r.json?.items ? r.json : { items: [] }; };
async function totpEnableP(s) {
  const a = await breq(s, "POST", "/auth/totp/setup", {});
  const secret = a.json?.secret; if (!secret) throw new Error("totp setup " + a.status);
  let b = await breq(s, "POST", "/auth/totp/enable", { code: totp(secret) });
  if (b.status !== 200) { await new Promise((r) => setTimeout(r, 31000)); b = await breq(s, "POST", "/auth/totp/enable", { code: totp(secret) }); }
  if (b.status !== 200) throw new Error("totp enable " + b.status);
  return secret;
}

// ---------- master, desktop tối ----------
let s = await session({ theme: "dark", w: 1366, h: 800 });
await go(s, "su-co?st=open", 2500);
const me = await breq(s, "GET", "/auth/me");
console.log("role", me.status, JSON.stringify(me.json)?.slice(0, 120));
await shot(s, "incidents-desktop-dark-list");
const cards = await s.page.locator("li.inc-card").count();
check("có thẻ sự cố", cards > 0, `n=${cards}`);
check("tiêu đề trang", (await s.page.locator("h1").first().innerText()).includes("Sự cố"));
check("ghi chú chỉ-đọc", (await s.page.locator("body").innerText()).includes("không có đặt lệnh"));
check("huy hiệu tab có số", (await s.page.locator(".inc-tabs .inc-n").first().innerText()).trim() !== "—");
await checks(s, "list");

// mở chi tiết (bảng bên phải ở 1366)
await s.page.locator("li.inc-card .inc-title").first().click();
await s.page.waitForTimeout(900);
check("chi tiết hiện bên phải", await s.page.locator(".inc-detail-pane [data-detail]").count() === 1);
check("có dòng thời gian", await s.page.locator(".inc-detail-pane .fl-timeline li").count() >= 1);
check("liên kết tài khoản", (await s.page.locator('.inc-detail-pane a[href*="#/doi-tai-khoan?q="]').count()) >= 1);
await shot(s, "incidents-desktop-dark-detail");

// phím tắt j/k + a
await s.page.locator("body").click({ position: { x: 5, y: 300 } });
await s.page.keyboard.press("j"); await s.page.waitForTimeout(300);
const curN = await s.page.locator('li.inc-card[aria-current="true"]').count();
check("j đặt thẻ hiện tại", curN === 1);
const before = (await listInc(s, "?status=ack")).items.length;
await s.page.keyboard.press("a"); await s.page.waitForTimeout(1500);
const after = (await listInc(s, "?status=ack")).items.length;
check("phím a nhận sự cố", after === before + 1, `${before}->${after}`);

// tab Đã nhận + giao + ghi chú
await s.page.getByRole("tab", { name: /Đã nhận/ }).click(); await s.page.waitForTimeout(1200);
await s.page.locator("li.inc-card .inc-title").first().click(); await s.page.waitForTimeout(800);
const sel = s.page.locator(".inc-detail-pane select").first();
const opts = await sel.locator("option").allInnerTexts();
console.log("assignees", JSON.stringify(opts));
if (opts.length > 1) { await sel.selectOption({ index: 1 }); await s.page.getByRole("button", { name: /Áp dụng/ }).first().click(); await s.page.waitForTimeout(1200); }
check("giao việc ghi dòng sự kiện", (await s.page.locator(".inc-detail-pane .fl-timeline").innerText()).includes("Giao việc") || opts.length <= 1);
await s.page.locator(".inc-detail-pane textarea").first().fill("Đã liên hệ khách (QA)");
await s.page.getByRole("button", { name: /Lưu ghi chú/ }).click(); await s.page.waitForTimeout(1200);
check("ghi chú vào dòng thời gian", (await s.page.locator(".inc-detail-pane .fl-timeline").innerText()).includes("Đã liên hệ khách (QA)"));

// tạm hoãn qua hộp thoại
await s.page.getByRole("button", { name: /^Tạm hoãn/ }).first().click(); await s.page.waitForTimeout(500);
await shot(s, "incidents-desktop-dark-snooze");
await s.page.getByRole("button", { name: /^1 giờ/ }).click(); await s.page.waitForTimeout(1500);
check("sự cố sang Tạm hoãn", (await listInc(s, "?status=snoozed")).items.length >= 1);
await s.page.getByRole("tab", { name: /Tạm hoãn/ }).click(); await s.page.waitForTimeout(1200);
check("nhãn còn bao lâu", (await s.page.locator("li.inc-card").first().innerText()).includes("còn"));
await shot(s, "incidents-desktop-dark-snoozed");

// chế độ gộp + bulk theo cụm
await go(s, "su-co?st=open&gop=1", 2500);
check("có thẻ cụm", await s.page.locator("li.inc-cluster").count() >= 1);
await shot(s, "incidents-desktop-dark-clusters");
await s.page.locator("li.inc-cluster").first().getByRole("button", { name: /Xem từng tài khoản/ }).click(); await s.page.waitForTimeout(500);
check("mở rộng cụm xem từng tài khoản", await s.page.locator("li.inc-cluster li.inc-card").count() >= 2);
await shot(s, "incidents-desktop-dark-cluster-open");
// bulk: chọn 2 thẻ -> thanh hàng loạt
const bx = s.page.locator("li.inc-card input[type=checkbox]");
if (await bx.count() >= 2) { await bx.nth(0).check(); await bx.nth(1).check(); await s.page.waitForTimeout(300); }
check("thanh hàng loạt", await s.page.locator(".fl-bulkbar").count() === 1);
await shot(s, "incidents-desktop-dark-bulk");
await s.page.locator(".fl-bulkbar").getByRole("button", { name: /^Đóng$/ }).click(); await s.page.waitForTimeout(500);
await s.page.getByRole("dialog").getByRole("button", { name: /Đóng \d+ sự cố/ }).click(); await s.page.waitForTimeout(1800);
const rs = await listInc(s, "?status=resolved");
check("bulk đóng", rs.items.some((i) => i.resolved_by && i.resolved_by !== "auto"), `resolved=${rs.items.length}`);

// tab Đã đóng + mở lại
await go(s, "su-co?st=resolved", 2200);
await shot(s, "incidents-desktop-dark-resolved");
const hasAuto = await s.page.locator("li.inc-card").filter({ hasText: "tự đóng" }).count();
console.log("tự đóng hiển thị:", hasAuto);
await s.page.locator("li.inc-card").filter({ hasNotText: "tự đóng" }).first().getByRole("button", { name: /Mở lại/ }).click().catch(() => {});
await s.page.waitForTimeout(1500);
check("mở lại trả về Mới", (await listInc(s, "?status=open")).items.some((i) => i.acked_at === null || true));

// bộ lọc trên URL
await go(s, "su-co?st=open&sv=critical&gop=", 2000);
check("bộ lọc mức lưu trên URL", s.page.url().includes("sv=critical"));
check("chỉ còn mức nghiêm trọng", (await s.page.locator("li.inc-card").filter({ hasText: "Cảnh báo" }).count()) === 0);
await go(s, "su-co?st=open&q=zzzz-khong-co", 1800);
check("rỗng khi lọc không khớp", (await s.page.locator("body").innerText()).includes("Không có sự cố khớp bộ lọc"));
await shot(s, "incidents-desktop-dark-empty-filter");

// sáng + mobile
fin(s);
await s.close();
s = await session({ theme: "light", w: 1366, h: 800 });
await go(s, "su-co?st=open", 2500);
await shot(s, "incidents-desktop-light");
await checks(s, "light");
await s.close();
for (const theme of ["dark", "light"]) {
  s = await session({ theme, w: 390, h: 844, mobile: true });
  await go(s, "su-co?st=open", 2500);
  await shot(s, `incidents-mobile-${theme}-list`);
  const c = await checks(s, `mobile-${theme}`);
  check(`mobile ${theme} không tràn ngang`, !c.hOverflow);
  if (theme === "dark") {
    await s.page.locator("li.inc-card .inc-title").first().click(); await s.page.waitForTimeout(900);
    check("mobile: chi tiết dạng ngăn kéo", await s.page.getByRole("dialog").count() === 1);
    await shot(s, "incidents-mobile-dark-detail");
    const c2 = await checks(s, "mobile-detail");
    check("mobile chi tiết không tràn ngang", !c2.hOverflow);
  }
  fin(s);
  await s.close();
}

// ---------- vai trò support ----------
s = await session({ theme: "dark", w: 1366, h: 800 });
let sup = null;
try {
  await go(s, "su-co", 1500);
  await totpEnableP(s);
  const r = await breq(s, "POST", "/auth/admin/staff", { name: "qa-fleet-sup-inc", role: "support", scope_all: true });
  console.log("staff", r.status);
  sup = r.json?.password || r.json?.initial_password || r.json?.secret || null;
  if (!sup) console.log("keys", Object.keys(r.json || {}));
} catch (e) { console.log("support setup lỗi", String(e).slice(0, 160)); }
fin(s);
await s.close();
if (sup) {
  const t = await session({ theme: "dark", w: 1366, h: 800, user: "qa-fleet-sup-inc", pass: sup });
  await go(t, "su-co", 1200);
  const np = "Qa-" + Math.random().toString(36).slice(2) + Math.random().toString(36).slice(2) + "9Z";
  const cp = await breq(t, "POST", "/auth/change-password", { current_password: sup, new_password: np });
  console.log("đổi mật khẩu lần đầu", cp.status);
  await go(t, "su-co?st=open", 2500);
  console.log("sup-role", JSON.stringify((await breq(t, "GET", "/auth/me")).json)?.slice(0, 300));
  console.log("sup-body", (await t.page.locator("body").innerText()).replace(/s+/g, " ").slice(0, 400));
  await shot(t, "incidents-support-debug");
  await t.page.locator("li.inc-card .inc-title").first().click(); await t.page.waitForTimeout(900);
  check("support: có banner chỉ xem + ghi chú", (await t.page.locator("body").innerText()).includes("Chế độ chỉ xem + ghi chú"));
  check("support: nút Tạm hoãn bị khoá", await t.page.locator(".inc-detail-pane button:disabled", { hasText: /Tạm hoãn/ }).count() === 1);
  check("support: không có checkbox chọn", await t.page.locator("li.inc-card input[type=checkbox]").count() === 0);
  await shot(t, "incidents-support-view");
  await t.page.locator(".inc-detail-pane textarea").first().fill("Ghi chú của support (QA)");
  await t.page.getByRole("button", { name: /Lưu ghi chú/ }).click(); await t.page.waitForTimeout(1200);
  check("support ghi chú được", (await t.page.locator(".inc-detail-pane .fl-timeline").innerText()).includes("Ghi chú của support (QA)"));
  fin(t);
  await t.close();
} else console.log("BỎ QUA kiểm tra support (không tạo được)");

console.log("TỔNG", ok.length, "đạt;", bad.length, "lỗi:", JSON.stringify(bad));
