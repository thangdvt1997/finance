// QA trang Vai trò & nhân sự / Phiên & thiết bị / Nhật ký kiểm toán + kiểm thử VAI TRÒ (support/analyst/auditor).
// Chạy: sh /root/trading-system/services/web-ui/qa/fleet-pw.sh fleet-staff.mjs staff   (ảnh ở /tmp/qa-fleet-staff/out)
import crypto from "node:crypto";
import { session, totpEnable, go, checks, fin, BASE, OUT } from "./fleet-lib.mjs";
const shot = async (s, name) => { await s.page.screenshot({ path: `${OUT}/${name}.png` }); console.log("shot", name); };

const NAMES = { sup: "qa-fleet-sup-st", ana: "qa-fleet-ana-st", aud: "qa-fleet-aud-st" };
const newPw = () => "Qa!" + crypto.randomBytes(12).toString("base64url") + "9z";
// fleet-lib.req (APIRequestContext) không gửi cookie Secure qua http://127.0.0.1 -> dùng fetch TRONG trình duyệt (cookie + Origin tự gửi).
async function withReq(s) {
  await s.page.goto(`${BASE}/robots.txt`, { waitUntil: "domcontentloaded" }).catch(() => {});
  s.req = (method, path, data) => s.page.evaluate(async ([m, p, d]) => {
    const x = await fetch(p, { method: m, credentials: "same-origin", headers: { "Content-Type": "application/json", Accept: "application/json" }, body: d === undefined || m === "GET" ? undefined : JSON.stringify(d) });
    let j = null; try { j = await x.json(); } catch { /* không JSON */ }
    return { status: x.status, json: j };
  }, [method, path, data]);
  return s;
}
const log = (...a) => console.log(...a);
const ok = (name, cond, extra = "") => log(cond ? "PASS" : "FAIL", name, extra);

const m = await withReq(await session({}));
const secret = await totpEnable(m);
log("master totp bat");

// ---- tạo nhân sự thử qua API ----
const gr = await m.req("GET", "/auth/admin/groups");
const g0 = gr.json?.items?.[0]?.id;
log("groups", gr.status, (gr.json?.items || []).length);
const made = {};
for (const [k, role] of [["sup", "support"], ["ana", "analyst"], ["aud", "auditor"]]) {
  const body = { name: NAMES[k], role, display_name: `QA ${role}`, ...(role === "auditor" ? {} : g0 ? { group_ids: [g0] } : { scope_all: true }) };
  const r = await m.req("POST", "/auth/admin/staff", body);
  ok(`tao ${role}`, r.status === 201 && r.json?.password, String(r.status));
  made[k] = { pw: r.json?.password, id: r.json?.user?.user_id };
}

// ---- đăng nhập lần đầu + đổi mật khẩu bắt buộc, rồi đăng nhập lại ----
const staff = {};
for (const k of Object.keys(NAMES)) {
  const s1 = await withReq(await session({ user: NAMES[k], pass: made[k].pw }));
  const pre = await s1.req("GET", "/auth/admin/roles");
  ok(`${k} chua doi mat khau -> bi chan`, [401, 403].includes(pre.status), String(pre.status));
  const np = newPw();
  const ch = await s1.req("POST", "/auth/change-password", { current_password: made[k].pw, new_password: np });
  ok(`${k} doi mat khau`, ch.status === 200, String(ch.status));
  await s1.close();
  staff[k] = await withReq(await session({ user: NAMES[k], pass: np }));
}

// ---- quét điều hướng + truy cập thẳng trang không có quyền ----
const HASHES = ["vai-tro", "kiem-toan", "phien-thiet-bi", "doi-tai-khoan", "su-co", "luat-tuan-thu", "bao-cao-khach", "khach-hang", "terminal", "tong-quan"];
const EXPECT = {
  sup: { has: ["Phiên & thiết bị"], not: ["Vai trò & nhân sự", "Nhật ký kiểm toán"] },
  ana: { has: ["Phiên & thiết bị"], not: ["Vai trò & nhân sự", "Nhật ký kiểm toán"] },
  aud: { has: ["Nhật ký kiểm toán", "Phiên & thiết bị"], not: ["Vai trò & nhân sự"] },
};
for (const k of Object.keys(staff)) {
  const s = staff[k];
  await go(s, "tong-quan", 2500);
  const nav = await s.page.evaluate(() => [...document.querySelectorAll("nav a, aside a")].map((a) => `${a.textContent.trim().replace(/\s+/g, " ")}|${a.getAttribute("href")}`).filter((x) => x.includes("#/")));
  const labels = nav.map((x) => x.split("|")[0]);
  log(`NAV ${k}:`, JSON.stringify([...new Set(nav)]));
  for (const h of EXPECT[k].has) ok(`${k} nav co ${h}`, labels.some((l) => l.includes(h)));
  for (const h of EXPECT[k].not) ok(`${k} nav khong co ${h}`, !labels.some((l) => l.includes(h)));
  await shot(s, `roles-nav-${k}`);
  for (const h of HASHES) {
    const e0 = s.errors.length;
    await go(s, h, 1500);
    const info = await s.page.evaluate(() => ({ hash: location.hash, h1: document.querySelector("h1")?.textContent?.trim() || "", crashed: /something went wrong|Unexpected Application Error/i.test(document.body.innerText) }));
    log(`  ${k} #/${h} ->`, JSON.stringify(info), s.errors.length > e0 ? "ERR:" + s.errors.slice(e0).join(" | ") : "");
    ok(`${k} #/${h} khong crash`, !info.crashed && s.errors.length === e0);
  }
  // admin API: vai trò phụ chỉ được đúng quyền
  const probe = {};
  for (const p of ["roles", "staff", "audit", "fleet", "incidents", "compliance", "groups"]) probe[p] = (await s.req("GET", `/auth/admin/${p}`)).status;
  log(`API ${k}`, JSON.stringify(probe));
  ok(`${k} khong doc duoc roles/staff`, probe.roles === 403 && probe.staff !== 200);
  ok(`${k} audit dung quyen`, k === "aud" ? probe.audit === 200 : probe.audit === 403);
  const me = await s.req("GET", "/auth/me");
  log(`ME ${k}`, JSON.stringify({ role: me.json?.role, perms: me.json?.perms, totp: me.json?.totp_enabled }));
}

// ---- trang Phiên & thiết bị bằng từng vai trò ----
for (const k of Object.keys(staff)) {
  const s = staff[k];
  await go(s, "phien-thiet-bi", 2200);
  const t = await s.page.evaluate(() => ({ h1: document.querySelector("h1")?.textContent, sess: document.querySelectorAll("ul[aria-label='Phiên đăng nhập của tôi'] li").length, cur: /Phiên hiện tại/.test(document.body.innerText), allp: /Phiên của mọi người/.test(document.body.innerText) }));
  log(`SESS ${k}`, JSON.stringify(t));
  ok(`${k} thay phien cua minh, khong thay phien nguoi khac`, t.sess >= 1 && t.cur && !t.allp);
  await shot(s, `roles-sessions-${k}`);
}
await go(staff.aud, "kiem-toan", 2500);
const au = await staff.aud.page.evaluate(() => ({ h1: document.querySelector("h1")?.textContent, rows: document.querySelectorAll("table[aria-label='Nhật ký kiểm toán'] tbody tr").length }));
log("AUDIT aud", JSON.stringify(au));
ok("auditor xem duoc nhat ky", au.rows > 0);
await shot(staff.aud, "roles-audit-auditor");
await go(staff.aud, "vai-tro", 1800);
await shot(staff.aud, "roles-direct-denied-auditor");

// ---- ảnh master: 3 trang x (sáng/tối) x (desktop/mobile) ----
const st = await m.ctx.storageState();
async function view(theme, w, h, mobile) {
  const ctx = await m.browser.newContext({ storageState: st, viewport: { width: w, height: h }, baseURL: BASE, ...(mobile ? { isMobile: true, hasTouch: true } : {}) });
  await ctx.addInitScript((t) => { try { localStorage.setItem("ts-ux", JSON.stringify({ onboarded: 99, theme: t })); } catch { /* bỏ */ } }, theme);
  const page = await ctx.newPage();
  page.setDefaultTimeout(9000);
  const v = { page, errors: [], bad: [], ctx };
  page.on("pageerror", (e) => v.errors.push("pageerror: " + String(e.message).slice(0, 240)));
  page.on("console", (x) => { if (x.type() === "error") v.errors.push("console: " + x.text().slice(0, 240)); });
  return v;
}
const PAGES = [["roles", "vai-tro"], ["sessions", "phien-thiet-bi"], ["audit", "kiem-toan"]];
for (const [theme, w, h, mobile, tag] of [["dark", 1366, 800, false, "d-dark"], ["light", 1366, 800, false, "d-light"], ["dark", 390, 844, true, "m-dark"], ["light", 390, 844, true, "m-light"]]) {
  const v = await view(theme, w, h, mobile);
  for (const [nm, hs] of PAGES) {
    await go(v, hs, 2600);
    await checks(v, `${nm} ${tag}`);
    await shot(v, `${nm}-${tag}`);
  }
  log("ERR", tag, JSON.stringify(v.errors));
  await v.ctx.close();
}

// ---- tương tác UI (desktop, tối) ----
const v = await view("dark", 1366, 900, false);
await go(v, "vai-tro", 2500);
const cnt = await v.page.evaluate(() => [...document.querySelectorAll("table[aria-label='Nhân sự phụ'] tbody tr")].map((r) => r.innerText.replace(/\s+/g, " ").slice(0, 120)));
log("STAFF rows", JSON.stringify(cnt));
ok("danh sach nhan su co 3 nguoi qa", cnt.filter((x) => /qa-fleet-(sup|ana|aud)-st/.test(x)).length === 3);
const mx = await v.page.evaluate(() => document.querySelector("table[aria-label='Ma trận quyền']")?.innerText.replace(/\s+/g, " ").slice(0, 400));
log("MATRIX", mx);
await v.page.getByRole("button", { name: "Tạo nhân sự" }).first().click();
await v.page.waitForTimeout(500);
await v.page.fill("#st-name", "qa-fleet-ui-st");
await v.page.selectOption("#st-role", "analyst");
await shot(v, "roles-create-form");
await v.page.getByRole("button", { name: "Tạo nhân sự" }).last().click();
await v.page.waitForTimeout(1500);
const sec = await v.page.evaluate(() => ({ warn: /MỘT lần/.test(document.body.innerText), pw: !!document.querySelector(".fl-secret-v"), done: document.querySelector("[role=dialog] button.\\!bg-accent")?.disabled }));
log("SECRET", JSON.stringify(sec));
ok("hien mat khau mot lan", sec.warn && sec.pw);
await shot(v, "roles-secret-once");
await v.page.getByLabel("Tôi đã lưu các giá trị này ở nơi an toàn").check();
await v.page.getByRole("button", { name: "Xong" }).click();
await v.page.waitForTimeout(1200);
const after = await v.page.evaluate(() => document.querySelector("table[aria-label='Nhân sự phụ']")?.innerText.includes("qa-fleet-ui-st"));
ok("nhan su moi xuat hien trong danh sach", after);
// sửa + đình chỉ (xác nhận 2 bước) trên nhân sự UI
await v.page.getByRole("button", { name: "Sửa qa-fleet-ui-st" }).click();
await v.page.waitForTimeout(600);
await shot(v, "roles-edit-form");
await v.page.getByRole("button", { name: "Huỷ" }).click();
await v.page.getByRole("button", { name: "Đình chỉ qa-fleet-ui-st" }).click();
await v.page.waitForTimeout(500);
await shot(v, "roles-confirm-suspend");
await v.page.getByRole("button", { name: "Đình chỉ", exact: true }).last().click();
await v.page.waitForTimeout(1500);
const susp = await v.page.evaluate(() => [...document.querySelectorAll("table[aria-label='Nhân sự phụ'] tbody tr")].find((r) => r.innerText.includes("qa-fleet-ui-st"))?.innerText.replace(/\s+/g, " "));
log("UI suspended row", susp);
ok("dinh chi hien trang thai", /Đình chỉ/.test(susp || ""));
await go(v, "phien-thiet-bi", 2200);
await v.page.getByRole("button", { name: "Đăng xuất mọi nơi" }).click();
await v.page.waitForTimeout(500);
await shot(v, "sessions-confirm-logoutall");
await v.page.getByRole("button", { name: "Huỷ" }).click();
await go(v, "kiem-toan", 2200);
await v.page.getByRole("button", { name: /Kiểm tra toàn vẹn/ }).click();
await v.page.waitForTimeout(2500);
const ver = await v.page.evaluate(() => /Chuỗi băm nguyên vẹn|bất thường/.test(document.body.innerText) ? document.body.innerText.match(/Chuỗi băm nguyên vẹn|bất thường[^.]*/)?.[0] : "none");
log("VERIFY", ver);
ok("kiem tra toan ven chay", /nguyên vẹn/.test(ver));
const tx = await v.page.evaluate(() => [...document.querySelectorAll("table[aria-label='Nhật ký kiểm toán'] tbody tr")].slice(0, 6).map((r) => r.innerText.replace(/\s+/g, " ").slice(0, 110)));
log("AUDIT rows", JSON.stringify(tx));
await v.page.getByRole("button", { name: /Chi tiết sự kiện/ }).first().click();
await v.page.waitForTimeout(500);
await shot(v, "audit-detail");
const pre = await v.page.evaluate(() => document.querySelector("[role=dialog] pre")?.innerText.slice(0, 300));
log("DETAIL", pre);
await v.page.keyboard.press("Escape");
log("ERR ui", JSON.stringify(v.errors));
// tên nguồn
await checks(v, "audit-final");

for (const k of Object.keys(staff)) { fin(staff[k]); await staff[k].close(); }
fin(m);
await m.close();
