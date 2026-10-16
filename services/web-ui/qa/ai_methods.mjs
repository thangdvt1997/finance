// QA màn "Phương pháp" (AI Training Class, master): MOCK=1 chặn /api/v1/ai-trading/class/* bằng fixture (CHỈ trong QA). Kiểm: không tràn ngang, cỡ chạm, axe AA,
// không lộ tên nguồn, biển "CHƯA đủ điều kiện" hiện khi bước 4-6 trượt và KHÔNG có nhãn "sẵn sàng", PUT quan hệ đúng hợp đồng, SSE phòng phương pháp, mở phòng từ sơ đồ. Ảnh vào OUT (ux-m*-...).
import { chromium } from "playwright";
import fs from "node:fs";
const BASE = process.env.BASE || "http://127.0.0.1:8580", OUT = process.env.OUT || "out";
fs.mkdirSync(OUT, { recursive: true });
const now = new Date().toISOString(), A = "a".repeat(32), B = "b".repeat(32), C = "c".repeat(32), MID = "9".repeat(32);
const sc = (id, title, role, score, test, paper) => ({ room_id: id, title, role, added_at: now, clarity: { score, weakest_row: "filters" }, rows_confirmed: 9, labels: { n_examples: 8, n_labeled: 8, precision: 0.81, coverage: 1 }, test, paper });
const scenarios = [
  sc(A, "3 đỉnh giảm dần (Sell)", "core", 84, { verdict: "no_edge", trades: 268, expectancy_r: -0.088, ci95: [-0.2, 0.02], test_opened: true }, { trades: 0, weeks: 0 }),
  sc(B, "Phá đáy nến nén (Sell)", "support", 61, { verdict: "unproven", trades: 118, expectancy_r: 0.04, ci95: [-0.12, 0.2], test_opened: false }, { trades: 12, weeks: 2 }),
  sc(C, "Bản mua đối xứng", "experimental", 35, { verdict: "none" }, { trades: 0, weeks: 0 }),
];
let relations = [{ id: "r1", kind: "priority", a: A, b: B, params: {}, note: "" }, { id: "r2", kind: "mirror", a: A, b: C, params: {}, note: "" }, { id: "r3", kind: "regime", a: B, b: null, params: { regime: "range" }, note: "" }, { id: "r4", kind: "exclusive", a: B, b: C, params: {}, note: "" }];
const meth = { id: MID, name: "Đảo chiều vùng đi ngang", description: "Gom các kịch bản Sell ở vùng đi ngang, ưu tiên bản 3 đỉnh.", owner: "qa", owner_name: "QA Master", version: 3, scenario_count: 3, clarity_avg: 60, plan: { passed: 2, total: 9, verdict: "not_eligible" }, created_at: now, updated_at: now };
const step = (n, key, vi, en, status, crit = [], extra = {}) => ({ n, key, title_vi: vi, title_en: en, status, owner: "master", since: now, criteria: crit, evidence: [], action: null, suggestions: [], ...extra });
const plan = {
  method_id: MID, method_version: 3, computed_at: now, progress: { passed: 2, total: 9 },
  verdict: { code: "not_eligible", label_vi: "CHƯA đủ điều kiện áp dụng", label_en: "NOT yet eligible for application", reasons: ["Bước 4: kỳ vọng sau chi phí = -0,088R, CI95 dưới < 0"], paper_only: true, note_vi: "Chỉ nghiên cứu/paper; vốn thật cần cổng pháp lý G1-G3." },
  steps: [
    step(1, "clarity", "Ý tưởng đủ rõ", "Idea is clear enough", "passed", [{ id: "c", label_vi: "Độ rõ >= 80", label_en: "Clarity >= 80", required: ">= 80", actual: "84", pass: true }]),
    step(2, "formalize", "Hình thức hoá", "Formalised", "passed"),
    step(3, "scan", "Quét + nhãn", "Scan + labels", "pending", [{ id: "p", label_vi: "Độ chính xác nhãn >= 0,70", label_en: "Label precision >= 0.70", required: ">= 0,70", actual: "0,81", pass: true }, { id: "n", label_vi: "Số nhãn >= 12", label_en: "Labels >= 12", required: ">= 12", actual: "8", pass: false }], { action: { kind: "open_room", label_vi: "Làm bước này", room_id: A } }),
    step(4, "backtest", "Backtest trung thực", "Honest backtest", "failed", [{ id: "exp_pos", label_vi: "Kỳ vọng sau chi phí > 0", label_en: "Expectancy after costs > 0", required: "> 0", actual: "-0,088", pass: false }], { evidence: [{ kind: "result", label: "Kết quả walk-forward", room_id: A, value: "n=268, exp -0,088R" }], suggestions: ["Không có edge sau chi phí: làm rõ ý tưởng, đổi khung/mã, thêm bộ lọc hoặc dừng."], action: { kind: "run_test", label_vi: "Làm bước này", room_id: A } }),
    step(5, "stability", "Ổn định", "Stability", "pending"), step(6, "guardrail", "Guardrail", "Guardrails", "pending"), step(7, "paper", "Paper", "Paper", "pending"), step(8, "approval", "Master duyệt", "Master approval", "blocked"), step(9, "export", "Xuất tài liệu", "Export", "pending"),
  ],
};
const rows = ["context", "priority", "risk_per_trade", "hot_risk", "loss_limits", "correlation", "stop_rules", "symbols_tf", "roles"].map((k, i) => ({ key: k, title_vi: ["Bối cảnh", "Ưu tiên", "Rủi ro mỗi lệnh", "Rủi ro nóng", "Giới hạn lỗ", "Tương quan", "Quy tắc dừng", "Mã & khung", "Vai trò"][i], title_en: ["Context", "Priority", "Risk per trade", "Hot risk", "Loss limits", "Correlation", "Stop rules", "Symbols & TF", "Roles"][i], text: i < 4 ? ["Vùng đi ngang rõ, H1", "3 đỉnh trước", "0,5% vốn mô phỏng", "Tối đa 2%"][i] : "", confidence: i < 4 ? "cao" : "trống", quantified: i >= 2 && i < 4, confirmed: i < 2, source: { author: "QA Master", turn: i + 1 }, editable: true }));
const canvas = { rows, clarity: { score: 40, breakdown: {}, weakest_row: "loss_limits", next_question: "Giới hạn lỗ ngày/tuần là bao nhiêu?" }, scenarios_overview: [], method_version: 3 };
const AI = { role: "ai", name: "AI học trò" }, ME = { role: "user", name: "QA Master" };
const msgs0 = { id: "1", seq: 1, kind: "text", author: AI, text: "Mình hỏi về **bối cảnh**: khi nào dùng phương pháp này?", chips: [{ label: "Chỉ khi đi ngang", text: "Chỉ dùng khi thị trường đi ngang" }, { label: "Bỏ qua câu này", text: "bỏ qua" }], data: null, created_at: now };
let msgs = [msgs0];
const sse = (evs) => evs.map((e) => `data: ${JSON.stringify(e)}\n\n`).join("");
const puts = [];
async function mock(ctx) {
  msgs = [msgs0];
  const json = (route, body, status = 200) => route.fulfill({ status, contentType: "application/json", body: JSON.stringify(body) });
  await ctx.route(/\/api\/v1\/ai-trading\/class\//, async (route) => {
    const u = new URL(route.request().url()), p = u.pathname.replace("/api/v1/ai-trading/class", ""), m = route.request().method();
    if (p === "/methods" && m === "GET") return json(route, { items: [meth], total: 1 });
    if (p === `/methods/${MID}` && m === "GET") return json(route, { ...meth, scenarios, relations, profile: { clarity: { score: 40 }, version: 3 }, plan: meth.plan });
    if (p.endsWith("/relations") && m === "GET") return json(route, { relations, graph: {}, warnings: [], kinds: [] });
    if (p.endsWith("/relations") && m === "PUT") { puts.push(JSON.parse(route.request().postData() || "{}")); return json(route, { relations, warnings: ["Ví dụ cảnh báo"] }); }
    if (p.endsWith("/canvas")) return json(route, canvas);
    if (p.endsWith("/plan") && m === "GET") return json(route, plan);
    if (p.endsWith("/messages") && m === "GET") return json(route, { items: msgs, has_more: false, next_row: "priority" });
    if (p.endsWith("/messages") && m === "POST") {
      msgs = [...msgs, { id: "2", seq: 2, kind: "text", author: ME, text: "Chỉ dùng khi đi ngang", chips: [], created_at: now }, { id: "3", seq: 3, kind: "text", author: AI, text: "Ghi nhận. Khi 2 tín hiệu cùng lúc thì bản nào đi trước?", chips: [{ label: "Bản 3 đỉnh", text: "Bản 3 đỉnh đi trước" }], created_at: now }];
      return route.fulfill({ status: 200, contentType: "text/event-stream", body: sse([{ type: "user", message: msgs[1] }, { type: "delta", text: "Ghi nhận. " }, { type: "turn", message: msgs[2], turn: { row: "context", recorded: true } }, { type: "done" }]) });
    }
    if (/\/rooms$/.test(p)) return json(route, { items: [], llm: {} });
    return json(route, { detail: "mock: chưa có" }, 404);
  });
}
const browser = await chromium.launch();
const res = [], errs = [], axeRes = [];
const sizes = process.env.SIZES ? process.env.SIZES.split(",").map((x) => [+x, 900]) : [[375, 800], [768, 1000], [1366, 900], [1920, 1000]];
const SHOT = process.env.SHOT !== "0";
let axeSrc = ""; try { axeSrc = fs.readFileSync("node_modules/axe-core/axe.min.js", "utf8"); } catch { /* không có axe */ }
for (const [w, h] of sizes) for (const th of ["dark", "light"]) for (const lang of (w === 1366 ? ["vi", "en"] : ["vi"])) {
  const ctx = await browser.newContext({ viewport: { width: w, height: h }, colorScheme: th, baseURL: BASE });
  await ctx.request.post(`${BASE}/auth/login`, { data: { platform: "master", login: process.env.QA_USER, secret: process.env.QA_PASS }, headers: { Origin: BASE, "Content-Type": "application/json" } });
  await ctx.addInitScript(([t, l]) => { try { const v = JSON.parse(localStorage.getItem("ts-ux") || "{}"); v.onboarded = 99; v.theme = t; localStorage.setItem("ts-ux", JSON.stringify(v)); localStorage.setItem("ts-theme", t); localStorage.setItem("ts-aitrading-lang", l); localStorage.setItem("cr-tour-done", "1"); sessionStorage.removeItem("ai.tab"); localStorage.removeItem("cm-sel"); } catch { /* bỏ */ } }, [th, lang]);
  await mock(ctx);
  await ctx.route(/\/api\/v1\/user\/prefs/, (route) => route.request().method() === "GET" ? route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ rev: 1, prefs: { theme: th } }) }) : route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ rev: 2 }) }));
  const page = await ctx.newPage(); page.setDefaultTimeout(15000);
  page.on("pageerror", (e) => errs.push(`${w}${th}: ${String(e.message).slice(0, 200)}`));
  page.on("console", (m) => { if (m.type() === "error" && !/Failed to load resource/.test(m.text())) errs.push(`${w}${th}: ${m.text().slice(0, 200)}`); });
  const tag = `${w}-${th}-${lang}`, shot = async (n) => { if (SHOT) await page.screenshot({ path: `${OUT}/ux-${n}-${tag}.png` }); };
  const check = async (n) => {
    const info = await page.evaluate(() => {
      const R = (e) => e.getBoundingClientRect(), vis = (e) => { const r = R(e); return r.width > 0 && r.height > 0 && getComputedStyle(e).visibility !== "hidden"; };
      const root = document.querySelector(".cm") || document.body;
      return {
        overflow: document.documentElement.scrollWidth - innerWidth,
        off: [...root.querySelectorAll("*")].filter((e) => vis(e) && R(e).right > innerWidth + 1 && !e.closest("table,.cm-scroll,.cm-tabs,svg,pre,code")).slice(0, 3).map((e) => String(e.className?.baseVal ?? e.className).slice(0, 40)),
        small: [...root.querySelectorAll("button,a.btn,input:not([type=checkbox]),select,[role=tab]")].filter((e) => vis(e) && !e.closest("[aria-hidden=true],.cr-canvas,.cm-chat > div:last-child") && R(e).height < 38).slice(0, 4).map((e) => `${e.tagName}:${(e.textContent || e.getAttribute("aria-label") || "").trim().slice(0, 24)}:${Math.round(R(e).height)}`),
        wide: [...document.querySelectorAll(".cm *")].filter((e) => vis(e) && R(e).right > innerWidth + 1).slice(0, 6).map((e) => `${e.tagName}.${String(e.className?.baseVal ?? e.className).slice(0, 30)}:${Math.round(R(e).right)}`),
        dbg: ["table.cm-tbl", "svg.cm-svg", ".cm-tabs", ".cm-warn", ".cm-opts"].map((q) => { const els = [...document.querySelectorAll(`.cm ${q}`)]; const old = els.map((e) => e.style.display); els.forEach((e) => { e.style.display = "none"; }); const w = document.documentElement.scrollWidth - innerWidth; els.forEach((e, i) => { e.style.display = old[i]; }); return `${q}:${els.length}:${w}`; }),
        leak: /binance|yahoo|metaquotes|twelve|dukascopy|openai/i.test(document.body.innerText),
      };
    });
    if (info.overflow > 0 || info.off.length || info.small.length || info.leak) res.push({ n, tag, ...info });
    if (axeSrc) { await page.evaluate(axeSrc); const v = await page.evaluate(async () => { const r = await axe.run(".cm", { runOnly: ["wcag2a", "wcag2aa"], resultTypes: ["violations"] }); return r.violations.map((x) => `${x.id}:${x.nodes.length}:${(x.nodes[0]?.html || "").slice(0, 90)}`); }); if (v.length) axeRes.push({ n, tag, v }); }
  };
  try {
    await page.goto(`${BASE}/#/ai-trading`, { waitUntil: "load" });
    await page.getByRole("tab", { name: /^(Phương pháp|Methods)$/ }).first().click();
    await page.waitForSelector(".cm-item", { timeout: 15000 });
    await shot("m1-list"); await check("list");
    await page.locator(".cm-item").first().click(); await page.waitForSelector("svg.cm-svg"); await page.waitForTimeout(400);
    await shot("m2-overview"); await check("overview");
    const txt0 = await page.locator(".cm").innerText();
    if (!/CHƯA đủ điều kiện|NOT yet eligible/.test(txt0)) res.push({ n: "verdict-missing", tag });
    if (/sẵn sàng|ready to (trade|apply)/i.test(txt0)) res.push({ n: "ready-label-present", tag });
    await page.locator(".cm").getByRole("tab", { name: /Quy tắc|Rules/ }).click(); await page.waitForTimeout(400); await shot("m3-rules"); await check("rules");
    if (w >= 768) { await page.getByRole("button", { name: /Lưu|Save/ }).first().isDisabled(); }
    await page.locator("input[maxlength='200']").first().fill("Ghi chú QA"); await page.getByRole("button", { name: /^(Lưu|Save)$/ }).click(); await page.waitForTimeout(500);
    if (!puts.length || !puts.at(-1).relations?.some((r) => r.kind === "regime" && r.b === null && r.params?.regime === "range")) res.push({ n: "put-shape", tag, put: JSON.stringify(puts.at(-1) || null).slice(0, 200) });
    await page.locator(".cm").getByRole("tab", { name: /Phòng phương pháp|Method room/ }).click(); await page.waitForSelector(".cm-chat"); await page.waitForTimeout(500);
    await shot("m4-room"); await check("room");
    await page.getByRole("button", { name: /Chỉ khi đi ngang/ }).click(); await page.waitForTimeout(900);
    if (!(await page.locator(".cm-chat").innerText()).includes("bản nào đi trước")) res.push({ n: "sse-turn-missing", tag });
    await page.locator(".cm").getByRole("tab", { name: /Kế hoạch áp dụng|Application plan/ }).click(); await page.waitForTimeout(500); await shot("m5-plan"); await check("plan");
    const ptxt = await page.locator(".cm").innerText();
    if (!/TRƯỢT|FAILED/.test(ptxt) || !/-0,088/.test(ptxt)) res.push({ n: "plan-facts-missing", tag });
    await page.locator(".cm").getByRole("tab", { name: /Tổng quan|Overview/ }).click(); await page.waitForSelector("svg.cm-svg");
    await page.locator("svg.cm-svg .cm-node").first().focus(); await page.keyboard.press("Enter"); await page.waitForTimeout(900);
    if (!(await page.getByRole("tab", { name: /AI Training Class/ }).first().getAttribute("aria-selected").catch(() => "")) === "true") res.push({ n: "open-room-nav", tag });
    const stored = await page.evaluate(() => localStorage.getItem("cr-room")); if (stored !== "a".repeat(32)) res.push({ n: "open-room-stored", tag, stored });
  } catch (e) { res.push({ n: "EXC", tag, msg: String(e.message).split("\n").slice(0, 3).join(" ") }); await page.screenshot({ path: `${OUT}/fail-m-${tag}.png` }).catch(() => {}); }
  await ctx.close();
}
await browser.close();
console.log("issues", JSON.stringify(res, null, 1)); console.log("axe", JSON.stringify(axeRes, null, 1)); console.log("errors", JSON.stringify(errs));
process.exit(res.length || errs.length ? 1 : 0);
