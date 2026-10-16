// Mô hình "Hồ sơ kịch bản": 16 hàng cố định, tính phía client từ /profile khi API canvas chưa có; chuẩn hoá khi API canvas có.
// Độ rõ ý tưởng 0-100 = trung bình điểm hàng: có nội dung 40 + (có số định lượng | độ chắc >= vừa) 30 + đã xác nhận 30.
export const ROWS = [
  // key, nhãn vi, nhãn en, nguồn dữ liệu (khoá câu trả lời), cần số
  ["context", "Bối cảnh & xu hướng lớn", "Context & big trend", "context", false],
  ["symbol_tf", "Mã & khung", "Symbol & timeframe", "symbol_tf", false],
  ["formation", "Các bước hình thành (định lượng)", "Formation steps (quantified)", "formation", true],
  ["trigger", "Điểm kích hoạt vào lệnh", "Entry trigger", "trigger", true],
  ["invalidation", "Điều kiện HUỶ", "Cancel condition", "invalidation", true],
  ["sl", "SL", "SL", "sl_tp", true],
  ["tp", "TP / quản lý lệnh", "TP / trade management", "sl_tp", true],
  ["sizing", "Khối lượng & rủi ro", "Size & risk", "sizing", true],
  ["filters", "Bộ lọc (phiên, tin, biến động, spread)", "Filters (session, news, volatility, spread)", "filters", true],
  ["ex_ok", "Ví dụ ĐÚNG", "RIGHT examples", "@dung", false],
  ["ex_bad", "Ví dụ SAI / gần giống", "WRONG / look-alike examples", "@sai", false],
  ["failure", "Điều gì làm thất bại", "What makes it fail", "failure", false],
  ["symmetry", "Phiên bản đối xứng", "Mirrored version", "symmetry", false],
  ["rationale", "Lý do kinh tế / tâm lý", "Economic / psychological reason", "rationale", false],
  ["assumptions", "Giả định ngầm", "Hidden assumptions", "@assumptions", false],
  ["open_questions", "Câu hỏi còn mở", "Open questions", "@open", false],
];
export const ROW_KEYS = ROWS.map((r) => r[0]);

const norm = (c) => { const s = String(c || "").toLowerCase(); return /^(cao|high)/.test(s) ? "high" : /^(v[uừ]a|medium|mid)/.test(s) ? "mid" : /^(th[aấ]p|low)/.test(s) ? "low" : null; };
export const CONF = { high: ["Cao", "High", "up", "▲"], mid: ["Vừa", "Medium", "accent", "◆"], low: ["Thấp", "Low", "down", "▼"] };
const hasNum = (s) => /\d/.test(String(s || ""));
const last = (xs) => (Array.isArray(xs) ? [...xs].reverse().find((a) => a && !a.skipped && String(a.text || "").trim()) : null);
const txt = (x) => (typeof x === "string" ? x : x?.text ?? x?.value ?? x?.question ?? x?.title ?? JSON.stringify(x));

function fromProfile(p, key, src, ctx) {
  const lbl = Array.isArray(p.labels) ? p.labels : p.labels?.items || [];
  const base = { value: "", confidence: null, source: "", turn: null };
  if (src === "@dung" || src === "@sai") {
    const v = lbl.filter((l) => (src === "@dung" ? l.verdict === "dung" : l.verdict === "sai" || l.verdict === "gan_dung"));
    const ex = last(p.answers?.examples);
    const parts = v.map((l) => l.reason || l.example_id);
    return { ...base, value: parts.join("; ") || (src === "@dung" && ex ? ex.text : ""), count: v.length, confidence: v.length >= 3 ? "high" : v.length ? "mid" : ex && src === "@dung" ? norm(ex.confidence) : null, source: v.length ? ctx.labelsSrc(v.length) : ex ? `${ex.author || ""}` : "" };
  }
  if (src === "@assumptions") { const a = p.assumptions || []; return { ...base, value: a.map(txt).join("; "), confidence: a.length ? "low" : null, source: a.length ? ctx.aiSrc : "" }; }
  if (src === "@open") { const a = p.open_questions || []; return { ...base, value: a.map(txt).join("; "), confidence: a.length ? "low" : null, source: a.length ? ctx.aiSrc : "" }; }
  const a = last(p.answers?.[src]);
  if (!a) return base;
  return { ...base, value: String(a.text).trim(), confidence: norm(a.confidence), source: [a.author, a.source && a.source !== "chat" ? a.source : ""].filter(Boolean).join(" · ") };
}

/** Chuẩn hoá thành {rows, clarity:{score, weakest}}. apiCanvas (nếu có) ghi đè từng hàng theo khoá. local = {confirmed:{key:bool}, edits:{key:text}}. */
export function buildCanvas({ profile, understanding, apiCanvas, local = {}, lang = "vi" }) {
  const ctx = { aiSrc: lang === "en" ? "AI" : "AI", labelsSrc: (n) => (lang === "en" ? `${n} labels` : `${n} nhãn`) };
  const p = profile || {};
  const apiRows = Array.isArray(apiCanvas?.rows) ? Object.fromEntries(apiCanvas.rows.map((r) => [r.key, r])) : {};
  const rows = ROWS.map(([key, vi, en, src, quant], i) => {
    const d = fromProfile(p, key, src, ctx), a = apiRows[key] || {};
    const edited = local.edits?.[key];
    const value = edited != null ? edited : a.value ?? a.text ?? d.value;
    const conf = norm(a.confidence ?? a.certainty) || d.confidence;
    const confirmed = a.confirmed != null ? !!a.confirmed : !!local.confirmed?.[key];
    const filled = String(value || "").trim().length > 0;
    const quantApi = typeof a.quantified === "boolean" ? a.quantified : null;
    const quantOk = quantApi != null ? quantApi : quant ? hasNum(value) : conf === "high" || conf === "mid";
    const score = !filled ? 0 : 40 + (quantOk ? 30 : 0) + (confirmed ? 30 : 0);
    const base = a.original ?? d.value;
    const srcObj = a.source && typeof a.source === "object" ? a.source : null;
    const srcTxt = srcObj ? srcObj.author || "" : a.source ?? d.source;
    return { key, i, label: lang === "en" ? en : vi, value: String(value ?? ""), original: String(base ?? ""), edited: edited != null && edited !== base, confidence: filled ? conf : null, source: srcTxt, turn: srcObj?.turn ?? a.turn ?? null, ai: a.ai_understanding || "", hasExamples: !!a.has_examples, confirmed, filled, quant, score, readonly: a.editable === false || (src.startsWith("@") && src !== "@dung" && src !== "@sai") };
  });
  const sc = apiCanvas?.clarity?.score ?? apiCanvas?.clarity;
  const score = typeof sc === "number" ? Math.round(sc <= 1 ? sc * 100 : sc) : Math.round(rows.reduce((s, r) => s + r.score, 0) / rows.length);
  // hàng mơ hồ nhất: điểm thấp nhất; hàng "mở/giả định" không tính (chúng là kết quả, không phải thiếu)
  const cand = rows.filter((r) => r.key !== "open_questions" && r.key !== "assumptions");
  const wk = apiCanvas?.clarity?.weakest_row ?? apiCanvas?.clarity?.weakest;
  const weakest = wk ? rows.find((r) => r.key === wk) || null : cand.reduce((m, r) => (!m || r.score < m.score ? r : m), null);
  const known = rows.filter((r) => r.confirmed).length;
  return { rows, clarity: { score, next: apiCanvas?.clarity?.next_question || "", breakdown: apiCanvas?.clarity?.breakdown || null, weakest: weakest && (wk || weakest.score < 100) ? weakest : null, confirmed: known, filled: rows.filter((r) => r.filled).length, total: rows.length }, understanding };
}

/** Diff từ (cũ -> mới) ở mức từ; trả mảng [{t:"=|+|-", s}] */
export function wordDiff(a, b) {
  const x = String(a || "").split(/(\s+)/).filter(Boolean), y = String(b || "").split(/(\s+)/).filter(Boolean);
  const n = x.length, m = y.length;
  if (n * m > 40000) return [{ t: "-", s: a }, { t: "+", s: b }];
  const L = Array.from({ length: n + 1 }, () => new Uint16Array(m + 1));
  for (let i = n - 1; i >= 0; i--) for (let j = m - 1; j >= 0; j--) L[i][j] = x[i] === y[j] ? L[i + 1][j + 1] + 1 : Math.max(L[i + 1][j], L[i][j + 1]);
  const out = []; let i = 0, j = 0;
  while (i < n && j < m) { if (x[i] === y[j]) { out.push({ t: "=", s: x[i] }); i++; j++; } else if (L[i + 1][j] >= L[i][j + 1]) out.push({ t: "-", s: x[i++] }); else out.push({ t: "+", s: y[j++] }); }
  while (i < n) out.push({ t: "-", s: x[i++] }); while (j < m) out.push({ t: "+", s: y[j++] });
  return out;
}
