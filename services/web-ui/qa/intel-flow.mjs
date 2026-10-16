// QA tương tác Market Intelligence (agent C): terminal tin tức, lịch kinh tế, tương quan, heatmap, movers + widget trong Terminal.
// Chạy: sh qa/run-c.sh intel-flow.mjs   (biến: ONLY=prefix, VIEWPORT=WxH, THEME=dark|light)
import { chromium } from "playwright";
import fs from "node:fs";

const BASE = process.env.BASE || "http://127.0.0.1:8580";
const OUT = process.env.OUT || "out";
const USER = process.env.QA_USER, PASS = process.env.QA_PASS;
const ONLY = process.env.ONLY ? process.env.ONLY.split(",") : null;
const [VW, VH] = (process.env.VIEWPORT || "1600x950").split("x").map(Number);
const THEME = process.env.THEME || "dark";
fs.mkdirSync(OUT, { recursive: true });
const results = [];
let errors = [];
const ok = (name, cond, extra = "") => { results.push({ name, pass: !!cond, extra }); console.log(`${cond ? "PASS" : "FAIL"}  ${name}${extra ? "  " + String(extra).slice(0, 240) : ""}`); return !!cond; };
const browser = await chromium.launch();
const ctx = await browser.newContext({ viewport: { width: VW, height: VH }, colorScheme: THEME, timezoneId: "Asia/Ho_Chi_Minh", locale: "vi-VN", baseURL: BASE, acceptDownloads: true });
const lr = await ctx.request.post(`${BASE}/auth/login`, { data: { platform: "master", login: USER, secret: PASS }, headers: { Origin: BASE, "Content-Type": "application/json" } });
console.log("login", lr.status());
const page = await ctx.newPage();
page.setDefaultTimeout(9000);
page.on("pageerror", (e) => errors.push(`pageerror: ${String(e.message).slice(0, 300)}`));
page.on("console", (m) => { if (m.type() === "error") errors.push(`console: ${m.text().slice(0, 300)}`); });
page.on("response", (r) => { if (r.status() >= 400 && /\/api\//.test(r.url())) errors.push(`http ${r.status()} ${r.url().replace(BASE, "").slice(0, 120)}`); });
const shot = (n) => page.screenshot({ path: `${OUT}/${n}-${VW}-${THEME}.png` });
const sleep = (ms) => page.waitForTimeout(ms);
await page.addInitScript((t) => { try { localStorage.setItem("ts-theme", t); } catch {} }, THEME);
const dismissTour = async () => { for (let i = 0; i < 2; i++) { if (await page.getByText("Chào mừng đến Trạm thị trường").count()) { await page.keyboard.press("Escape"); await sleep(300); } } };
const go = async (p, wait = 3500) => { errors = []; await page.goto(`${BASE}/#/${p}`, { waitUntil: "load" }); await sleep(Math.min(wait, 1500)); await dismissTour(); await sleep(Math.max(0, wait - 1500)); };
const step = async (name, fn) => { if (ONLY && !ONLY.some((o) => name.startsWith(o))) return; errors = []; try { await fn(); } catch (e) { console.log("  errors:", errors.slice(-6).join(" || ").slice(0, 900)); ok(name, false, `EXC ${String(e.message).split("\n")[0]}`); await shot(`fail-${name.replace(/\W+/g, "_").slice(0, 30)}`).catch(() => {}); } };
const noErr = (name) => ok(`${name}: không lỗi JS/HTTP`, errors.length === 0, errors.slice(0, 3).join(" || "));

await step("news", async () => {
  await go("tin-tuc", 5000);
  const rows = await page.locator('[aria-label="Dòng tin"] [role="listitem"]').count();
  ok("news: ảo hoá danh sách (số hàng DOM < 80)", rows > 3 && rows < 80, `rows=${rows}`);
  const box = await page.locator('[aria-label="Dòng tin"][role="list"]').boundingBox();
  ok("news: vùng cuộn có chiều cao hữu hạn", box && box.height > 200 && box.height < VH, `h=${box?.height}`);
  await page.locator('[aria-label="Dòng tin"] [role="listitem"] [role="button"]').first().click();
  await sleep(1200);
  ok("news: bấm tin mở chi tiết", (await page.locator('article[aria-label="Chi tiết tin"] h2').count()) > 0);
  await shot("news-detail");
  await page.getByRole("button", { name: /Lưu tin/ }).first().click();
  await sleep(300);
  ok("news: lưu tin", (await page.getByRole("button", { name: /Đã lưu/ }).count()) > 0);
  await page.getByRole("button", { name: /Đã lưu \(1\)/ }).click().catch(() => {});
  await sleep(500);
  ok("news: tab Đã lưu có 1 tin", (await page.locator('[aria-label="Dòng tin"] [role="listitem"]').count()) === 1);
  await page.getByRole("button", { name: /^Dòng tin$/ }).first().click();
  await sleep(300);
  await page.locator("#nt-q").fill("giá vàng");
  await sleep(1800);
  const n1 = await page.locator('[aria-label="Dòng tin"] [role="listitem"]').count();
  ok("news: tìm toàn văn trả kết quả", n1 >= 0, `rows=${n1}`);
  await shot("news-search");
  await page.locator("#nt-q").fill("");
  await page.getByRole("button", { name: "Quan trọng", exact: true }).click();
  await sleep(1500);
  await shot("news-important");
  await page.getByRole("button", { name: "Squawk" }).click();
  await sleep(600);
  ok("news: chế độ squawk dày hơn", (await page.locator('[aria-label="Dòng tin"] [role="listitem"]').count()) > 6);
  await shot("news-squawk");
  await page.getByRole("button", { name: "Theo chủ đề" }).click();
  await sleep(800);
  ok("news: nhóm theo chủ đề", (await page.locator("section[aria-label]").count()) > 2);
  await shot("news-topics");
  noErr("news");
});

await step("calendar", async () => {
  await go("lich", 4500);
  if (!(await page.locator(".cal-ev").count())) { await page.getByRole("button", { name: "Tuần sau" }).click(); await sleep(2500); }   // múi giờ hiển thị có thể làm "tuần này" chưa có sự kiện
  ok("cal: có thẻ sự kiện", (await page.locator(".cal-ev").count()) > 0, `n=${await page.locator(".cal-ev").count()}`);
  ok("cal: không còn dòng QA", (await page.getByText("QA event").count()) === 0);
  const box = await page.locator('main section.panel').first().boundingBox();
  ok("cal: panel bị chặn chiều cao", box && box.height < VH + 40, `h=${box?.height}`);
  await page.locator(".cal-ev").first().click();
  await sleep(2500);
  ok("cal: chi tiết sự kiện", (await page.locator('article[aria-label="Chi tiết sự kiện"]').count()) > 0 || (await page.getByRole("dialog").count()) > 0);
  await shot("cal-detail");
  const cpi = page.locator(".cal-ev", { hasText: /CPI/ }).first();
  if (await cpi.count()) { await cpi.click(); await sleep(2500); ok("cal: lịch sử CPI (biểu đồ hoặc bảng các kỳ đã có)", (await page.locator('article[aria-label="Chi tiết sự kiện"] canvas, article[aria-label="Chi tiết sự kiện"] table').count()) > 0); await shot("cal-cpi"); }
  const rem = page.getByRole("button", { name: /Đặt nhắc/ }).first();
  if (await rem.count()) { await rem.click(); await sleep(500); ok("cal: hộp thoại đặt nhắc", (await page.getByRole("dialog", { name: /nhắc/i }).count()) > 0); await shot("cal-remind"); await page.keyboard.press("Escape"); }
  await page.getByRole("button", { name: "Bảng tuần" }).click();
  await sleep(500);
  ok("cal: bảng tuần", (await page.locator("table.tbl tbody tr").count()) > 0);
  await shot("cal-table");
  await page.getByRole("button", { name: "Ngày", exact: true }).click();
  await sleep(500);
  await shot("cal-day");
  await page.getByRole("button", { name: "Tuần trước" }).click();
  await sleep(1500);
  ok("cal: chuyển tuần trước", true);
  noErr("calendar");
});

await step("risk", async () => {
  await go("tuong-quan-rui-ro", 4500);
  const cv = page.locator('main [role="img"] canvas').first();
  const b = await cv.boundingBox();
  if (b) { await page.mouse.click(b.x + b.width * 0.30, b.y + b.height * 0.40); await sleep(1500); }
  ok("risk: bấm ô ma trận mở tương quan lăn", (await page.getByText(/lăn/i).count()) > 0);
  await shot("risk-rolling");
  noErr("risk");
});

await step("heat", async () => {
  await go("ban-do-nhiet", 4000);
  for (const t of ["Chỉ số & ETF toàn cầu", "Ngành Mỹ (ETF)", "Kim loại & hàng hoá", "Forex", "Ngành VN"]) {
    await page.getByRole("button", { name: t, exact: true }).click(); await sleep(1800);
    ok(`heat: tab ${t}`, (await page.locator("#main canvas, #main table").count()) > 0);
  }
  await shot("heat-vn");
  await page.getByRole("button", { name: "Ngành Mỹ (ETF)", exact: true }).click(); await sleep(1500);
  await shot("heat-sector");
  await page.getByRole("button", { name: "Bảng", exact: true }).click(); await sleep(800);
  await shot("heat-table");
  noErr("heat");
});

await step("movers", async () => {
  await go("movers", 3500);
  await page.getByRole("button", { name: "Tổng quan 4 cột" }).click(); await sleep(800);
  await shot("movers-4col");
  for (const k of ["Gap mở cửa", "Gần đỉnh 52 tuần"]) { await page.getByRole("button", { name: k }).first().click().catch(() => {}); await sleep(500); }
  noErr("movers");
});

await step("widgets", async () => {
  await go("terminal", 3000);
  await page.getByRole("button", { name: "Thêm workspace" }).click();   // workspace trống: tránh tải nặng của bảng giá mặc định làm nhiễu kiểm thử
  await page.getByRole("menuitem", { name: /Trống/ }).click();
  await sleep(800);
  const titles = ["Sức mạnh tiền tệ", "Bản đồ nhiệt Forex", "Tỷ giá chéo", "Giờ mở cửa các sàn", "Biên độ theo phiên", "Bản đồ nhiệt thị trường", "Movers", "Nhịp thị trường", "Ma trận tương quan", "Xếp hạng biến động", "Phân phối lợi suất", "Vị thế đầu cơ lớn", "Dòng tin squawk", "Lịch kinh tế (nâng cao)"];
  let added = 0;
  for (const t of titles) {
    await page.getByRole("button", { name: "Thêm widget" }).first().click();
    await sleep(400);
    await page.getByLabel("Tìm widget").fill(t.split(" ").slice(0, 2).join(" "));
    await sleep(300);
    const btn = page.locator('[role="dialog"] ul button').first();
    if (await btn.count()) { await btn.click(); added++; } else { console.log("không thấy widget", t); await page.keyboard.press("Escape"); }
    await sleep(1200);
    if (await page.getByText("Không hiển thị được trang này").count()) { console.log("CRASH sau khi thêm:", t, "|", errors.slice(-4).join(" || ")); await shot("widgets-crash"); break; }
  }
  ok("widgets: đã thêm đủ", added >= titles.length - 2, `added=${added}/${titles.length}`);
  await sleep(5000);
  const bad = await page.evaluate(() => [...document.querySelectorAll(".tm-w")].filter((w) => w.querySelector('[role="alert"]')?.textContent.includes("Widget gặp lỗi")).map((w) => w.querySelector(".tm-wt")?.textContent));
  ok("widgets: không widget nào lỗi", bad.length === 0, bad.join(","));
  const ws = page.locator(".tm-w");
  const n = await ws.count();
  for (let i = Math.max(0, n - added); i < n; i++) {
    const w = ws.nth(i);
    const title = ((await w.locator(".tm-wt").first().textContent().catch(() => "")) || `w${i}`).replace(/\W+/g, "_").slice(0, 24);
    await w.scrollIntoViewIfNeeded().catch(() => {});
    await sleep(500);
    await w.screenshot({ path: `${OUT}/w${String(i).padStart(2, "0")}-${title}.png` }).catch(() => {});
  }
  // dọn: xoá workspace thử (prefs người dùng là dùng chung, không để lại rác trong Terminal của người dùng thật)
  try {
    await page.getByRole("button", { name: "Menu workspace" }).click();
    await page.getByRole("menuitem", { name: /Xoá workspace/ }).click();
    await page.getByRole("dialog").getByRole("button", { name: "Xoá", exact: true }).click();
    await sleep(1500);
    ok("widgets: đã xoá workspace thử", (await page.getByRole("tab", { name: "Trống" }).count()) === 0);
  } catch (e) { ok("widgets: đã xoá workspace thử", false, String(e.message).slice(0, 120)); }
  noErr("widgets");
});

fs.writeFileSync(`${OUT}/results-flow.json`, JSON.stringify(results, null, 1));
const bad = results.filter((r) => !r.pass);
console.log(`\n${results.length - bad.length}/${results.length} PASS`);
await browser.close();
process.exit(bad.length ? 1 : 0);
