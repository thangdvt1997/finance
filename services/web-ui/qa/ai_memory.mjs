// QA "Bộ nhớ của AI" (master, MOCK): chặn /api/v1/ai-trading/class/* bằng fixture (CHỈ trong QA). Kiểm: không tràn ngang, cỡ chạm, axe AA, không lộ tên nguồn,
// thẻ xác nhận trong chat [Đúng][Sửa][Đừng nhớ], toast "Đã ghi nhớ 2 điều", chỉ báo "Mình nhớ lần trước bạn nói", mâu thuẫn, thống kê, xuất JSON. Ảnh JPEG nhỏ vào OUT.
import { chromium } from "playwright";
import fs from "node:fs";
const BASE = process.env.BASE || "http://127.0.0.1:8580", OUT = process.env.OUT || "out";
fs.mkdirSync(OUT, { recursive: true });
const now = new Date().toISOString();
const au = (id, name, role) => ({ user_id: id, name, role });
const ME = au("qa", "QA Master", "master"), AI = au("ai", "AI học trò", "ai");
const M = (seq, author, text, extra = {}) => ({ id: `m${seq}`, seq, room_id: "r1", kind: "text", author, text, created_at: now, pinned: false, attachments: [], data: null, review: null, understanding: null, chips: [], ...extra });
const msgs = [M(1, ME, "SL của mình là 1 ATR trên đỉnh nhịp."), M(2, AI, "Mình nhớ lần trước bạn nói SL đặt trên đỉnh nhịp 1 ATR. Áp dụng cho kịch bản này không?", { data: { memory_used: [{ id: "m_a1", text: "SL đặt trên đỉnh nhịp 1 ATR", status: "confirmed" }, { id: "m_a2", text: "Khung chính H1", status: "proposed" }] } })];
const room = { id: "r1", title: "Nhấn chìm bóng trên EURUSD", created_at: now, updated_at: now, members: [{ ...ME, joined_at: now }, { user_id: "ex1", name: "Anh Minh", role: "expert", joined_at: now }], phase: "interview", step: 3, profile_version: 2, msg_count: 2, last_message: { author: AI, text: msgs[1].text, created_at: now } };
const item = (id, type, text, o = {}) => ({ id, type, type_label: type, topic: "sl", content: { text }, room_id: "r1", room_title: room.title, room_deleted: false, scope: "scenario", author: au("qa", "QA Master", "master"), source: { room_id: "r1", message_id: "m1", excerpt: "SL của mình là 1 ATR trên đỉnh nhịp.", kind: "chat" }, importance: "critical", confidence: 0.7, status: "proposed", confirm_count: 0, created_at: now, updated_at: now, use_count: 3, last_used_at: now, version: 1, is_current: true, pinned: false, locked: false, conflict_id: null, can_edit: true, can_moderate: true, ...o });
let ITEMS = [
  item("m_a1", "knowledge", "SL đặt trên đỉnh nhịp 1 ATR", { status: "confirmed", confidence: 0.9, pinned: true }),
  item("m_a2", "knowledge", "Khung chính H1, khung xác nhận M15", { topic: "symbol_tf", importance: "minor" }),
  item("m_a3", "lesson", "Trước đây AI hiểu bóng trên 30%, chuyên gia sửa thành 40% thân vì lọc nhiễu", { topic: "formation", status: "confirmed", version: 2 }),
  item("m_a4", "term", "nhịp hồi = pullback", { topic: "general", scope: "expert", importance: "minor", status: "confirmed", room_id: null, room_title: null }),
  item("m_a5", "test_result", "Walk-forward 2023-2025: kỳ vọng -0,12R, không hơn ngẫu nhiên (p=0,41)", { topic: "general", status: "confirmed", confidence: 0.95 }),
  item("m_a6", "preference", "Thích câu trả lời ngắn, có số liệu", { topic: "general", importance: "minor", conflict_id: "c1" }),
];
const CONF = [{ id: "c1", status: "open", topic: "sl", room_id: "r1", question: "Hai bản ghi về SL khác nhau, bản nào đúng cho kịch bản này?", a: ITEMS[0], b: item("m_b1", "knowledge", "SL đặt dưới đáy nến tín hiệu 0,5 ATR", { author: au("ex1", "Anh Minh", "expert"), conflict_id: "c1" }), created_at: now }];
const STATS = { total: 6, confirmed: 4, proposed: 2, rejected: 0, revoked: 0, conflicts_open: 1, by_type: { knowledge: 2, lesson: 1, term: 1, test_result: 1, preference: 1 }, sessions: 3, learned_from_sessions: "AI đã học 4 điều từ 3 buổi", rooms_covered: [{ room_id: "r1", title: room.title, rows_known: 9, rows_total: 14, coverage: 0.64 }, { room_id: "r2", title: "Sóng hồi 61.8% XAUUSD", rows_known: 2, rows_total: 14, coverage: 0.14 }], avg_confidence: 0.77, repeat_questions_avoided: 7, retrieval: { engine: "bm25+ngram", budget_tokens: 600 } };
const OPT = { mine: { kinds: [{ kind: "variant", label: "biến thể", p_accept: 0.72, events: 9, clicked: 7 }, { kind: "question", label: "câu hỏi tiếp theo", p_accept: 0.35, events: 12, clicked: 3 }], total: 21 }, class: { kinds: [{ kind: "variant", label: "biến thể", p_accept: 0.6, events: 20, clicked: 12 }, { kind: "question", label: "câu hỏi tiếp theo", p_accept: 0.4, events: 30, clicked: 10 }], total: 50 }, weights: {} };
const CARDS = [{ id: "m_n1", kind: "confirm", text: "Mình ghi nhớ: Điều kiện huỷ là giá đóng cửa trên đỉnh nhịp. Đúng không?", actions: ["confirm", "edit", "reject"], labels: { confirm: "Đúng", edit: "Sửa", reject: "Đừng nhớ" } }, { id: "m_n2", kind: "confirm", text: "Mình ghi nhớ: TP 2R. Đúng không?", actions: ["confirm", "edit", "reject"], labels: { confirm: "Đúng", edit: "Sửa", reject: "Đừng nhớ" } }];
const sse = (evs) => evs.map((e) => `data: ${JSON.stringify(e)}\n\n`).join("");
const KEYS = ["context", "symbol_tf", "formation", "trigger", "invalidation", "sl", "tp", "sizing", "filters", "ex_ok", "ex_bad", "failure", "symmetry", "rationale", "assumptions", "open_questions"];
const CANVAS = { rows: KEYS.map((key) => ({ key, title_vi: key, title_en: key, text: "", confidence: "trống", source: { author: "", turn: 0 }, confirmed: false, quantified: false, has_examples: false, ai_understanding: "", editable: true })), clarity: { score: 10, breakdown: {}, weakest_row: "context", next_question: "Bối cảnh lớn là gì?" }, profile_version: 2 };
const calls = [];
async function mock(ctx) {
  const json = (route, body, status = 200) => route.fulfill({ status, contentType: "application/json", body: JSON.stringify(body) });
  await ctx.route(/\/api\/v1\/ai-trading\/class\//, async (route) => {
    const req = route.request(), u = new URL(req.url()), p = u.pathname.replace("/api/v1/ai-trading/class", ""), m = req.method();
    if (m !== "GET") calls.push(`${m} ${p}`);
    if (p === "/rooms" && m === "GET") return json(route, { items: [room, { ...room, id: "r2", title: "Sóng hồi 61.8% XAUUSD", phase: "intake", profile_version: null, last_message: null, members: [ME] }], llm: { provider: "local", enabled: true } });
    if (/^\/rooms\/r1$/.test(p)) return json(route, { room, messages: msgs, pinned: [], chips: [], state: { phase: "interview", step: 3, idx: 3, total: 13 }, labels_summary: {}, pending_actions: [], has_more: false });
    if (/^\/rooms\/r2$/.test(p)) return json(route, { room: { ...room, id: "r2" }, messages: [], pinned: [], chips: [], state: {}, labels_summary: {}, pending_actions: [], has_more: false });
    if (/\/messages$/.test(p) && m === "POST") return route.fulfill({ status: 200, headers: { "content-type": "text/event-stream" }, body: sse([{ type: "user", message: M(90, ME, "Điều kiện huỷ là giá đóng cửa trên đỉnh nhịp, TP 2R") }, { type: "delta", text: "Ghi nhận." }, { type: "turn", message: M(91, AI, "Ghi nhận. Mình nhớ SL bạn nói là 1 ATR.", {}), turn: { questions: [], memory_used: [{ id: "m_a1", text: "SL đặt trên đỉnh nhịp 1 ATR", status: "confirmed" }] } }, { type: "memory", notice: "Đã ghi nhớ 2 điều", cards: CARDS, created: ["m_n1", "m_n2"] }, { type: "done" }]) });
    if (/\/canvas$/.test(p)) return json(route, CANVAS);
    if (/\/labels$/.test(p)) return json(route, { items: [], summary: {} });
    if (/\/profile$/.test(p)) return json(route, { profile: { name: "KB-QA", version: 2, answers: {}, open_questions: [], assumptions: [], contributors: [], labels: [] }, understanding: {}, versions: [] });
    if (p === "/memory/conflicts") return json(route, { items: CONF, total: 1 });
    if (p === "/memory/stats") return json(route, STATS);
    if (p === "/options/stats") return json(route, OPT);
    if (p === "/memory/export") return json(route, { version: 1, exported_at: now, items: ITEMS, conflicts: [] });
    if (p === "/memory/import") return json(route, { imported: 2, skipped: [{ index: 1, reason: "injection" }], merged: 0 });
    if (p === "/memory" && m === "GET") {
      const q = u.searchParams; let it = ITEMS.filter((x) => (!q.get("type") || x.type === q.get("type")) && (!q.get("status") || x.status === q.get("status")) && (!q.get("q") || x.content.text.toLowerCase().includes(q.get("q").toLowerCase())));
      return json(route, { items: it, total: it.length, limit: 100, offset: 0, facets: { type: Object.fromEntries(Object.keys({ knowledge: 1, lesson: 1, term: 1 }).map((k) => [k, ITEMS.filter((x) => x.type === k).length])), status: {} } });
    }
    let mm = /^\/memory\/(m_\w+)$/.exec(p);
    if (mm && m === "GET") { const it = ITEMS.find((x) => x.id === mm[1]) || ITEMS[0]; return json(route, { item: it, history: [{ id: 1, memory_id: it.id, event: "extract", by: { user_id: "ai", name: "AI", role: "ai" }, at: now, detail: "trích từ chat" }, { id: 2, memory_id: it.id, event: "edit", by: { user_id: "qa", name: "QA Master", role: "master" }, at: now, before: "SL 0,5 ATR", after: it.content.text }], versions: [it], source_message: { id: "m1", author: { name: "QA Master" }, text: "SL của mình là 1 ATR trên đỉnh nhịp.", created_at: now } }); }
    mm = /^\/memory\/(m_\w+)\/(confirm|reject|pin)$/.exec(p);
    if (mm && m === "POST") { const it = ITEMS.find((x) => x.id === mm[1]); if (it) { if (mm[2] === "confirm") it.status = "confirmed"; if (mm[2] === "reject") it.status = "rejected"; if (mm[2] === "pin") it.pinned = JSON.parse(req.postData() || "{}").pinned; } return json(route, { item: it || ITEMS[0] }); }
    if (mm = /^\/memory\/(m_\w+)$/.exec(p), mm && (m === "PATCH" || m === "DELETE")) return json(route, m === "DELETE" ? { ok: true, id: mm[1] } : { item: ITEMS[0], previous: ITEMS[0] });
    if (/^\/memory\/conflicts\/c1\/resolve$/.test(p)) { CONF.length = 0; return json(route, { conflict: {}, items: [] }); }
    return json(route, { detail: "mock: chưa có" }, 404);
  });
}

const browser = await chromium.launch();
const res = [], errs = [], axeRes = [];
let storage = null;
const sizes = process.env.SIZES ? process.env.SIZES.split(",").map((x) => [+x, 900]) : [[375, 800], [768, 1000], [1366, 900], [1920, 1000]];
let axeSrc = ""; try { axeSrc = fs.readFileSync("node_modules/axe-core/axe.min.js", "utf8"); } catch { /* không có axe */ }
for (const [w, h] of sizes) for (const th of ["dark", "light"]) for (const lang of (w === 1366 ? ["vi", "en"] : ["vi"])) {
  const ctx = await browser.newContext({ viewport: { width: w, height: h }, colorScheme: th, baseURL: BASE, acceptDownloads: true, ...(storage ? { storageState: storage } : {}) });
  if (!storage) { const lr = await ctx.request.post(`${BASE}/auth/login`, { data: { platform: "master", login: process.env.QA_USER, secret: process.env.QA_PASS }, headers: { Origin: BASE, "Content-Type": "application/json" } }); console.log("login", lr.status(), (await lr.text()).slice(0, 120)); storage = await ctx.storageState(); }   // đăng nhập 1 lần (tránh giới hạn tần suất)
  await ctx.addInitScript(([t, l]) => { try { const v = JSON.parse(localStorage.getItem("ts-ux") || "{}"); v.onboarded = 99; v.theme = t; localStorage.setItem("ts-ux", JSON.stringify(v)); localStorage.setItem("ts-theme", t); localStorage.setItem("ts-aitrading-lang", l); localStorage.setItem("cr-tour-done", "1"); localStorage.setItem("cr-room", "r1"); } catch {} }, [th, lang]);
  await mock(ctx);
  await ctx.route(/\/api\/v1\/user\/prefs/, (route) => route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ rev: 1, prefs: { theme: th } }) }));
  const page = await ctx.newPage(); page.setDefaultTimeout(15000);
  page.on("pageerror", (e) => errs.push(`${w}${th}: ${String(e.message).slice(0, 200)}`));
  page.on("console", (m) => { if (m.type() === "error" && !/Failed to load resource/.test(m.text())) errs.push(`${w}${th}: ${m.text().slice(0, 200)}`); });
  for (let k = 0; k < 6; k++) { try { await page.goto(`${BASE}/#/ai-trading`, { waitUntil: "load" }); break; } catch (e) { if (k === 5) throw e; await page.waitForTimeout(8000); } }   // chịu deploy của agent khác
  await page.getByRole("tab", { name: /AI Training Class/ }).first().click().catch(() => {});
  await page.waitForTimeout(1800);
  const mobile = w < 1180, tag = `${w}-${th}-${lang}`, vi = lang === "vi";
  const shot = async (n) => { await page.screenshot({ path: `${OUT}/mem-${n}-${tag}.jpg`, type: "jpeg", quality: 55 }); };
  const check = async (n) => {
    const info = await page.evaluate(([mobile]) => {
      const R = (e) => e.getBoundingClientRect();
      const vis = (e) => { const r = R(e); return r.width > 0 && r.height > 0 && getComputedStyle(e).visibility !== "hidden"; };
      return {
        overflow: document.documentElement.scrollWidth - innerWidth,
        off: [...document.querySelectorAll(".mem *,.mem-card *,.mem-used *")].filter((e) => vis(e) && R(e).right > innerWidth + 1 && !e.closest("table,pre,code")).slice(0, 3).map((e) => String(e.className).slice(0, 40)),
        small: [...document.querySelectorAll(".mem button,.mem input:not([type=checkbox]):not([hidden]),.mem select,.mem-card button,.mem-used button")].filter((e) => vis(e) && (R(e).height < 38 || R(e).width < 38)).slice(0, 3).map((e) => `${e.tagName}:${(e.innerText || e.getAttribute("aria-label") || "").slice(0, 20)}:${Math.round(R(e).height)}`),
        leak: /binance|yahoo|metaquotes|twelve|dukascopy|openai/i.test(document.body.innerText),
      };
    }, [mobile]);
    if (info.overflow > 0 || info.off.length || info.small.length || info.leak) res.push({ n, tag, ...info });
    if (axeSrc) { await page.evaluate(axeSrc); const v = await page.evaluate(async () => { const r = await axe.run(".cr", { runOnly: ["wcag2a", "wcag2aa"], resultTypes: ["violations"] }); return r.violations.map((x) => `${x.id}:${x.nodes.length}:${(x.nodes[0]?.html || "").slice(0, 90)}`); }); if (v.length) axeRes.push({ n, tag, v }); }
  };
  try {
    // 1 chat: gửi tin -> toast + thẻ xác nhận + chỉ báo "Mình nhớ"
    if (mobile && !(await page.locator(".cr-nav").isVisible().catch(() => false))) throw new Error("no nav");
    if (mobile) await page.locator(".cr-nav button").filter({ hasText: /Chat/ }).click();
    await page.waitForTimeout(500);
    const used = page.locator(".mem-used-b").first();
    if (!(await used.isVisible().catch(() => false))) res.push({ n: "used-chip-missing", tag });
    await used.click(); await page.waitForTimeout(200);
    if (!(await page.getByRole("button", { name: /Xem \/ sửa nguồn|View \/ edit source/ }).first().isVisible().catch(() => false))) res.push({ n: "used-open-missing", tag });
    await shot("1-used"); await check("used");
    await used.click();
    const ta = page.locator("textarea[aria-label]").first();
    await ta.fill("Điều kiện huỷ là giá đóng cửa trên đỉnh nhịp, TP 2R"); await ta.press("Enter").catch(() => {});
    await page.getByRole("button", { name: /^(Gửi|Send)/ }).first().click({ timeout: 1500 }).catch(() => {});
    await page.waitForTimeout(1500);
    if (!(await page.getByText(/Đã ghi nhớ 2 điều/).first().isVisible().catch(() => false))) res.push({ n: "toast-missing", tag });
    const dung = page.getByRole("button", { name: vi ? /^Đúng/ : /^Right/ }).first();
    if (!(await dung.isVisible().catch(() => false))) res.push({ n: "confirm-card-missing", tag });
    await shot("2-card"); await check("card");
    await dung.click(); await page.waitForTimeout(400);
    if (!calls.some((c) => /POST \/memory\/m_n1\/confirm/.test(c))) res.push({ n: "confirm-not-posted", tag });
    await page.getByRole("button", { name: vi ? /^Đừng nhớ/ : /^Do not remember/ }).first().click(); await page.waitForTimeout(400);
    if (!calls.some((c) => /POST \/memory\/m_n2\/reject/.test(c))) res.push({ n: "reject-not-posted", tag });
    // 2 panel
    if (mobile) { await page.locator(".cr-nav button").filter({ hasText: /Hồ sơ|Profile/ }).click(); }
    await page.getByRole("tab", { name: vi ? /^Bộ nhớ/ : /^Memory/ }).first().click(); await page.waitForTimeout(700);
    await shot("3-list"); await check("list");
    await page.getByRole("searchbox").first().fill("SL"); await page.waitForTimeout(700);
    await page.getByRole("button", { name: vi ? /Nguồn & nhật ký/ : /Source & log/ }).first().click(); await page.waitForTimeout(700);
    if (!(await page.locator(".mem-src").first().isVisible().catch(() => false))) res.push({ n: "source-missing", tag });
    await shot("4-detail"); await check("detail");
    await page.getByRole("button", { name: vi ? /^Ghim|^Bỏ ghim/ : /^Pin|^Unpin/ }).nth(1).click().catch(() => {});
    await page.getByRole("button", { name: vi ? /^Sửa/ : /^Edit/ }).first().click(); await page.waitForTimeout(300); await shot("5-edit"); await check("edit");
    await page.getByRole("button", { name: vi ? /^Huỷ/ : /^Cancel/ }).first().click();
    await page.getByRole("searchbox").first().fill("");
    // xuất JSON
    const dl = page.waitForEvent("download", { timeout: 4000 }).catch(() => null);
    await page.getByRole("button", { name: vi ? /Xuất JSON/ : /Export JSON/ }).click(); const d = await dl; if (!d) res.push({ n: "export-no-download", tag });
    // 3 mâu thuẫn
    await page.getByRole("tab", { name: /Mâu thuẫn|Conflicts/ }).click(); await page.waitForTimeout(600); await shot("6-conflicts"); await check("conflicts");
    // 4 thống kê
    await page.getByRole("tab", { name: /Thống kê|Stats/ }).click(); await page.waitForTimeout(600);
    if (!(await page.getByText(vi ? /AI đã học 4 điều từ 3 buổi/ : /learned 4 things from 3 sessions/).first().isVisible().catch(() => false))) res.push({ n: "stats-headline", tag });
    await shot("7-stats"); await check("stats");
  } catch (e) { res.push({ n: "EXC", tag, msg: String(e.message).split("\n").slice(0, 3).join(" ") }); await page.screenshot({ path: `${OUT}/fail-mem-${tag}.jpg`, type: "jpeg", quality: 50 }).catch(() => {}); }
  await ctx.close();
}
await browser.close();
console.log("issues", JSON.stringify(res, null, 1)); console.log("axe", JSON.stringify(axeRes, null, 1)); console.log("errors", JSON.stringify(errs));
process.exit(res.length || errs.length ? 1 : 0);
