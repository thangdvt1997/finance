// QA "AI Training Class" (master): MOCK=1 dùng fixture chặn /api/v1/ai-trading/class/* (CHỈ trong QA, không có trong bản chạy); MOCK=0 chạy backend thật + kịch bản demo đầu-cuối.
// Kiểm: không tràn ngang, không lộ tên nguồn, không nút đặt lệnh, ảnh không hỏng, lỗi JS. Ảnh vào OUT.
import { chromium } from "playwright";
import fs from "node:fs";
const BASE = process.env.BASE || "http://127.0.0.1:8580", OUT = process.env.OUT || "out", MOCK = process.env.MOCK === "1";
fs.mkdirSync(OUT, { recursive: true });
const PNG = Buffer.from("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg==", "base64");
const au = (id, name, role) => ({ user_id: id, name, role });
const ME = au("qa", "QA Master", "master"), AI = au("ai", "AI học trò", "ai");
const now = new Date().toISOString();
const M = (seq, kind, author, text, extra = {}) => ({ id: `m${seq}`, seq, room_id: "r1", kind, author, text, created_at: now, pinned: false, attachments: [], data: null, review: null, understanding: null, chips: [], ...extra });
const msgs = [
  M(1, "text", ME, "Kịch bản sell EURUSD H1: sau đà tăng mạnh 6 nến, nến có bóng trên dài thì vào bán, SL trên đỉnh, TP 2R."),
  M(2, "text", AI, "Mình hiểu sơ bộ như sau. **Bước 3/13**: điều kiện hình thành.\n\n| Mục | Giá trị |\n|---|---|\n| Mã | EURUSD |\n| Khung | H1 |\n\n- Đà tăng: 6 nến\n- Bóng trên: chưa rõ tỷ lệ\n\nBóng trên dài là bao nhiêu phần của nến? Còn nếu giá phá đáy nến tín hiệu thì sao?", { understanding: { ma_khung: { value: "EURUSD H1", confidence: "cao" }, bong_tren: { value: "chưa rõ tỷ lệ", confidence: "thấp" } } }),
  M(3, "scan", AI, "Mình quét được 6 lần xuất hiện, bạn gắn nhãn giúp.", { data: { round: 1, precision_hint: "Chưa có nhãn nên chưa tính độ chính xác.", examples: Array.from({ length: 6 }, (_, i) => ({ id: `e${i + 1}`, symbol: "EURUSD", tf: "H1", ts: now, image_url: `/api/v1/ai-trading/class/rooms/r1/media/ex${i + 1}`, entry: 1.0912 + i / 1e4, sl: 1.0950, note: "Bóng trên 48% thân" })) } }),
  M(4, "result_card", AI, "", { data: { scenario_id: "CL-QA-1", verdict: "no_edge", metrics: { expectancy_r: -0.12, p_vs_random: 0.41, trades: 183, max_drawdown_r: 9.4 }, honesty: ["Walk-forward dev, ngoài mẫu, đã trừ chi phí.", "Không hơn baseline ngẫu nhiên (p=0,41)."], disclaimer: "Không phải khuyến nghị; chỉ nghiên cứu/paper." } }),
  M(5, "annotation", AI, "Đỉnh đã vẽ.", { data: { kind: "dinh", note: "Đỉnh quan trọng", symbol: "EURUSD", tf: "H1" } }),
];
const room = { id: "r1", title: "Nhấn chìm bóng trên EURUSD", created_at: now, updated_at: now, members: [{ ...ME, joined_at: now }, { user_id: "ex1", name: "Anh Minh", role: "expert", joined_at: now }], phase: "interview", step: 3, profile_name: "KB-QA", profile_version: 2, msg_count: 5, last_message: { author: AI, text: msgs[4].text, created_at: now } };
const detail = { room, messages: msgs, pinned: [], chips: [{ label: "/tom-tat", command: "/tom-tat" }, { label: "/quet", command: "/quet" }, { label: "Bỏ qua câu này", text: "bỏ qua" }, { label: "/bien-the", command: "/bien-the" }], state: { phase: "interview", step: 3, idx: 3, total: 13, missing_required: ["Điểm kích hoạt", "SL/TP"] }, labels_summary: {}, pending_actions: [], has_more: false };
const sse = (evs) => evs.map((e) => `data: ${JSON.stringify(e)}\n\n`).join("");
async function mock(ctx) {
  const json = (route, body, status = 200) => route.fulfill({ status, contentType: "application/json", body: JSON.stringify(body) });
  await ctx.route(/\/api\/v1\/ai-trading\/class\//, async (route) => {
    const u = new URL(route.request().url()), p = u.pathname.replace("/api/v1/ai-trading/class", ""), m = route.request().method();
    if (/\/media\/ex/.test(p)) return route.fulfill({ status: 200, contentType: "image/png", body: PNG });
    if (p === "/rooms" && m === "GET") return json(route, { items: [room, { ...room, id: "r2", title: "Sóng hồi 61.8% XAUUSD", phase: "intake", profile_version: null, last_message: null, members: [ME] }], llm: { provider: "local", enabled: true, note: "Chưa có khoá đám mây; đang dùng mô hình cục bộ." } });
    if (/^\/rooms\/r1$/.test(p)) return json(route, { ...detail, messages: msgs });
    if (/^\/rooms\/r2$/.test(p)) return json(route, { ...detail, room: { ...room, id: "r2", title: "Sóng hồi 61.8% XAUUSD" }, messages: [], chips: [] });
    if (/\/messages$/.test(p) && m === "POST") { msgs.push(M(90, "text", ME, "đúng"), M(91, "text", AI, "Ghi nhận. **Câu tiếp theo:** điểm vào lệnh là phá đáy nến tín hiệu hay đóng cửa dưới nó?")); return route.fulfill({ status: 200, headers: { "content-type": "text/event-stream" }, body: sse([{ type: "user", message: M(90, "text", ME, "đúng") }, { type: "meta", message_id: "m91", phase: "interview", step: 3 }, { type: "delta", text: "Ghi nhận. " }, { type: "delta", text: "**Câu tiếp theo:** điểm vào lệnh là phá đáy nến tín hiệu hay đóng cửa dưới nó?" }, { type: "turn", message: M(91, "text", AI, "Ghi nhận. **Câu tiếp theo:** điểm vào lệnh là phá đáy nến tín hiệu hay đóng cửa dưới nó?"), turn: { reply: "", phase: "interview", step: 3, questions: ["x"], chips: [], used_llm: false } }, { type: "done" }]) }); }
    if (/\/labels$/.test(p) && m === "GET") return json(route, { items: [{ example_id: "e1", verdict: "dung", reason: "Đúng hình" }], summary: { n_examples: 6, n_labeled: 1, coverage: 1 / 6, precision: 1, precision_strict: 1, rounds: 1, by_round: [{ round: 1, n: 1, precision: 1 }], advice: "Gắn thêm ít nhất 5 ví dụ." } });
    if (/\/labels$/.test(p)) return json(route, { label: {}, summary: {} }, 200);
    if (/\/profile$/.test(p)) return json(route, { profile: { name: "KB-QA", version: 2, answers: { ma_khung: "EURUSD H1", da_tang: { value: "6 nến", confidence: "cao" } }, open_questions: ["Tỷ lệ bóng trên?"], assumptions: ["Chỉ phiên London"], contributors: ["QA Master", "Anh Minh"], labels: [] }, understanding: { ma_khung: { value: "EURUSD H1", confidence: "cao" } }, versions: [{ version: 1, note: "đầu", created_at: now, by: "QA" }, { version: 2, note: "thêm bóng trên", created_at: now, by: "Anh Minh" }] });
    if (/\/profile\/diff/.test(p)) return json(route, { items: [{ section: "answers", title: "Bóng trên", change: "changed", before: "chưa rõ", after: "≥ 40% thân" }] });
    if (/\/profile\/export$/.test(p)) return json(route, { ok: true, yaml: "id: CL-QA-1\nname: QA\nside: sell\n", errors: [], warnings: ["DSL hiện chỉ chạy sell"], registered: false });
    if (/\/actions$/.test(p) || /\/attachments$/.test(p) || /\/pins$/.test(p) || /\/review$/.test(p)) return json(route, { ok: true, message: msgs[4], attachment: {}, action: { id: "a1", status: "queued", command: "ve" }, warnings: [] }, 201);
    return json(route, { detail: "mock: chưa có" }, 404);
  });
}
const browser = await chromium.launch();
const res = [], errs = [];
const sizes = [[1440, 900, "desktop"], [1024, 800, "laptop"], [820, 1100, "tablet"], [390, 800, "mobile"]];
let n = 0;
for (const [w, h, name] of sizes) for (const th of ["dark", "light"]) {
  const ctx = await browser.newContext({ viewport: { width: w, height: h }, colorScheme: th, baseURL: BASE });
  await ctx.request.post(`${BASE}/auth/login`, { data: { platform: "master", login: process.env.QA_USER, secret: process.env.QA_PASS }, headers: { Origin: BASE, "Content-Type": "application/json" } });
  await ctx.addInitScript((t) => { try { const v = JSON.parse(localStorage.getItem("ts-ux") || "{}"); v.onboarded = 99; localStorage.setItem("ts-ux", JSON.stringify(v)); localStorage.setItem("ts-theme", t); localStorage.removeItem("cr-room"); } catch { /* bỏ */ } }, th);
  if (MOCK) await mock(ctx);
  const page = await ctx.newPage(); page.setDefaultTimeout(15000);
  page.on("pageerror", (e) => errs.push(String(e.message).slice(0, 200)));
  page.on("console", (m) => { if (m.type() === "error" && !/Failed to load resource/.test(m.text())) errs.push(m.text().slice(0, 200)); });
  page.on("response", async (rs) => { if (n === 0 && /\/v1\/bars\?/.test(rs.url())) { const j = await rs.json().catch(() => null); console.log("bars", rs.url().split("?")[1], rs.status(), j && (j.items || []).length); } });
  await page.goto(`${BASE}/#/ai-trading`, { waitUntil: "load" });
  await page.getByRole("tab", { name: /AI Training Class/ }).first().click();
  await page.waitForTimeout(2000);
  const mobile = w < 1180;
  const view = async (v) => { if (mobile) await page.locator(".cr-nav").getByRole("tab", { name: v }).click(); await page.waitForTimeout(300); };
  if (mobile) await view(/Phòng/);
  await page.screenshot({ path: `${OUT}/cls-${name}-${th}-1rooms.png` });
  await page.locator(".cr-room").first().click().catch(() => {});
  await page.waitForTimeout(1500);
  if (mobile) await view(/Chat/);
  await page.screenshot({ path: `${OUT}/cls-${name}-${th}-2chat.png` });
  if (n === 0) {
    // tương tác (desktop tối): gõ /, chip, gửi tin SSE, nhận định, nhãn, biểu đồ, sổ tay
    const ta = page.locator("textarea[aria-label='Tin nhắn']"); await ta.fill("/t");
    await page.locator("[role=listbox]").waitFor(); await page.screenshot({ path: `${OUT}/cls-slash.png` }); await ta.fill("");
    await ta.fill("đúng"); await ta.press("Enter");
    await page.getByText(/Câu tiếp theo/).first().waitFor({ timeout: 20000 }).catch(async (e) => { await page.screenshot({ path: `${OUT}/cls-debug.png` }); console.log("sendfail", (await page.locator(".cr-bottom").innerText()).slice(0, 300)); throw e; });
    await page.getByRole("button", { name: "Phản bác" }).first().click(); await page.screenshot({ path: `${OUT}/cls-review.png` });
    await page.locator(".cr-msg.ai").first().scrollIntoViewIfNeeded();
    await page.getByRole("tab", { name: /Ví dụ/ }).click(); await page.waitForTimeout(800);
    await page.getByRole("button", { name: "ĐÚNG" }).first().click().catch(() => {}); await page.screenshot({ path: `${OUT}/cls-labels.png` });
    await page.getByRole("tab", { name: /Biểu đồ/ }).click(); await page.waitForTimeout(2500); await page.screenshot({ path: `${OUT}/cls-chart.png` });
    await page.getByRole("tab", { name: /Sổ tay/ }).click(); await page.waitForTimeout(1200); await page.getByRole("button", { name: /Xuất & kiểm tra/ }).click(); await page.waitForTimeout(800); await page.screenshot({ path: `${OUT}/cls-notebook.png` });
    await page.getByRole("button", { name: /Mời/ }).first().click(); await page.waitForTimeout(300); await page.screenshot({ path: `${OUT}/cls-invite.png` });
  }
  if (mobile) { await view(/Bảng bên/); await page.screenshot({ path: `${OUT}/cls-${name}-${th}-3side.png` }); await view(/Chat/); }
  const info = await page.evaluate(() => {
    const txt = document.body.innerText, root = document.querySelector(".cr");
    return {
      overflow: document.documentElement.scrollWidth > innerWidth + 1,
      offender: [...document.querySelectorAll(".cr *")].filter((e) => e.getBoundingClientRect().right > innerWidth + 1 && e.getBoundingClientRect().width > 0 && !e.closest("table,.scroll-x,.cr-chips,.cr-sidetabs,.cr-tw,.cr-pre,.cr-roomlist")).slice(0, 3).map((e) => e.tagName + "." + String(e.className).slice(0, 40)),
      mounted: !!root, leak: /binance|yahoo|metaquotes|twelve|dukascopy|\bmt5\b|openai|anthropic_api/i.test(txt),
      orderBtn: [...document.querySelectorAll("button,a")].some((b) => /^(buy|sell|đặt lệnh|mua|bán|place order)$/i.test(b.textContent.trim())),
      broken: [...document.querySelectorAll(".cr img")].filter((i) => i.complete && i.naturalWidth === 0).length,
      unlabeledBtn: [...document.querySelectorAll(".cr button")].filter((b) => !b.textContent.trim() && !b.getAttribute("aria-label") && !b.title).length,
    };
  });
  res.push({ w, th, ...info }); console.log(JSON.stringify(res.at(-1)));
  await ctx.close(); n++;
}
console.log("errors", JSON.stringify(errs));
await browser.close();
const bad = res.filter((r) => r.overflow || r.offender.length || !r.mounted || r.leak || r.orderBtn || r.broken || r.unlabeledBtn);
console.log(bad.length ? "FAIL" : "PASS");
process.exit(bad.length || errs.length ? 1 : 0);
