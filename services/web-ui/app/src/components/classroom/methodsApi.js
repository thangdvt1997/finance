// Lớp API "Phương pháp" (AI Training Class, tầng trên phòng kịch bản). Hợp đồng: docs/handoff/METHOD_API.md (+ CLASS_ROUTES_PLAN.md).
// Mọi bộ chuẩn hoá (norm*) nhận dữ liệu lỏng lẻo: thiếu trường -> giá trị mặc định, KHÔNG bịa số. Chỉ nghiên cứu/paper.
import { api, apiWrite, ApiError, getCsrf } from "../../lib/api";
import { readSSE } from "./sse";

const B = "/ai-trading/class";
export const mget = (path, params, signal) => api(`${B}${path}`, params || {}, signal);
export const mwrite = (method, path, body) => apiWrite(method, `${B}${path}`, body ?? {}, { maxBytes: 1_000_000 });
export const enc = encodeURIComponent;

/** Loại quan hệ giữa kịch bản: [khoá, vi, en, mô tả vi, mô tả en, có hướng?, cần B?] (khoá khớp METHOD_API.md) */
export const REL_KINDS = [
  ["exclusive", "Loại trừ", "Mutually exclusive", "Không chạy cùng lúc: tín hiệu này có thì bỏ tín hiệu kia.", "Never run together: when one fires the other is skipped.", false, true],
  ["complementary", "Bổ trợ", "Complementary", "Hai kịch bản củng cố/ xác nhận lẫn nhau.", "The two scenarios reinforce/confirm each other.", false, true],
  ["priority", "Ưu tiên", "Priority", "Khi cùng có tín hiệu, A được xét trước B (không tạo vòng).", "When both fire, A is considered before B (no cycles).", true, true],
  ["regime", "Chỉ trong regime", "Regime only", "A chỉ chạy khi thị trường ở trạng thái đã chọn (xu hướng, đi ngang, biến động...).", "A runs only in the chosen market regime (trend, range, volatility...).", false, false],
  ["mirror", "Đối xứng mua/bán", "Buy/sell mirror", "B là bản đối xứng của A (mua <-> bán); mỗi kịch bản tối đa 1 bản.", "B mirrors A (buy <-> sell); at most one per scenario.", false, true],
  ["timeframe", "Khung xác nhận", "Confirmation timeframe", "A là khung chính, B là khung xác nhận.", "A is the main timeframe, B the confirming one.", true, true],
];
export const REL_BY = Object.fromEntries(REL_KINDS.map((k) => [k[0], k]));
export const REGIMES = [["trend", "Xu hướng", "Trend"], ["range", "Đi ngang", "Range"], ["high_vol", "Biến động cao", "High volatility"], ["low_vol", "Biến động thấp", "Low volatility"]];
export const ROLES = [["core", "Cốt lõi", "Core"], ["support", "Hỗ trợ", "Support"], ["filter", "Bộ lọc", "Filter"], ["experimental", "Thử nghiệm (không tính vào điều kiện)", "Experimental (not counted)"]];
export const roleLabel = (r, en) => { const x = ROLES.find((v) => v[0] === r); return x ? (en ? x[2] : x[1]) : r || ""; };

/** Tên + mô tả mặc định của 9 bước (backend trả title_vi/en; đây chỉ là dự phòng). */
export const PLAN_STEPS = [
  ["clarity", "Ý tưởng đủ rõ", "Idea is clear enough"], ["formalize", "Hình thức hoá thành luật máy", "Formalised as machine rules"], ["scan", "Quét lịch sử + nhãn chuyên gia", "History scan + expert labels"],
  ["backtest", "Backtest trung thực", "Honest backtest"], ["stability", "Ổn định theo mã/ khung/ năm", "Stability across symbols/timeframes/years"], ["guardrail", "Guardrail rủi ro + stress", "Risk guardrails + stress"],
  ["paper", "Paper forward-test", "Paper forward-test"], ["approval", "Master duyệt", "Master approval"], ["export", "Xuất tài liệu áp dụng", "Application document exported"],
];
/** Trạng thái bước: [vi, en, tone, ký hiệu] — ký hiệu + chữ (không chỉ dựa vào màu) */
export const STEP_ST = {
  passed: ["Đạt", "Passed", "up", "✓"],
  pending: ["Chưa đạt/ đang chờ", "Pending", "accent", "○"],
  failed: ["TRƯỢT", "FAILED", "down", "✕"],
  blocked: ["Bị chặn", "Blocked", "down", "■"],
};
export const VERDICT_TONE = { not_eligible: "down", incomplete: "down", eligible_review: "accent", ready: "up" };

const arr = (x) => (Array.isArray(x) ? x : Array.isArray(x?.items) ? x.items : []);
const numOrNull = (v) => (v == null || v === "" || !Number.isFinite(+v) ? null : +v);
const pick = (o, vi, en, lang) => (lang === "en" ? o?.[en] ?? o?.[vi] : o?.[vi] ?? o?.[en]) ?? "";

export const normMethod = (m = {}) => ({
  id: String(m.id ?? ""), name: m.name || "", description: m.description || "", owner: m.owner || "", ownerName: m.owner_name || m.owner || "",
  version: m.version ?? null, updated_at: m.updated_at || null, scenarios: numOrNull(m.scenario_count ?? (Array.isArray(m.scenarios) ? m.scenarios.length : null)),
  clarityAvg: numOrNull(m.clarity_avg), plan: { passed: numOrNull(m.plan?.passed), total: numOrNull(m.plan?.total) ?? 9, verdict: m.plan?.verdict || null },
});
export const normScenario = (s = {}) => {
  const test = s.test || {}, paper = s.paper || {}, lb = s.labels || {};
  return {
    rid: String(s.room_id ?? ""), title: s.title || "", role: s.role || "core",
    clarity: numOrNull(s.clarity?.score), weakest: s.clarity?.weakest_row || null, confirmed: numOrNull(s.rows_confirmed),
    labels: { n: numOrNull(lb.n_labeled), of: numOrNull(lb.n_examples), precision: numOrNull(lb.precision) },
    test: { verdict: test.verdict && test.verdict !== "none" ? test.verdict : null, expectancy: numOrNull(test.expectancy_r), trades: numOrNull(test.trades), ci: Array.isArray(test.ci95) ? test.ci95 : null, opened: !!test.test_opened },
    paper: { trades: numOrNull(paper.trades), weeks: numOrNull(paper.weeks) },
  };
};
export const normRelation = (r = {}, i = 0) => ({ id: String(r.id ?? `r${i}`), kind: r.kind || "complementary", a: String(r.a ?? ""), b: r.b == null ? "" : String(r.b), regime: r.params?.regime || "", note: r.note || "" });
export const relToApi = (r) => ({ kind: r.kind, a: r.a, b: REL_BY[r.kind]?.[6] === false ? null : r.b, params: r.kind === "regime" ? { regime: r.regime } : {}, ...(r.note ? { note: r.note.slice(0, 200) } : {}) });

export const normPlan = (p = {}, lang = "vi") => {
  const raw = arr(p.steps);
  const steps = PLAN_STEPS.map((def, i) => {
    const s = raw.find((x) => x.n === i + 1 || x.key === def[0]) || {};
    const crit = arr(s.criteria).map((c) => (typeof c === "string" ? { label: c } : { label: pick(c, "label_vi", "label_en", lang) || c.id || "", required: c.required, actual: c.actual, pass: c.pass }));
    return {
      n: i + 1, key: s.key || def[0], title: pick(s, "title_vi", "title_en", lang) || (lang === "en" ? def[2] : def[1]),
      status: STEP_ST[s.status] ? s.status : "pending", owner: s.owner || "", since: s.since || "",
      criteria: crit, evidence: arr(s.evidence).map((e) => ({ label: e.label || "", value: e.value || "", room_id: e.room_id || null, kind: e.kind })),
      action: s.action ? { kind: s.action.kind, label: pick(s.action, "label_vi", "label_en", lang), room_id: s.action.room_id || null } : null, suggestions: arr(s.suggestions),
    };
  });
  const passed = numOrNull(p.progress?.passed) ?? steps.filter((s) => s.status === "passed").length;
  const code = p.verdict?.code || "incomplete";
  const g = steps.slice(3, 6).every((s) => s.status === "passed");
  return {
    steps, passed, total: numOrNull(p.progress?.total) ?? 9, code: !g && code === "ready" ? "incomplete" : code, // không bao giờ "ready" khi bước 4-6 chưa đạt
    label: pick(p.verdict, "label_vi", "label_en", lang), reasons: arr(p.verdict?.reasons), note: pick(p.verdict, "note_vi", "note_en", lang), computed_at: p.computed_at || null, thresholds: p.thresholds || null,
  };
};
/** Hàng canvas phương pháp -> hình dạng hàng của ProfileCanvas. */
export const normCanvasRows = (c, lang = "vi") => arr(c?.rows).map((a, i) => {
  const value = String(a.text ?? a.value ?? ""), conf = String(a.confidence ?? "").toLowerCase();
  const cf = /^(cao|high)/.test(conf) ? "high" : /^(v[uừ]a|med|mid)/.test(conf) ? "mid" : /^(th[aấ]p|low)/.test(conf) ? "low" : null;
  const filled = value.trim().length > 0, confirmed = !!a.confirmed;
  return { key: String(a.key ?? i), i, label: pick(a, "title_vi", "title_en", lang) || a.key, value, original: "", edited: false, confidence: filled ? cf : null, source: a.source?.author || "", turn: a.source?.turn ?? null, filled, confirmed, readonly: a.editable === false, score: filled ? 40 + (a.quantified ? 30 : 0) + (confirmed ? 30 : 0) : 0 };
});
export const clarityOf = (c) => { const s = c?.clarity?.score; return typeof s === "number" ? Math.round(s <= 1 ? s * 100 : s) : null; };

/** SSE phòng phương pháp (cùng định dạng sự kiện với phòng kịch bản). */
export async function streamMethodMessage(mid, text, handlers, signal, row) {
  const token = await getCsrf();
  let res;
  try {
    res = await fetch(`/api/v1${B}/methods/${enc(mid)}/messages`, { method: "POST", credentials: "same-origin", signal, headers: { Accept: "text/event-stream", "Content-Type": "application/json", "X-CSRF-Token": token }, body: JSON.stringify({ text, ...(row ? { row } : {}) }) });
  } catch (e) { if (e.name === "AbortError") return; throw new ApiError(0, "Không kết nối được máy chủ. Kiểm tra mạng rồi thử lại."); }
  if (!res.ok) { let d = ""; try { d = (await res.json()).detail; } catch { /* bỏ */ } throw new ApiError(res.status, res.status === 429 ? "AI đang nhận quá nhiều tin, đợi vài giây rồi gửi lại." : (typeof d === "string" && d) || `Lỗi ${res.status} từ máy chủ.`); }
  await readSSE(res, ({ data }) => { const h = handlers[data?.type]; if (h) h(data); }, signal);
}
