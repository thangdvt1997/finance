// QA trang "Báo cáo khách": chưa khả dụng / rỗng thật / có dữ liệu mô phỏng (page.route, CHỈ trong QA) / hộp thoại / lịch; desktop 1366 + mobile 390; sáng + tối.
import { session, go, shot, checks, fin } from "./fleet-lib.mjs";

const ACC = "mt5:99000001";
const J = (o, s = 200) => ({ status: s, contentType: "application/json", body: JSON.stringify(o) });
const items = [
  { account_id: ACC, kind: "weekly", period: "2026-10-11", generated_at: "2026-10-12T01:10:00Z", bytes: 42113, pdf_bytes: 88120, has_pdf: true, status: "ok", sections_ok: ["risk", "equity"], sections_fail: [], released: true, released_at: "2026-10-12T02:00:00Z", read_only: true },
  { account_id: ACC, kind: "daily", period: "2026-10-11", generated_at: "2026-10-12T01:05:00Z", bytes: 21003, pdf_bytes: 0, has_pdf: false, status: "degraded", sections_ok: ["risk"], sections_fail: ["equity", "journal"], released: false, read_only: true },
  { account_id: ACC, kind: "monthly", period: "2026-09-30", generated_at: "2026-10-01T01:00:00Z", bytes: 61000, pdf_bytes: 120000, has_pdf: true, status: "ok", sections_ok: [], sections_fail: [], released: false, read_only: true },
];
const scheds = [
  { schedule_id: "aaaaaaaa11112222", scope: { type: "group", ref: "g1" }, kind: "weekly", hour: 7, enabled: true, auto_release: false },
  { schedule_id: "bbbbbbbb11112222", scope: { type: "all", ref: null }, kind: "monthly", hour: 8, enabled: false, auto_release: true },
];

async function run(theme, w, h, mobile, tag) {
  const s = await session({ theme, w, h, mobile });
  const p = s.page;
  const chk = async (l) => { const r = await checks(s, `${tag}-${l}`); if (r.banned || r.hOverflow) { console.log("!!! FAIL", tag, l, JSON.stringify(r)); if (r.hOverflow) console.log("offenders", JSON.stringify(await p.evaluate(() => [...document.querySelectorAll("body *")].filter((e) => e.getBoundingClientRect().right > innerWidth + 2 && !e.closest(".fl-tablewrap")).slice(0, 8).map((e) => e.tagName + "." + String(e.className).slice(0, 60) + " r=" + Math.round(e.getBoundingClientRect().right))))); } };
  // 1) Chưa khả dụng: nginx trả trang SPA (không phải JSON)
  await p.route("**/api/v1/account-report*", (r) => r.fulfill({ status: 200, contentType: "text/html", body: "<html></html>" }));
  await go(s, `bao-cao-khach/${ACC}`); await shot(s, `${tag}-unavailable`); await chk("unavail");
  await p.getByRole("button", { name: /Lịch tự động/ }).click(); await p.waitForTimeout(800); await shot(s, `${tag}-sched-unavail`);
  await p.unroute("**/api/v1/account-report*");
  const reload = async () => { await p.reload({ waitUntil: "load" }); await p.waitForTimeout(1800); };
  // 2) Rỗng thật (route có thật, tài khoản demo chưa có báo cáo hoặc có sẵn)
  await reload(); await shot(s, `${tag}-real`); await chk("real");
  // 3) Dữ liệu mô phỏng
  let released = null;
  await p.route("**/api/v1/account-reports?*", (r) => r.fulfill(J({ read_only: true, account_id: ACC, items })));
  await p.route("**/api/v1/account-reports/release", (r) => { released = JSON.parse(r.request().postData() || "{}"); return r.fulfill(J({ ...items[1], released: released.released })); });
  await p.route("**/api/v1/account-reports/generate", (r) => r.fulfill(J({ ...items[1], skipped: undefined })));
  await p.route("**/api/v1/account-report-schedules", (r) => (r.request().method() === "GET" ? r.fulfill(J({ schedules: scheds })) : r.fulfill(J({ schedules: JSON.parse(r.request().postData()).schedules }))));
  await p.route("**/api/v1/user/csrf", (r) => r.fulfill(J({ token: "t", ttl_s: 600 })));
  await reload(); await shot(s, `${tag}-data`); await chk("data");
  await p.getByRole("button", { name: "Phát hành" }).first().click(); await p.waitForTimeout(500); await shot(s, `${tag}-release-confirm`);
  await p.getByRole("dialog").getByRole("button", { name: "Phát hành" }).click(); await p.waitForTimeout(900);
  console.log("release body", JSON.stringify(released));
  await p.getByRole("button", { name: /Tạo báo cáo/ }).first().click(); await p.waitForTimeout(500); await shot(s, `${tag}-generate`); await chk("gen");
  await p.getByRole("dialog").getByRole("button", { name: /^Tạo báo cáo$/ }).click(); await p.waitForTimeout(1500); await shot(s, `${tag}-generate-done`);
  await p.getByRole("dialog").getByRole("button", { name: "Xong" }).click().catch(() => {});
  await p.getByRole("button", { name: /Lịch tự động/ }).click(); await p.waitForTimeout(900); await shot(s, `${tag}-sched`); await chk("sched");
  await p.getByRole("button", { name: /Thêm lịch/ }).first().click(); await p.waitForTimeout(400); await shot(s, `${tag}-sched-form`);
  fin(s); await s.close();
}
const J4 = [["dark", 1366, 800, false, "d-dark"], ["light", 1366, 800, false, "d-light"], ["dark", 390, 844, true, "m-dark"], ["light", 390, 844, true, "m-light"]];
for (const a of J4) { if (process.env.ONLY && !a[4].startsWith(process.env.ONLY)) continue; try { await run(...a); } catch (e) { console.log("RUN FAIL", a[4], String(e.message).slice(0, 300)); } }
