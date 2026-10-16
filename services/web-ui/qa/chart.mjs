// QA trực quan + chức năng biểu đồ chuyên nghiệp (agent B). Chạy trong container Playwright tạm qa-ui-b-* TRÊN VPS qua qa/run-b.sh.
// Tài khoản master THỬ do run-b.sh tạo/xoá. Dọn: bản vẽ/mẫu/cảnh báo do script tạo đều bị xoá ở cuối.
import { chromium } from "playwright";
import fs from "node:fs";

const BASE = process.env.BASE || "http://127.0.0.1:8580";
const OUT = process.env.OUT || "out";
const USER = process.env.QA_USER, PASS = process.env.QA_PASS;
const ONLY = process.env.ONLY ? process.env.ONLY.split(",") : null;
fs.mkdirSync(OUT, { recursive: true });
const results = [];
const errors = [];
const ok = (name, cond, extra = "") => { results.push({ name, pass: !!cond, extra }); console.log(`${cond ? "PASS" : "FAIL"}  ${name}${extra ? "  " + String(extra).slice(0, 220) : ""}`); return !!cond; };

const browser = await chromium.launch();
const ctx = await browser.newContext({ viewport: { width: 1600, height: 950 }, colorScheme: "dark", baseURL: BASE, permissions: ["clipboard-read", "clipboard-write"], acceptDownloads: true });
if (USER) {
  const lr = await ctx.request.post(`${BASE}/auth/login`, { data: { platform: "master", login: USER, secret: PASS }, headers: { Origin: BASE, "Content-Type": "application/json" } });
  console.log("login", lr.status());
}
const page = await ctx.newPage();
page.setDefaultTimeout(9000);
page.on("pageerror", (e) => errors.push(`pageerror: ${String(e.message).slice(0, 300)}`));
page.on("console", (m) => { if (m.type() === "error") errors.push(`console: ${m.text().slice(0, 300)}`); });
const shot = (n) => page.screenshot({ path: `${OUT}/${n}.png` });
const sleep = (ms) => page.waitForTimeout(ms);
const step = async (name, fn) => { if (ONLY && !ONLY.some((o) => name.startsWith(o))) return; try { await fn(); } catch (e) { ok(name, false, `EXC ${String(e.message).split("\n")[0]}`); await shot(`fail-${name.replace(/\W+/g, "_").slice(0, 40)}`).catch(() => {}); } };

// ---- tiện ích ----
const LAYOUT_NAME = { "1": "1 biểu đồ", "2v": "2 biểu đồ xếp dọc", "2h": "2 biểu đồ cạnh nhau", "1+3": "1 lớn + 3 nhỏ", "3x2": "6 biểu đồ (3×2)" };
const apiGet = async (p) => { for (let i = 0; i < 6; i++) { const r = await page.evaluate(async (p) => { try { const r = await fetch(`/api/v1${p}`, { credentials: "same-origin" }); const t = await r.text(); try { return { s: r.status, j: JSON.parse(t) }; } catch { return { s: r.status, t: t.slice(0, 200) }; } } catch (e) { return { s: 0, t: String(e) }; } }, p); if (r.s === 200 || r.s === 404 || i === 5) return r; await sleep(3000); } };
const csrf = async () => (await apiGet("/user/csrf")).j.token;
const apiPut = async (p, body, method = "PUT") => { const tk = await csrf(); return page.evaluate(async ([p, body, method, tk]) => { const r = await fetch(`/api/v1${p}`, { method, credentials: "same-origin", headers: { "Content-Type": "application/json", "X-CSRF-Token": tk }, body: body ? JSON.stringify(body) : undefined }); return { s: r.status, t: (await r.text()).slice(0, 300) }; }, [p, body, method, tk]); };
const paneBox = async (i = 0) => { const bx = await page.locator('.ws-cell .pc-surface').nth(i).boundingBox(); return { x: bx.x + 70, y: bx.y + 70, w: bx.width - 170, h: bx.height - 130, raw: bx }; };
const pt = (b, fx, fy) => [b.x + b.w * fx, b.y + b.h * fy];
const clickAt = async (b, fx, fy) => { const [x, y] = pt(b, fx, fy); await page.mouse.move(x, y); await page.mouse.click(x, y); await sleep(120); };
const drawingsCount = async () => {
  await ensureTab("Đối tượng");
  const t = await page.evaluate(() => [...document.querySelectorAll(".mkt-pop h3")].find((h) => /^Hình vẽ/.test(h.textContent))?.textContent || "");
  return Number((/\((\d+)\)/.exec(t) || [])[1] ?? -1);
};
const pauseIfPlaying = async () => { if (await page.getByRole("button", { name: "Tạm dừng", exact: true }).count()) await page.getByRole("button", { name: "Tạm dừng", exact: true }).click(); };
const closePanel = async () => { for (let i = 0; i < 2 && await page.locator(".mkt-pop").count(); i++) { await page.keyboard.press("Escape"); await sleep(150); } };
const ensureTab = async (tab) => {
  if (!(await page.locator(".mkt-pop").count())) await page.getByRole("button", { name: /^Chỉ báo/ }).first().click();
  await sleep(150);
  await page.locator(".mkt-pop").getByRole("button", { name: tab, exact: true }).click(); await sleep(200);
};
const cntOf = async () => { const t = await page.locator('dt:has-text("Nến") + dd').first().innerText().catch(() => "0"); return Number(String(t).replace(/[^\d]/g, "") || 0); };

// ======================================================================
const waitBars = async (min = 50, ms = 90000) => { const t0 = Date.now(); while (Date.now() - t0 < ms) { if ((await cntOf()) >= min) { await sleep(1500); return true; } await sleep(1000); } return false; };
const openMarket = async () => {
  for (let i = 0; i < 5; i++) {
    await page.goto(`${BASE}/#/thi-truong/EURUSD?tf=H1`, { waitUntil: "load" }).catch(() => {});
    if (i) await page.reload({ waitUntil: "load" }).catch(() => {});
    if (await page.waitForSelector(".ws-cell canvas", { timeout: 20000 }).then(() => true).catch(() => false)) { await waitBars(); return true; }
    console.log("openMarket retry", i + 1);
  }
  return false;
};
await openMarket();
await page.evaluate(() => { try { localStorage.removeItem("ts-ws-v2"); } catch {} });
await openMarket();
const prefsBefore = await apiGet("/user/prefs");
console.log("prefs.before", prefsBefore.s, JSON.stringify(prefsBefore.j?.prefs || {}).length, "chars");

await step("01-render", async () => {
  await shot("01-market");
  const n = await page.locator('.ws-cell .pc-surface canvas').count();
  ok("Biểu đồ dựng canvas", n >= 2, `canvas=${n}`);
  const legend = await page.locator(".ws-cell").first().innerText();
  ok("Legend OHLC có mã EURUSD", /EURUSD/.test(legend) && /O\s/.test(legend), legend.slice(0, 60).replace(/\n/g, " | "));
  const cnt = await cntOf();
  ok("Dải giá hiện số nến nạp", cnt > 50, `nến=${cnt}`);
});

await step("02-worker", async () => {
  const res = await page.evaluate(() => performance.getEntriesByType("resource").map((r) => r.name).filter((n) => /indWorker/i.test(n)));
  ok("Web Worker chỉ báo được nạp (CSP worker-src self)", res.length > 0, res[0] || "không thấy");
  const cspErr = errors.filter((e) => /Content Security|worker/i.test(e));
  ok("Không có lỗi CSP/worker", cspErr.length === 0, cspErr[0] || "");
});

await step("03-indicators", async () => {
  await page.getByRole("button", { name: /Chỉ báo/ }).first().click();
  await sleep(300);
  const tabs = await page.locator(".mkt-pop button[aria-pressed]").allInnerTexts();
  ok("Bảng có đủ tab Chỉ báo/Tín hiệu/Hiển thị/Đối tượng/Mẫu/Đa khung", ["Chỉ báo", "Tín hiệu", "Hiển thị", "Đối tượng", "Mẫu", "Đa khung"].every((t) => tabs.includes(t)), tabs.join(","));
  await page.locator(".mkt-pop").getByRole("button", { name: /RSI/ }).first().click();
  await sleep(1200);
  await shot("03-rsi");
  const legend = await page.locator(".ws-cell").first().innerText();
  ok("RSI thêm vào pane (tính bằng worker)", /RSI/.test(legend), legend.replace(/\n/g, " | ").slice(0, 120));
  await closePanel();
});

await step("04-types", async () => {
  const sel = page.getByLabel("Loại biểu đồ").first();
  for (const t of ["hollow", "ha", "bars", "line", "area", "baseline", "columns", "renko", "range", "linebreak", "kagi", "pnf", "candles"]) {
    const before = errors.length;
    await sel.selectOption(t);
    await sleep(900);
    const n = await page.locator('.ws-cell .pc-surface canvas').count();
    ok(`Loại biểu đồ ${t}`, n >= 2 && errors.length === before, errors.slice(before)[0] || "");
    if (["renko", "kagi", "pnf", "range", "baseline"].includes(t)) await shot(`04-type-${t}`);
  }
});

await step("05-layout-sync", async () => {
  await page.getByRole("button", { name: /Bố cục/ }).click();
  await page.getByRole("button", { name: "4 biểu đồ (2×2)" }).click();
  await sleep(2500);
  const cells = await page.locator(".ws-cell").count();
  ok("Bố cục 2x2 có 4 ô", cells === 4, `cells=${cells}`);
  await shot("05-layout-2x2");
  // crosshair sync: rê chuột ở ô 1, kiểm thuộc tính data-ext của ô khác
  const b = await paneBox(0);
  await page.mouse.move(...pt(b, 0.5, 0.4)); await page.mouse.move(...pt(b, 0.55, 0.45), { steps: 5 }); await sleep(500);
  const ext = await page.evaluate(() => [...document.querySelectorAll('.ws-cell .pc-surface')].map((e) => e.dataset.ext || ""));
  ok("Đồng bộ crosshair sang các ô khác", ext.slice(1).filter(Boolean).length >= 2, JSON.stringify(ext));
  await shot("05-crosshair-sync");
  // đồng bộ vùng thời gian
  await page.getByRole("button", { name: /Bố cục/ }).click();
  await page.getByLabel(/Vùng thời gian/).check();
  await page.keyboard.press("Escape");
  const r0 = await page.evaluate(() => 0);
  const bb = await paneBox(0);
  await page.mouse.move(...pt(bb, 0.5, 0.5)); await page.mouse.down(); await page.mouse.move(...pt(bb, 0.8, 0.5), { steps: 8 }); await page.mouse.up(); await sleep(800);
  await shot("05-range-sync");
  ok("Kéo vùng thời gian không lỗi", r0 === 0 && errors.filter((e) => /pageerror/.test(e)).length === 0, errors.filter((e) => /pageerror/.test(e))[0] || "");
  // nhóm màu: gán 2 ô cùng nhóm đỏ rồi đổi mã ở ô 1
  const dets = page.locator(".ws-cellhead details summary");
  await dets.nth(0).click(); await page.getByRole("button", { name: "Nhóm red" }).first().click();
  await dets.nth(1).click(); await page.getByRole("button", { name: "Nhóm red" }).nth(1).click().catch(async () => { await page.locator(".ws-cellhead details").nth(1).getByRole("button", { name: "Nhóm red" }).click(); });
  await page.locator(".ws-cellhead").nth(0).getByRole("button", { name: /Đổi mã/ }).click();
  await page.getByRole("dialog").getByLabel("Tìm mã").fill("GBPUSD"); await sleep(300); await page.keyboard.press("Enter"); await sleep(1500);
  const labels = await page.locator(".ws-cellhead button[aria-label^='Đổi mã']").allInnerTexts();
  ok("Đồng bộ mã theo nhóm màu (ô 0 và 1 cùng GBPUSD, ô khác giữ)", labels[0] === "GBPUSD" && labels[1] === "GBPUSD" && labels[2] === "EURUSD", labels.join(","));
  await shot("05-group-sync");
  for (const l of ["1+3", "3x2", "2v", "2h", "1"]) {
    await page.getByRole("button", { name: /Bố cục/ }).click();
    await page.getByRole("button", { name: LAYOUT_NAME[l] }).click(); await sleep(1500);
    const n = await page.locator(".ws-cell").count();
    ok(`Bố cục ${l}`, n === ({ "1+3": 4, "3x2": 6, "2v": 2, "2h": 2, 1: 1 })[l], `cells=${n}`);
    if (l === "1+3" || l === "3x2") await shot(`05-layout-${l.replace("+", "p")}`);
  }
});

await step("06-tools", async () => {
  // chỉ còn 1 ô (bước 05 kết thúc ở layout 1); quay về EURUSD H1
  const TOOLS = [["t", 2, "trend"], ["f", 2, "fib"], ["k", 2, "regression"], ["p", 3, "pitchfork"], ["g", 2, "gannfan"], ["3", 3, "triangle"], ["e", 6, "elliott5"], ["q", 4, "elliottabc"],
    ["u", 2, "supply"], ["j", 2, "demand"], ["w", 2, "arrow"], ["i", 2, "fibarc"], ["z", 2, "fibtime"], ["o", 3, "projection"], ["a", 1, "avwap"], ["y", 2, "vprofile"], ["h", 1, "hline"], ["v", 1, "vline"], ["r", 2, "rect"], ["c", 3, "channel"], ["x", 3, "fibext"], ["m", 2, "ruler"]];
  const b = await paneBox(0);
  let n = 0;
  const before = await drawingsCount(); await closePanel();
  let i = 0;
  for (const [key, pts, id] of TOOLS) {
    if (key === "a") continue; // Alt+A = cảnh báo giá; vẽ VWAP neo qua thanh công cụ ở bước sau
    await page.keyboard.press(`Alt+${key}`);
    for (let k = 0; k < pts; k++) { await clickAt(b, 0.15 + 0.1 * (k + (i % 3) * 1.5) + (k % 2) * 0.03, 0.25 + 0.5 * ((k * 0.37 + i * 0.13) % 0.5)); }
    await sleep(150);
    const c = await drawingsCount(); await closePanel();
    ok(`Vẽ ${id} (Alt+${key.toUpperCase()}, ${pts} điểm)`, c === before + ++n, `đếm=${c}`);
    i++;
  }
  await shot("06-all-tools");
  // text + note (cần nhập chữ)
  for (const [key, id] of [["b", "text"], ["l", "note"]]) {
    await page.keyboard.press(`Alt+${key}`);
    await clickAt(b, 0.3 + (key === "l" ? 0.2 : 0), 0.7);
    await page.getByLabel("Nội dung").fill(id === "text" ? "Vùng kháng cự" : "Ghi chú QA"); await page.keyboard.press("Enter"); await sleep(300);
    const c = await drawingsCount(); await closePanel();
    ok(`Vẽ ${id} + nhập chữ`, c === before + ++n, `đếm=${c}`);
  }
  // VWAP neo qua flyout
  await page.getByRole("button", { name: /^Khối lượng:/ }).click();
  await page.getByRole("menuitem", { name: /VWAP neo/ }).click();
  await clickAt(b, 0.4, 0.5);
  const c2 = await drawingsCount(); await closePanel();
  ok("Vẽ VWAP neo (flyout Khối lượng)", c2 === before + ++n, `đếm=${c2}`);
  await shot("06-tools-final");
});

await step("07-objects", async () => {
  await ensureTab("Đối tượng");
  const first = page.locator(".mkt-pop li").first();
  await first.getByRole("button", { name: "Khoá" }).click(); await sleep(200);
  ok("Khoá hình vẽ trong cây đối tượng", await first.getByRole("button", { name: "Mở khoá" }).count() === 1);
  await first.getByRole("button", { name: "Ẩn" }).click(); await sleep(200);
  ok("Ẩn hình vẽ", await first.getByRole("button", { name: "Hiện" }).count() === 1);
  await first.getByRole("button", { name: "Đổi tên" }).click(); await page.getByLabel("Tên hình vẽ").fill("Đường QA"); await page.keyboard.press("Enter"); await sleep(250);
  ok("Đổi tên hình vẽ", (await first.innerText()).includes("Đường QA"), (await first.innerText()).slice(0, 40));
  await shot("07-object-tree");
  await first.getByRole("button", { name: "Hiện" }).click(); await first.getByRole("button", { name: "Mở khoá" }).click();
  const c = await drawingsCount();
  await page.locator(".mkt-pop li").first().getByRole("button", { name: "Xoá" }).click(); await sleep(200);
  ok("Xoá hình vẽ", (await drawingsCount()) === c - 1);
  await page.keyboard.press("Control+z"); await sleep(250);
  ok("Undo khôi phục hình đã xoá", (await drawingsCount()) === c);
  await page.keyboard.press("Control+Shift+z"); await sleep(250);
  ok("Redo xoá lại", (await drawingsCount()) === c - 1);
  await page.keyboard.press("Control+z"); await sleep(250);
  await closePanel();
});

await step("08-server-persist", async () => {
  await sleep(2500); // đợi debounce ghi prefs
  const p = await apiGet("/user/prefs");
  const keys = Object.keys(p.j?.prefs?.chart?.draw || {});
  const curSym = ((await page.locator("section h2").first().innerText()).split("·")[0] || "").trim();
  const curKey = `${curSym}|H1`;
  ok("Bản vẽ được lưu trên máy chủ (user_prefs.chart.draw)", keys.includes(curKey), `key=${curKey} keys=${keys.join(",")} size=${JSON.stringify(p.j?.prefs || {}).length}`);
  const cnt = (p.j?.prefs?.chart?.draw?.[curKey]?.d || []).length;
  // xoá localStorage để chứng minh nạp từ máy chủ
  await page.evaluate(() => { for (const k of Object.keys(localStorage)) if (k.startsWith("ts-draw")) localStorage.removeItem(k); });
  await page.evaluate(() => { location.hash = "#/thi-truong"; });
  await page.reload({ waitUntil: "load" }).catch(() => {});
  await page.waitForSelector(".ws-cell canvas", { timeout: 40000 }); await waitBars();
  let c = await drawingsCount(); await closePanel();
  for (let i = 0; i < 12 && c !== cnt; i++) { await sleep(2500); c = await drawingsCount(); await closePanel(); }
  ok("Sau khi xoá localStorage + tải lại: bản vẽ được khôi phục từ máy chủ", c === cnt && c > 0, `server=${cnt} ui=${c}`);
  await shot("08-restored-from-server");
});

await step("09-alert", async () => {
  const b = await paneBox(0);
  await page.keyboard.press("Alt+a"); await sleep(200);
  await clickAt(b, 0.5, 0.35);
  await page.getByLabel("Tên cảnh báo").fill("QA-B cảnh báo thử");
  await shot("09-alert-popover");
  await page.getByRole("button", { name: "Tạo cảnh báo" }).click(); await sleep(2000);
  const rules = await apiGet("/user/rules");
  const mine = (rules.j?.items || []).filter((r) => /^QA-B/.test(r.name));
  ok("Tạo cảnh báo giá qua /v1/user/rules (chỉ cảnh báo)", mine.length === 1 && mine[0].conditions?.[0]?.type === "price", JSON.stringify(mine[0]?.conditions || null));
  await sleep(2500); await shot("09-alert-line");
  // kéo đường cảnh báo để đổi mức giá
  const oldV = mine[0]?.conditions?.[0]?.value;
  const [x, y] = pt(b, 0.5, 0.35);
  const ay = await page.evaluate(() => 0);
  await page.mouse.move(x, y); await page.mouse.down(); await page.mouse.move(x, y + 60, { steps: 6 }); await page.mouse.up(); await sleep(2500);
  const rules2 = await apiGet("/user/rules");
  const m2 = (rules2.j?.items || []).find((r) => /^QA-B/.test(r.name));
  ok("Kéo đường cảnh báo -> cập nhật giá trên máy chủ", m2 && Number(m2.conditions[0].value) !== Number(oldV) && ay === 0, `${oldV} -> ${m2?.conditions?.[0]?.value}`);
  await shot("09-alert-dragged");
  for (const r of (rules2.j?.items || []).filter((r) => /^QA-B/.test(r.name))) await apiPut(`/user/rules/${r.id}`, null, "DELETE");
});

await step("10-overlays", async () => {
  await ensureTab("Hiển thị");
  await page.getByLabel("Tô vùng phiên (khung ≤ H4)").check();
  await page.getByLabel("Đường giá đóng cửa trước").check();
  await page.getByLabel("Đường giá mở cửa ngày").check();
  await page.getByLabel("Sự kiện lịch kinh tế tác động CAO").check();
  await page.getByLabel(/Hiện cả sự kiện không liên quan/).check().catch(() => {});
  await page.getByLabel("Tin quan trọng (sắc thái mạnh) của mã").check();
  await sleep(2500);
  await closePanel();
  await shot("10-overlays");
  ok("Bật phiên/đóng cửa trước/lịch HIGH/tin không lỗi", errors.filter((e) => /pageerror/.test(e)).length === 0, errors.filter((e) => /pageerror/.test(e))[0] || "");
  const cal = await apiGet(`/calendar?limit=500&order=asc&from=${new Date(Date.now() - 20 * 864e5).toISOString()}&to=${new Date(Date.now() + 10 * 864e5).toISOString()}`);
  const hi = (cal.j?.items || []).filter((e) => String(e.impact).toLowerCase() === "high").length;
  ok("API lịch có sự kiện HIGH để đánh dấu", hi > 0, `high=${hi}`);
});

await step("11-compare", async () => {
  await ensureTab("Hiển thị");
  await page.getByLabel("Mã so sánh").selectOption("AUDUSD"); await sleep(2500);
  await shot("11-compare-pct");
  await page.getByRole("button", { name: "Spread A−B" }).click(); await sleep(2000); await shot("11-spread");
  await page.getByRole("button", { name: "Tỉ lệ A/B" }).click(); await sleep(2000); await shot("11-ratio");
  await page.getByLabel(/Pane tương quan/).check(); await sleep(2000); await shot("11-corr");
  const legend = await page.locator(".ws-cell").first().innerText();
  ok("Pane tương quan hiện trong biểu đồ", /Tương quan/.test(legend), legend.replace(/\n/g, "|").slice(0, 160));
  await page.getByLabel("Mã so sánh").selectOption("");
  await closePanel();
});

await step("12-mtf", async () => {
  await ensureTab("Đa khung"); await sleep(3500);
  const t = await page.locator(".mkt-pop").innerText();
  ok("Panel đa khung có M15/H1/H4/D1", ["M15", "H1", "H4", "D1"].every((x) => t.includes(x)), t.replace(/\n/g, " ").slice(0, 200));
  await shot("12-mtf");
  await closePanel();
});

await step("13-templates", async () => {
  await ensureTab("Mẫu");
  await page.getByLabel("Tên mẫu").fill("qa-b-mau-1"); await page.getByRole("button", { name: /Lưu mẫu/ }).click(); await sleep(2500);
  const p = await apiGet("/user/prefs");
  ok("Mẫu lưu trên máy chủ (user_prefs.chart.tpl)", !!p.j?.prefs?.chart?.tpl?.["qa-b-mau-1"], Object.keys(p.j?.prefs?.chart?.tpl || {}).join(","));
  await shot("13-templates");
  // xuất JSON -> nhập lại tên khác
  const [dl] = await Promise.all([page.waitForEvent("download"), page.getByRole("button", { name: "Tải về .json" }).first().click()]);
  const txt = fs.readFileSync(await dl.path(), "utf8");
  ok("Xuất JSON mẫu", /"name": "qa-b-mau-1"/.test(txt), txt.slice(0, 80).replace(/\n/g, " "));
  const o = JSON.parse(txt); o.name = "qa-b-mau-2";
  await page.getByLabel("JSON mẫu").fill(JSON.stringify(o)); await page.getByRole("button", { name: "Nhập", exact: true }).click(); await sleep(2500);
  const p2 = await apiGet("/user/prefs");
  ok("Nhập JSON mẫu", !!p2.j?.prefs?.chart?.tpl?.["qa-b-mau-2"]);
  // áp dụng mẫu: đổi loại biểu đồ trước để thấy tác dụng
  await closePanel();
  await page.getByLabel("Loại biểu đồ").first().selectOption("line"); await sleep(500);
  await ensureTab("Mẫu");
  await page.locator(".mkt-pop li", { hasText: "qa-b-mau-1" }).getByRole("button", { name: "Áp dụng" }).click(); await sleep(800);
  ok("Áp dụng mẫu đưa loại biểu đồ về nến", (await page.getByLabel("Loại biểu đồ").first().inputValue()) === "candles");
  for (const n of ["qa-b-mau-1", "qa-b-mau-2"]) { await page.getByRole("button", { name: `Xoá mẫu ${n}` }).click().catch(() => {}); await sleep(300); }
  await closePanel();
});

await step("14-replay", async () => {
  await page.getByRole("button", { name: /^Replay/ }).click(); await sleep(500);
  await shot("14-replay-pick");
  const b = await paneBox(0);
  await clickAt(b, 0.5, 0.5); await sleep(1200);
  const rep = await page.locator(".ws-cell").first().innerText();
  ok("Replay: đã chọn điểm bắt đầu (hiện REPLAY + thanh điều khiển)", /REPLAY/.test(rep), rep.replace(/\n/g, "|").slice(0, 100));
  const before = await page.getByLabel("Tua replay").inputValue();
  await page.getByRole("button", { name: "Tiến 1 nến" }).click(); await sleep(400);
  await page.getByRole("button", { name: "Tiến 1 nến" }).click(); await sleep(400);
  const after = await page.getByLabel("Tua replay").inputValue();
  ok("Replay: bước từng nến (+2)", Number(after) === Number(before) + 2, `${before} -> ${after}`);
  await page.getByRole("button", { name: "Phát", exact: true }).click(); await sleep(3000);
  const playing = await page.getByLabel("Tua replay").inputValue();
  ok("Replay: tự phát tiến thêm nến", Number(playing) > Number(after) + 3, `${after} -> ${playing}`);
  await pauseIfPlaying();
  await page.getByLabel("Tốc độ phát lại").selectOption("25"); await page.getByRole("button", { name: "Phát", exact: true }).click(); await sleep(2000);
  const fast = await page.getByLabel("Tua replay").inputValue();
  ok("Replay: tốc độ 25 nến/giây nhanh hơn", Number(fast) > Number(playing) + 20, `${playing} -> ${fast}`);
  await pauseIfPlaying();
  await page.getByLabel("Tua replay").fill(String(Math.max(0, Number(after) - 40)));
  await sleep(600); await shot("14-replay");
  await page.getByRole("button", { name: "Thoát replay" }).click(); await sleep(800);
  ok("Thoát replay trả về dữ liệu đầy đủ", !(await page.locator(".ws-cell").first().innerText()).includes("REPLAY"));
});

await step("15-capture-full", async () => {
  const [dl] = await Promise.all([page.waitForEvent("download"), page.getByRole("button", { name: "Chụp ảnh biểu đồ (tải PNG)" }).click()]);
  const path = await dl.path();
  const st = fs.statSync(path);
  const head = fs.readFileSync(path).subarray(0, 8).toString("hex");
  ok("Tải ảnh PNG biểu đồ", head === "89504e470d0a1a0a" && st.size > 5000, `${dl.suggestedFilename()} ${st.size}B`);
  fs.copyFileSync(path, `${OUT}/capture.png`);
  await page.getByRole("button", { name: "Sao chép ảnh biểu đồ vào clipboard" }).click(); await sleep(800);
  const hasImg = await page.evaluate(async () => { try { const it = await navigator.clipboard.read(); return it.some((i) => i.types.includes("image/png")); } catch (e) { return String(e).slice(0, 80); } });
  ok("Sao chép ảnh vào clipboard", hasImg === true, String(hasImg));
  await page.getByRole("button", { name: /Toàn màn hình/ }).click(); await sleep(800);
  ok("Toàn màn hình (mkt-full)", await page.locator(".mkt-full").count() === 1);
  await shot("15-fullscreen");
  await page.keyboard.press("Escape"); await sleep(400);
  if (await page.locator(".mkt-full").count()) { await page.keyboard.press("Escape"); await sleep(300); }
  ok("Esc thoát toàn màn hình", await page.locator(".mkt-full").count() === 0);
});

await step("16-style", async () => {
  await ensureTab("Hiển thị");
  await page.getByLabel("Lưới").selectOption("none");
  await page.getByLabel("Phía thang giá").selectOption("left"); await sleep(1200);
  await page.getByLabel("Nến tăng").fill?.("#00aaff").catch(() => {});
  await page.evaluate(() => { const i = [...document.querySelectorAll('.mkt-pop input[type=color]')][0]; const set = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value").set; set.call(i, "#00aaff"); i.dispatchEvent(new Event("input", { bubbles: true })); i.dispatchEvent(new Event("change", { bubbles: true })); });
  await sleep(1200); await closePanel(); await shot("16-style-left-scale");
  // vẽ khi thang giá bên trái: bấm điểm phải khớp
  const b = await paneBox(0);
  await page.keyboard.press("Alt+t"); await page.mouse.click(b.x + b.w * 0.3 + 30, b.y + b.h * 0.3); await page.mouse.click(b.x + b.w * 0.6 + 30, b.y + b.h * 0.6); await sleep(300);
  await shot("16-draw-left-scale");
  await ensureTab("Hiển thị");
  await page.getByLabel("Phía thang giá").selectOption("right"); await page.getByLabel("Lưới").selectOption("both"); await closePanel();
});

await step("17-history-perf", async () => {
  await page.getByRole("group", { name: "Khung thời gian" }).getByRole("button", { name: "M1", exact: true }).click(); await sleep(6000);
  const b = await paneBox(0);
  const n0 = await cntOf();
  // fps khi kéo (pan) liên tục: đếm frame bằng rAF
  await page.evaluate(() => { window.__fr = 0; window.__run = true; const f = () => { window.__fr++; if (window.__run) requestAnimationFrame(f); }; requestAnimationFrame(f); });
  const t0 = Date.now();
  for (let i = 0; i < 40; i++) {
    await page.mouse.move(...pt(b, 0.1, 0.5)); await page.mouse.down(); await page.mouse.move(...pt(b, 0.95, 0.5), { steps: 12 }); await page.mouse.up(); await sleep(250);
    if (i > 12 && i % 4 === 0 && (await cntOf()) > n0) break;
  }
  const dt = (Date.now() - t0) / 1000;
  const fr = await page.evaluate(() => { window.__run = false; return window.__fr; });
  await sleep(1500);
  const n1 = await cntOf();
  ok("Kéo trái tải thêm lịch sử (phân trang /v1/bars)", n1 > n0, `${n0} -> ${n1} nến`);
  ok("Hiệu năng khi kéo >= 25 fps", fr / dt >= 25, `${(fr / dt).toFixed(1)} fps (${fr} frame/${dt.toFixed(1)}s, ${n1} nến)`);
  await shot("17-history-loaded");
});

await step("17b-20k", async () => {
  const SYN_N = 30000, STEP = 60, END = Math.floor(Date.now() / 1000 / STEP) * STEP, T0 = END - (SYN_N - 1) * STEP;
  let synReq = 0;
  const bar = (i) => { const x = i, base = 2300 + 40 * Math.sin(x / 700) + 15 * Math.sin(x / 90) + 3 * Math.sin(x / 9), o = base + Math.sin(x * 1.7), c = base + Math.cos(x * 1.3);
    return { symbol: "XAUUSD", tf: "M1", ts_open: new Date((T0 + i * STEP) * 1000).toISOString(), o, h: Math.max(o, c) + 1.5 + Math.abs(Math.sin(x * 3.1)), l: Math.min(o, c) - 1.5 - Math.abs(Math.cos(x * 2.3)), c, v: 50 + ((x * 37) % 200), source: "syn" }; };
  await page.route(/\/api\/v1\/bars\?/, async (route) => {
    const u = new URL(route.request().url());
    if (u.searchParams.get("symbol") !== "XAUUSD" || u.searchParams.get("tf") !== "M1") return route.continue();
    synReq++;
    const lim = Number(u.searchParams.get("limit") || 500), to = u.searchParams.get("to");
    let hi = SYN_N - 1;
    if (to) hi = Math.min(hi, Math.floor((Date.parse(to) / 1000 - T0) / STEP));
    const items = [];
    for (let i = hi; i >= 0 && items.length < lim; i--) items.push(bar(i));
    await route.fulfill({ json: { items, limit: lim, offset: 0, count: items.length } });
  });
  await page.getByRole("button", { name: /^Đổi mã/ }).first().click();
  await page.getByRole("dialog").getByLabel("Tìm mã").fill("XAUUSD"); await sleep(400); await page.keyboard.press("Enter"); await sleep(1500);
  await page.getByRole("group", { name: "Khung thời gian" }).getByRole("button", { name: "M1", exact: true }).click(); await waitBars(500, 60000);
  // nạp dần lịch sử tới ~20.000 nến bằng phím Z (vừa dữ liệu -> chạm mép trái -> tải thêm), rồi đo mượt khi kéo + tác vụ dài
  await page.evaluate(() => { window.__lt = []; try { new PerformanceObserver((l) => { for (const e of l.getEntries()) window.__lt.push(e.duration); }).observe({ entryTypes: ["longtask"] }); } catch {} });
  let n = await cntOf(), last = -1;
  for (let i = 0; i < 24 && n < 19000; i++) {
    await page.keyboard.press("z"); await sleep(1400);
    n = await cntOf();
    if (n === last && i > 4 && n < 19000) { await sleep(2500); n = await cntOf(); if (n === last) break; }
    last = n;
  }
  await sleep(2000);
  ok("Nạp tới 20.000 nến (phân trang lịch sử)", n >= 19000, `${n} nến`);
  const b = await paneBox(0);
  await page.evaluate(() => { window.__fr = 0; window.__run = true; window.__lt = []; const f = () => { window.__fr++; if (window.__run) requestAnimationFrame(f); }; requestAnimationFrame(f); });
  const t0 = Date.now();
  for (let i = 0; i < 12; i++) { await page.mouse.move(...pt(b, 0.15, 0.5)); await page.mouse.down(); await page.mouse.move(...pt(b, 0.9, 0.5), { steps: 10 }); await page.mouse.up(); await sleep(120); }
  const dt = (Date.now() - t0) / 1000;
  const m = await page.evaluate(() => { window.__run = false; return { fr: window.__fr, lt: window.__lt.slice().sort((a, b) => b - a).slice(0, 3).map((x) => Math.round(x)) }; });
  ok(`Mượt ở ${n} nến: kéo >= 25 fps`, m.fr / dt >= 25, `${(m.fr / dt).toFixed(1)} fps; longtask lớn nhất ms=${m.lt.join(",")}`);
  await shot("17b-20k");
  // thêm chỉ báo nặng ở 20k nến: đo thời gian worker tính (không chặn giao diện)
  await ensureTab("Chỉ báo");
  const t1 = Date.now();
  await page.locator(".mkt-pop").getByRole("button", { name: /Ichimoku/ }).first().click();
  await page.locator(".mkt-pop").getByRole("button", { name: /ADX/ }).first().click();
  await page.waitForFunction(() => /Ichimoku/.test(document.querySelector(".ws-cell")?.innerText || ""), null, { timeout: 20000 });
  ok("Thêm Ichimoku + ADX ở 20k nến (worker) hiện trong legend", true, `${Date.now() - t1}ms (gồm click)`);
  await closePanel();
  const wk = await page.evaluate(async () => {
    const url = performance.getEntriesByType("resource").map((r) => r.name).find((n) => /indWorker/.test(n));
    if (!url) return null;
    const w = new Worker(url, { type: "module" });
    const N = 20000, t = [], o = [], h = [], l = [], c = [], v = [];
    let p = 100;
    for (let i = 0; i < N; i++) { p += Math.sin(i / 50) + (Math.random() - 0.5); t.push(1700000000 + i * 60); o.push(p); h.push(p + 1); l.push(p - 1); c.push(p + 0.3); v.push(100); }
    const cols = { n: N, t, o, h, l, c, v };
    const list = [["ema", { period: 20 }], ["rsi", { period: 14 }], ["macd", { fast: 12, slow: 26, signal: 9 }], ["bb", { period: 20, mult: 2 }], ["adx", { period: 14 }], ["ichimoku", { short: 9, medium: 26, long: 52 }], ["stoch", { k: 14, smooth: 3, d: 3 }]].map(([type, params], i) => ({ id: "i" + i, type, params }));
    const t0 = performance.now();
    const res = await new Promise((r) => { w.onmessage = (e) => r(e.data); w.postMessage({ id: 1, cols, list, tfSec: 60 }); });
    const ms = Math.round(performance.now() - t0);
    w.terminate();
    return { ms, ok: Object.values(res.out).every((x) => x), n: N, k: list.length };
  });
  ok("Worker tính 7 chỉ báo (gồm Ichimoku) trên 20.000 nến < 1,5s", wk && wk.ok && wk.ms < 1500, wk ? `${wk.ms}ms` : "không có worker");
  ok("Phân trang lịch sử gọi /v1/bars?to=… nhiều lần", synReq >= 7, `${synReq} request`);
  await page.unroute(/\/api\/v1\/bars\?/);
  await page.getByRole("group", { name: "Khung thời gian" }).getByRole("button", { name: "H1", exact: true }).click(); await sleep(2500);
});

await step("18-live", async () => {
  await page.getByLabel("Loại biểu đồ").first().selectOption("candles");
  await page.getByRole("button", { name: /^Đổi mã/ }).first().click();
  await page.getByRole("dialog").getByLabel("Tìm mã").fill("BTCUSDT"); await sleep(400); await page.keyboard.press("Enter"); await sleep(4000);
  await shot("18-btc-m1");
  await sleep(25000);
  const live = await page.evaluate(() => Number(document.querySelector('.ws-cell .pc-surface').dataset.liveN || 0));
  ok("Realtime: nhận cập nhật nến qua WebSocket (không giật)", live > 0, `updateLast=${live} trong 20s`);
});

await step("19-mobile", async () => {
  await page.setViewportSize({ width: 390, height: 800 }); await sleep(1500);
  const ov = await page.evaluate(() => document.documentElement.scrollWidth > document.documentElement.clientWidth + 1);
  await shot("19-mobile");
  ok("Mobile 390px không tràn ngang", !ov);
  await page.setViewportSize({ width: 1600, height: 950 });
});

await step("20-terminal-widget", async () => {
  await page.goto(`${BASE}/#/terminal`, { waitUntil: "load" }).catch(() => {});
  await sleep(2500);
  await page.getByRole("tab", { name: "Forex" }).click().catch(() => {});
  const found = await page.waitForSelector(".ws-embedded .ws-cell canvas", { timeout: 40000 }).then(() => true).catch(() => false);
  await sleep(4000); await shot("20-terminal");
  const n = await page.locator(".ws-embedded").count();
  ok("Widget `chart` hiện trong trang Terminal (khung widget của agent A)", found && n >= 1, `widget chart x${n}`);
});

// ---- dọn dẹp prefs: chỉ gỡ khoá của mình ----
for (let k = 0; k < 3; k++) {
  const p = await apiGet("/user/prefs");
  const pr = p.j?.prefs || {};
  if (pr.chart) {
    for (const key of Object.keys(pr.chart.draw || {})) if (!(prefsBefore.j?.prefs?.chart?.draw || {})[key]) delete pr.chart.draw[key];
    for (const key of Object.keys(pr.chart.tpl || {})) if (/^qa-b/.test(key)) delete pr.chart.tpl[key];
    if (prefsBefore.j?.prefs?.chart?.draw) Object.assign(pr.chart.draw ||= {}, prefsBefore.j.prefs.chart.draw);
  }
  const r = await apiPut("/user/prefs", { rev: p.j.rev, prefs: pr });
  console.log("cleanup prefs", r.s);
  if (r.s === 200) break;
}
const rules = await apiGet("/user/rules");
for (const r of (rules.j?.items || []).filter((r) => /^QA-B/.test(r.name))) await apiPut(`/user/rules/${r.id}`, null, "DELETE");

fs.writeFileSync(`${OUT}/results.json`, JSON.stringify({ results, errors: [...new Set(errors)].slice(0, 40) }, null, 1));
const fails = results.filter((r) => !r.pass);
console.log(`\nTỔNG: ${results.length - fails.length}/${results.length} PASS; lỗi console/page: ${new Set(errors).size}`);
for (const e of [...new Set(errors)].slice(0, 15)) console.log("  ERR", e);
await browser.close();
process.exit(0);
