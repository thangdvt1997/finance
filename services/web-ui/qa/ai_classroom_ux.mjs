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
const KEYS = [["context","Bối cảnh & xu hướng lớn","Context & big trend"],["symbol_tf","Mã & khung","Symbol & timeframe"],["formation","Các bước hình thành","Formation steps"],["trigger","Điểm kích hoạt vào lệnh","Entry trigger"],["invalidation","Điều kiện HUỶ","Cancel condition"],["sl","SL","SL"],["tp","TP / quản lý lệnh","TP / management"],["sizing","Khối lượng & rủi ro","Size & risk"],["filters","Bộ lọc","Filters"],["ex_ok","Ví dụ ĐÚNG","Right examples"],["ex_bad","Ví dụ SAI / gần giống","Wrong examples"],["failure","Điều gì làm thất bại","What fails"],["symmetry","Phiên bản đối xứng","Mirror"],["rationale","Lý do kinh tế / tâm lý","Rationale"],["assumptions","Giả định ngầm","Hidden assumptions"],["open_questions","Câu hỏi còn mở","Open questions"]];
const FILL = { symbol_tf: ["EURUSD H1","cao",true,true], formation: ["Đà tăng 6 nến liên tiếp, bóng trên >= 40% thân","vừa",true,false], trigger: ["Vào Sell khi nến đóng dưới đáy nến tín hiệu","thấp",false,false], sl: ["Trên đỉnh nến tín hiệu + 0,25 ATR","vừa",true,false], tp: ["TP 2R","vừa",true,false] };
const mkRows = (full) => KEYS.map(([key, vi, en]) => { const f = full && FILL[key]; return { key, title_vi: vi, title_en: en, text: f ? f[0] : "", confidence: f ? f[1] : "trống", source: f ? { author: "QA Master", turn: 1 } : { author: "", turn: 0 }, confirmed: !!(f && f[3]), quantified: !!(f && f[2]), has_examples: false, ai_understanding: f ? "AI hiểu: " + f[0].toLowerCase() : "", editable: !["assumptions","open_questions"].includes(key) }; });
const CANVAS1 = { rows: mkRows(true), clarity: { score: 42, breakdown: { filled: 0.3, confirmed: 0.1, quantified: 0.3, examples: 0 }, weakest_row: "trigger", next_question: "Chính xác điều gì xảy ra thì kịch bản kích hoạt vào lệnh?" }, profile_version: 2 };
const CANVAS0 = { rows: mkRows(false), clarity: { score: 0, breakdown: {}, weakest_row: "context", next_question: "Bối cảnh lớn là gì?" }, profile_version: 0 };
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
    if (/\/canvas$/.test(p)) return json(route, p.includes("/r2/") ? CANVAS0 : CANVAS1);
    return json(route, { detail: "mock: chưa có" }, 404);
  });
}

const browser = await chromium.launch();
const res = [], errs = [], axeRes = [];
const sizes = (process.env.SIZES ? process.env.SIZES.split(",").map((x) => [+x, 850]) : [[375, 800], [768, 1000], [1366, 850], [1920, 1000]]);
const SHOT = process.env.SHOT !== "0";
let axeSrc = ""; try { axeSrc = fs.readFileSync("node_modules/axe-core/axe.min.js", "utf8"); } catch { /* không có axe */ }
for (const [w, h] of sizes) for (const th of ["dark", "light"]) for (const lang of (w === 1366 ? ["vi", "en"] : ["vi"])) {
  const ctx = await browser.newContext({ viewport: { width: w, height: h }, colorScheme: th, baseURL: BASE });
  await ctx.request.post(`${BASE}/auth/login`, { data: { platform: "master", login: process.env.QA_USER, secret: process.env.QA_PASS }, headers: { Origin: BASE, "Content-Type": "application/json" } });
  await ctx.addInitScript(([t, l]) => { try { const v = JSON.parse(localStorage.getItem("ts-ux") || "{}"); v.onboarded = 99; v.theme = t; localStorage.setItem("ts-ux", JSON.stringify(v)); localStorage.setItem("ts-theme", t); localStorage.setItem("ts-aitrading-lang", l); localStorage.setItem("cr-tour-done", "1"); localStorage.removeItem("cr-room"); } catch {} }, [th, lang]);
  await mock(ctx);
  await ctx.route(/\/api\/v1\/user\/prefs/, (route) => route.request().method() === "GET" ? route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ rev: 1, prefs: { theme: th } }) }) : route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ rev: 2, prefs: { theme: th } }) }),);
  const page = await ctx.newPage(); page.setDefaultTimeout(15000);
  page.on("pageerror", (e) => { errs.push(`${w}${th}: ${String(e.message).slice(0, 200)}`); console.log("PAGEERR", e.message.slice(0, 300), String(e.stack || "").slice(0, 400)); });
  page.on("console", (m) => { if (m.type() === "error" && !/Failed to load resource/.test(m.text())) errs.push(`${w}${th}: ${m.text().slice(0, 200)}`); });
  await page.goto(`${BASE}/#/ai-trading`, { waitUntil: "load" });
  await page.getByRole("tab", { name: /AI Training Class|AI Training Class/ }).first().click().catch(async (e) => { await page.screenshot({ path: `${OUT}/fail-tab-${w}-${th}.png` }); console.log("tabfail", await page.evaluate(() => document.body.innerText.slice(0, 300))); throw e; });
  await page.waitForTimeout(1800);
  const mobile = w < 1180, tag = `${w}-${th}-${lang}`;
  const nav = async (re) => { if (mobile) await page.locator(".cr-nav button").filter({ hasText: re }).click(); await page.waitForTimeout(350); };
  const shot = async (n) => { if (SHOT) await page.screenshot({ path: `${OUT}/ux-${n}-${tag}.png` }); };
  const check = async (n) => {
    const info = await page.evaluate(([mobile]) => {
      const R = (e) => e.getBoundingClientRect();
      const vis = (e) => { const r = R(e); return r.width > 0 && r.height > 0 && getComputedStyle(e).visibility !== "hidden"; };
      return {
        overflow: document.documentElement.scrollWidth - innerWidth,
        off: [...document.querySelectorAll(".cr *")].filter((e) => vis(e) && R(e).right > innerWidth + 1 && !e.closest("table,.cr-sidetabs,.gd-tabs,.cr-chips,.cr-cmds,.xg-scroll,.scroll-x,[data-scroll],.cr-top,pre,code")).slice(0, 3).map((e) => e.className.toString().slice(0, 40)),
        small: [...document.querySelectorAll(".cr button,.cr a.btn,.cr input,.cr select,.cr [role=tab]")].filter((e) => vis(e) && !e.closest("[aria-hidden=true]") && (R(e).height < (mobile ? 36 : 24) || R(e).width < (mobile ? 32 : 24)) && e.type !== "checkbox" && e.type !== "radio").slice(0, 4).map((e) => `${(e.getAttribute("aria-label") || e.textContent || "").trim().slice(0, 20)}:${Math.round(R(e).width)}x${Math.round(R(e).height)}`),
        leak: /binance|yahoo|metaquotes|twelve|dukascopy|openai/i.test(document.body.innerText),
        slash: [...document.querySelectorAll(".cr")].some((e) => { const c = e.cloneNode(true); c.querySelectorAll(".cr-chips,.cr-msgs").forEach((x) => x.remove()); return /(^|\s)\/(test|quet|luu|bien-the|doi-xung|so-sanh|giai-thich|tom-tat|hoi-them|ve)\b/.test(c.innerText || c.textContent); }),
      };
    }, [mobile]);
    if (info.overflow > 0 || info.off.length || info.small.length || info.leak || info.slash) res.push({ n, tag, ...info });
    if (axeSrc) { await page.evaluate(axeSrc); const v = await page.evaluate(async () => { const r = await axe.run(".cr", { runOnly: ["wcag2a", "wcag2aa"], resultTypes: ["violations"] }); return r.violations.map((x) => `${x.id}:${x.nodes.length}:${(x.nodes[0]?.target || []).join(" ").slice(0, 60)}`); }); if (v.length) axeRes.push({ n, tag, v }); }
  };
  try {
  // 1 rỗng
  const rooms = async () => { if (!mobile && !(await page.locator(".cr-room").first().isVisible().catch(() => false))) { await page.locator(".cr-top-l .cr-only-d").first().click(); await page.waitForTimeout(300); } if (mobile) { await page.locator(".cr-top-l .cr-only-m").click(); await page.waitForTimeout(300); } };
  await rooms(); await page.locator(".cr-room").nth(1).click(); await page.waitForTimeout(900); await nav(/Chat/); await shot("1-empty"); await check("empty");
  // 2 đang chat
  await rooms(); await page.locator(".cr-room").first().click().catch(() => {}); await page.waitForTimeout(1200); await nav(/Chat/); await shot("2-chat"); await check("chat");
  // 3 hồ sơ
  await nav(/Hồ sơ|Profile/); if (!mobile) await page.getByRole("tab", { name: /Hồ sơ|Profile/ }).first().click(); await page.waitForTimeout(500); await shot("3-profile"); await check("profile");
  // 4 ví dụ
  await nav(/Ví dụ|Examples/); if (!mobile) await page.getByRole("tab", { name: /Ví dụ|Examples/ }).first().click(); await page.waitForTimeout(700); await shot("4-examples"); await check("examples");
  // 5 test
  await nav(/Test/); if (!mobile) await page.getByRole("tab", { name: /^Test/ }).first().click(); await page.waitForTimeout(700); await shot("5-test"); await check("test");
  await nav(/Chat/);
  // 6 demo
  await page.getByRole("button", { name: /Xem demo|Watch demo/ }).click(); await page.waitForTimeout(700);
  for (let i = 0; i < 4; i++) await page.getByRole("button", { name: /^(Tiếp|Next)/ }).first().click({ timeout: 2000 }).catch(() => {});
  await page.waitForTimeout(400); await shot("6-demo"); await check("demo"); await page.keyboard.press("Escape"); await page.waitForTimeout(300);
  // 7 cách dạy
  await page.getByRole("button", { name: /Cách dạy|How to teach/ }).click(); await page.waitForTimeout(500); await shot("7-guide"); await check("guide"); await page.keyboard.press("Escape"); await page.waitForTimeout(300);
  // 8 mẫu -> điền ô nhập
  await page.getByRole("button", { name: /^(Mẫu|Templates)/ }).click(); await page.waitForTimeout(400); await page.locator(".gd-tpl").nth(1).click(); await shot("8-templates"); await check("templates");
  await page.getByRole("button", { name: /Dùng mẫu này|Use this template/ }).click(); await page.waitForTimeout(500);
  const filled = await page.locator("textarea[aria-label]").first().inputValue().catch(() => "");
  if (!filled || filled.length < 40) res.push({ n: "template-fill", tag, filled: filled.length });
  // 9 tour
  await page.getByRole("button", { name: /Tham quan|Interface tour|Tour/ }).first().click(); await page.waitForTimeout(500); await shot("9-tour1");
  for (let i = 0; i < 4; i++) { await page.getByRole("button", { name: /^(Tiếp|Next)$/ }).click(); await page.waitForTimeout(300); if (i === 3) { await shot("9-tour5"); await check("tour5"); } }
  await page.keyboard.press("Escape");
  } catch (e) { res.push({ n: "EXC", tag, msg: String(e.message).split("\n").slice(0, 3).join(" ") }); await page.screenshot({ path: `${OUT}/fail-${tag}.png` }).catch(() => {}); }
  await ctx.close();
}
await browser.close();
console.log("issues", JSON.stringify(res, null, 1)); console.log("axe", JSON.stringify(axeRes, null, 1)); console.log("errors", JSON.stringify(errs));
process.exit(res.length || errs.length ? 1 : 0);
