// Dữ liệu GIẢ (cờ ?mock=1) cho: thông báo máy chủ, giới hạn/mục tiêu, tuỳ chọn thông báo, thiết bị push, quy tắc cảnh báo cá nhân.
// Trả undefined khi không phải đường dẫn của mình để mock.js xử lý tiếp. Bịa hoàn toàn, không có tên nguồn.
import { ApiError } from "./api";

const NOW = () => Date.now();
const iso = (ms) => new Date(ms).toISOString();
const bad = (detail, status = 422) => { throw new ApiError(status, status === 409 ? "Dữ liệu đã thay đổi ở nơi khác." : status === 403 ? "Bạn không có quyền xem mục này." : "Dữ liệu không hợp lệ.", detail); };
const H = 3600e3, D = 86400e3;

// ---------- giới hạn ----------
const KEYS = ["daily_loss_pct", "max_dd_pct", "min_margin_level", "max_orders_day", "monthly_target_pct"];
const LOOSE = { daily_loss_pct: "up", max_dd_pct: "up", min_margin_level: "down", max_orders_day: "up", monthly_target_pct: null };
const LIM = {};     // account_id -> {key: {value, pending_value, pending_effective_at, updated_at}}
const HIST = {};    // account_id -> []
const CUR = { daily_loss_pct: 2.34, max_dd_pct: 4.1, min_margin_level: 412, max_orders_day: 9, monthly_target_pct: 3.2 };
function limState(acc) {
  if (!LIM[acc]) {
    LIM[acc] = {
      daily_loss_pct: { value: 3, pending_value: null, pending_effective_at: null, updated_at: iso(NOW() - 9 * D) },
      max_dd_pct: { value: 10, pending_value: 12, pending_effective_at: iso(NOW() + 17.5 * H), updated_at: iso(NOW() - 6 * H) },
      min_margin_level: { value: 300, pending_value: null, pending_effective_at: null, updated_at: iso(NOW() - 20 * D) },
      max_orders_day: { value: 10, pending_value: null, pending_effective_at: null, updated_at: iso(NOW() - 3 * D) },
      monthly_target_pct: { value: 5, pending_value: null, pending_effective_at: null, updated_at: iso(NOW() - 12 * D) },
    };
    HIST[acc] = [
      { ts: iso(NOW() - 6 * H), key: "max_dd_pct", old: 10, new: 12, applied: "pending", effective_at: iso(NOW() + 17.5 * H) },
      { ts: iso(NOW() - 3 * D), key: "max_orders_day", old: 15, new: 10, applied: "now", effective_at: iso(NOW() - 3 * D) },
      { ts: iso(NOW() - 9 * D), key: "daily_loss_pct", old: null, new: 3, applied: "now", effective_at: iso(NOW() - 9 * D) },
    ];
  }
  return LIM[acc];
}
function level(ratio) {
  if (ratio == null) return "unknown";
  if (ratio >= 1) return "hit";
  return ratio >= 0.9 ? "danger" : ratio >= 0.7 ? "warn" : "ok";
}
function progressFor(k, lim) {
  if (lim == null) return null;
  const cur = CUR[k];
  const ratio = k === "min_margin_level" ? lim / cur : cur / lim;
  const remaining = k === "min_margin_level" ? cur - lim : Math.max(0, lim - cur);
  return { current: cur, limit: lim, ratio: +ratio.toFixed(3), remaining: +remaining.toFixed(2), unit: k === "max_orders_day" ? "orders" : "%", level: level(ratio), as_of: iso(NOW() - 20e3) };
}
function limitsFor(acc) {
  const st = limState(acc);
  for (const k of KEYS) { // áp dụng thay đổi chờ hiệu lực đã tới hạn
    const it = st[k];
    if (it.pending_effective_at && Date.parse(it.pending_effective_at) <= NOW()) { it.value = it.pending_value; it.pending_value = null; it.pending_effective_at = null; }
  }
  return { account_id: acc, now: iso(NOW()), items: KEYS.map((k) => ({ key: k, ...st[k] })), progress: Object.fromEntries(KEYS.filter((k) => st[k].value != null).map((k) => [k, progressFor(k, st[k].value)])) };
}
function putLimit(acc, body) {
  const { key, value } = body || {};
  if (!KEYS.includes(key)) bad([{ loc: ["body", "key"], msg: "khoá giới hạn không hợp lệ" }]);
  if (value !== null && (typeof value !== "number" || !Number.isFinite(value) || value <= 0)) bad([{ loc: ["body", "value"], msg: "giá trị phải là số dương" }]);
  const st = limState(acc), it = st[key], cur = it.value;
  const log = (applied, eff) => { HIST[acc].unshift({ ts: iso(NOW()), key, old: cur, new: value, applied, effective_at: eff || iso(NOW()) }); };
  const hasPending = it.pending_effective_at != null;
  if (hasPending && value === cur) { it.pending_value = null; it.pending_effective_at = null; log("cancelled"); return { key, applied: "cancelled", value: cur, pending_value: null, effective_at: null }; }
  if (value === cur) return { key, applied: "noop", value: cur, pending_value: it.pending_value, effective_at: it.pending_effective_at };
  const loosen = cur != null && LOOSE[key] && (value === null || (LOOSE[key] === "up" ? value > cur : value < cur));
  if (loosen) {
    it.pending_value = value; it.pending_effective_at = iso(NOW() + 24 * H); it.updated_at = iso(NOW());
    log("pending", it.pending_effective_at);
    return { key, applied: "pending", value: cur, pending_value: value, effective_at: it.pending_effective_at };
  }
  it.value = value; it.pending_value = null; it.pending_effective_at = null; it.updated_at = iso(NOW());
  log("now");
  return { key, applied: "now", value, pending_value: null, effective_at: iso(NOW()) };
}

// ---------- thông báo ----------
const NOTIFS = (() => {
  const mk = (i, hAgo, kind, severity, title, body, link, account_id = "mt5:12345678") => ({ id: `n${1000 - i}`, kind, severity, title, body, account_id, link, ts: iso(NOW() - hAgo * H), read: i > 6 });
  const seed = [
    [0.4, "limit", "danger", "Lỗ trong ngày đạt 78% giới hạn", "Lỗ hôm nay 2,34% so với giới hạn 3%. Chỉ là nhắc, hệ thống không chặn lệnh.", "/gioi-han"],
    [1.2, "rule", "warn", "Giá EURUSD chạm 1,0900", "Quy tắc “EURUSD ≥ 1,0900” vừa kích hoạt. Giá hiện tại 1,0902.", "/canh-bao"],
    [2.5, "report", "info", "Báo cáo tuần đã sẵn sàng", "Tổng kết tuần 05–11/10: 31 lệnh, tỷ lệ thắng 54%, lãi ròng +1,8%.", "/bao-cao"],
    [3.1, "briefing", "info", "Bản tin sáng: thị trường thận trọng chờ số liệu bán lẻ Mỹ", "Vàng đi ngang vùng đỉnh, USD biến động nhẹ.", "/ban-tin"],
    [5, "support", "info", "Yêu cầu hỗ trợ #1042 đã có phản hồi", "Đội hỗ trợ đã trả lời về việc EA mất kết nối. Mở Trợ giúp để xem.", "/tro-giup"],
    [7, "limit", "warn", "Số lệnh trong ngày: 9/10", "Bạn đã mở 9 lệnh hôm nay; giới hạn bạn đặt là 10 lệnh.", "/gioi-han"],
    [9, "rule", "danger", "Mức margin còn 286%", "Tài khoản MT5 · 12345678 dưới ngưỡng 300% bạn đặt.", "/canh-bao"],
    [20, "system", "warn", "EA phản hồi chậm", "Tài khoản MT4 · 7654321 chưa gửi dữ liệu trong 12 phút.", "/rui-ro", "mt4:7654321"],
    [27, "report", "info", "Báo cáo ngày 10/10", "Hôm qua: 6 lệnh, +0,6%. Kỷ luật 82/100.", "/bao-cao"],
    [30, "limit", "info", "Đã siết chặt giới hạn lệnh/ngày", "Số lệnh tối đa/ngày: 15 → 10 (có hiệu lực ngay).", "/gioi-han"],
    [34, "rule", "warn", "Tin tác động cao sắp ra trong 30 phút", "Doanh số bán lẻ Mỹ 19:30. Cân nhắc vị thế đang mở.", "/tin-lich"],
    [50, "briefing", "info", "Bản tin tối quốc tế", "Chứng khoán Mỹ đóng cửa tăng nhẹ, vàng giữ vững.", "/ban-tin"],
    [52, "system", "info", "EA kết nối lại", "MT4 · 7654321 đã gửi dữ liệu trở lại.", "/tong-quan", "mt4:7654321"],
    [73, "limit", "warn", "Sụt vốn 7,4% từ đỉnh", "Bạn đặt giới hạn 10%. Cân nhắc giảm khối lượng.", "/gioi-han"],
    [76, "rule", "info", "XAUUSD biến động ≥ 1% trong 60 phút", "Vàng tăng 1,2% trong 1 giờ qua.", "/canh-bao"],
    [98, "report", "info", "Báo cáo tháng 9 đã sẵn sàng", "Lãi ròng +4,1%, sụt vốn tối đa 6,2%.", "/bao-cao"],
    [120, "support", "info", "Đã nhận yêu cầu hỗ trợ #1042", "Chúng tôi sẽ phản hồi sớm nhất có thể.", "/tro-giup"],
    [146, "limit", "danger", "Đã chạm giới hạn lỗ trong ngày", "Lỗ hôm qua đạt 3,1% (giới hạn 3%). Hệ thống chỉ nhắc, không chặn lệnh.", "/gioi-han"],
    [150, "rule", "warn", "GBPUSD ≤ 1,2500", "Giá GBPUSD xuống dưới ngưỡng bạn đặt.", "/canh-bao"],
    [170, "briefing", "info", "Bản tin sáng quốc tế", "Giá dầu giảm, đồng USD đi ngang.", "/ban-tin"],
  ];
  const out = seed.map((s, i) => mk(i, s[0], s[1], s[2], s[3], s[4], s[5], s[6]));
  for (let j = 0; j < 14; j++) out.push({ id: `n${980 - j}`, kind: ["rule", "limit", "report", "briefing", "system"][j % 5], severity: ["info", "warn", "info"][j % 3], title: ["Giá chạm ngưỡng", "Số lệnh trong ngày", "Báo cáo ngày", "Bản tin sáng", "EA kết nối lại"][j % 5], body: "Nội dung mẫu cho danh sách dài.", account_id: "mt5:12345678", link: ["/canh-bao", "/gioi-han", "/bao-cao", "/ban-tin", "/tong-quan"][j % 5], ts: iso(NOW() - (180 + j * 11) * H), read: true });
  return out;
})();
function listNotifs(p) {
  let arr = NOTIFS;
  if (p.kind) arr = arr.filter((x) => x.kind === p.kind);
  if (p.unread === "1" || p.unread === 1) arr = arr.filter((x) => !x.read);
  const unread = NOTIFS.filter((x) => !x.read).length;
  if (p.before) { const i = arr.findIndex((x) => x.id === p.before); arr = i >= 0 ? arr.slice(i + 1) : []; }
  return { items: arr.slice(0, Number(p.limit) || 20), unread };
}

// ---------- tuỳ chọn + thiết bị ----------
let PREFS = { rev: 3, data: { lang: "vi", notif: { rule: { app: true, push: true }, limit: { app: true, push: true }, report: { app: true, push: false }, briefing: { app: true, push: false }, support: { app: true, push: true } } } };
let DEVICES = [
  { id: "9f2c7d1ab04e5c36d81f0a9be2c47713aa5d09f1c3e6b8274d50a1be9c3f8d20", user_agent: "Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 Chrome/126.0 Mobile Safari/537.36", created_at: iso(NOW() - 20 * D), last_ok_at: iso(NOW() - 2 * H) },
  { id: "1b8e44a07c9d2f5630e1ad87b4c59f02d63e7a18b0c4d95e2f71a3860bd4c9e5", user_agent: "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/126.0 Safari/537.36 Edg/126.0", created_at: iso(NOW() - 45 * D), last_ok_at: iso(NOW() - 3 * D) },
];

// ---------- quy tắc cảnh báo cá nhân ----------
let RULES = [
  { id: "11111111-1111-4111-8111-111111111111", name: "Margin thấp (MT5 12345678)", enabled: true, logic: "and", status: "active", conditions: [{ type: "account", account_id: "mt5:12345678", metric: "margin_level", op: "lte", value: 300 }], mode: "repeat", cooldown_min: 30, level: "crit", channels: ["app", "push"], note: "", expires_at: null, last_fired_at: iso(NOW() - 9 * H), fire_count: 3 },
  { id: "22222222-2222-4222-8222-222222222222", name: "EURUSD lên 1,0900", enabled: true, logic: "and", status: "active", conditions: [{ type: "price", symbol: "EURUSD", op: "gte", value: 1.09 }], mode: "once", cooldown_min: 60, level: "warn", channels: ["app"], note: "", expires_at: iso(NOW() + 20 * D), last_fired_at: iso(NOW() - 1.2 * H), fire_count: 1 },
  { id: "33333333-3333-4333-8333-333333333333", name: "Tin mạnh sắp ra", enabled: false, logic: "and", status: "disabled", conditions: [{ type: "news_window", impact: "high", within_min: 30, phase: "upcoming" }], mode: "repeat", cooldown_min: 60, level: "info", channels: ["app", "push"], note: "", expires_at: null, last_fired_at: null, fire_count: 0 },
];
const EVENTS = [
  { id: 3, ts: iso(NOW() - 1.2 * H), rule_name: "EURUSD lên 1,0900", level: "warn", title: "Giá EURUSD ≥ 1,0900", body: "Giá hiện tại 1,0902." },
  { id: 2, ts: iso(NOW() - 9 * H), rule_name: "Margin thấp (MT5 12345678)", level: "crit", title: "Mức margin còn 286%", body: "Tài khoản mt5:12345678 chạm ngưỡng 300%." },
  { id: 1, ts: iso(NOW() - 2 * D), rule_name: "Margin thấp (MT5 12345678)", level: "crit", title: "Mức margin còn 291%", body: "Tài khoản mt5:12345678 chạm ngưỡng 300%." },
];
function validateRule(b, mine) {
  const errs = [];
  if (!b || typeof b.name !== "string" || b.name.trim().length < 1 || b.name.length > 60) errs.push({ loc: ["body", "name"], msg: "tên 1–60 ký tự" });
  if (!Array.isArray(b?.conditions) || b.conditions.length < 1 || b.conditions.length > 8) errs.push({ loc: ["body", "conditions"], msg: "cần 1–8 điều kiện" });
  (b?.conditions || []).forEach((c, i) => {
    if (c.type === "account") {
      if (!c.account_id) { if (mine.length !== 1) errs.push({ loc: ["body", "conditions", i, "account_id"], msg: "điều kiện tài khoản cần chọn một tài khoản" }); }
      else if (!mine.includes(c.account_id)) errs.push({ loc: ["body", "conditions", i, "account_id"], msg: "tài khoản không hợp lệ" });
    }
    if (c.type !== "news_window" && c.type !== "state" && !Number.isFinite(Number(c.value))) errs.push({ loc: ["body", "conditions", i, "value"], msg: "giá trị phải là số hữu hạn" });
  });
  if (errs.length) bad(errs);
}
const clientize = (b, mine) => {
  const ch = (b.channels || []).filter((x) => x === "app" || x === "push");
  return { ...b, conditions: b.conditions.map((c) => (c.type === "account" && !c.account_id ? { ...c, account_id: mine[0] } : c)), channels: ch.length ? ch : ["app"], cooldown_min: Math.max(Number(b.cooldown_min) || 60, 5) };
};
function previewConds(b) {
  return {
    result: false,
    conditions: b.conditions.map((c) => {
      const op = { gte: "≥", lte: "≤", cross_up: "cắt lên", cross_down: "cắt xuống", abs_gte: "|Δ| ≥" }[c.op] || c.op;
      if (c.type === "price") { const v = 1.0842; const ok = c.op === "lte" ? v <= c.value : v >= c.value; return { ok, value: v, text: `${c.symbol} = ${v} ${op} ${c.value}`, stale: false }; }
      if (c.type === "account") { const v = c.metric === "margin_level" ? 412 : c.metric === "equity_drawdown_24h" ? 4.1 : -0.8; const ok = c.op === "lte" ? v <= c.value : v >= c.value; return { ok, value: v, text: `${c.metric} = ${v}% ${op} ${c.value}%`, stale: false }; }
      if (c.type === "news_window") return { ok: false, value: null, text: "Chưa có tin tác động cao trong cửa sổ này", stale: false };
      if (c.type === "indicator") return { ok: c.op === "gte" ? 52 >= c.value : 52 <= c.value, value: 52, text: `${c.field} ${c.tf} = 52 ${op} ${c.value}`, stale: false };
      if (c.type === "pct_change") return { ok: null, value: 0.31, text: `${c.symbol} ${c.window_min} phút: +0.31%`, stale: true };
      return { ok: null, value: null, text: "Không đánh giá được", stale: true };
    }),
  };
}

export async function handleNotif(method, path, params, body, mine) {
  let m;
  if (path === "/user/limits" && method === "GET") { if (!mine.includes(params.account_id)) bad("forbidden", 403); return limitsFor(params.account_id); }
  if (path === "/user/limits" && method === "PUT") { if (!mine.includes(body?.account_id)) bad("forbidden", 403); return putLimit(body.account_id, body); }
  if (path === "/user/limits/history") { if (!mine.includes(params.account_id)) bad("forbidden", 403); limState(params.account_id); return HIST[params.account_id].slice(0, Number(params.limit) || 30); }
  if (path === "/user/notifications" && method === "GET") return listNotifs(params);
  if (path === "/user/notifications/read" && method === "POST") { for (const n of NOTIFS) if (body?.all || (body?.ids || []).includes(n.id)) n.read = true; return { ok: true, unread: NOTIFS.filter((x) => !x.read).length }; }
  if (path === "/user/client-prefs" && method === "GET") return PREFS;
  if (path === "/user/client-prefs" && method === "PUT") { if (body?.rev !== PREFS.rev) bad("rev_conflict", 409); PREFS = { rev: PREFS.rev + 1, data: body.data || {} }; return PREFS; }
  if (path === "/user/push/devices") return DEVICES;
  if ((m = /^\/user\/push\/devices\/(.+)$/.exec(path)) && method === "DELETE") { DEVICES = DEVICES.filter((d) => d.id !== decodeURIComponent(m[1])); return { ok: true }; }
  if (path === "/user/push/test" && method === "POST") return { ok: true, sent: DEVICES.length };
  if (path === "/user/rules" && method === "GET") return { items: RULES, limits: { max_rules: 20, max_conditions: 8, channels: ["app", "push"] } };
  if (path === "/user/rules" && method === "POST") {
    validateRule(body, mine);
    if (RULES.length >= 20) bad("đã đạt tối đa 20 quy tắc");
    const r = { id: crypto.randomUUID(), status: body.enabled === false ? "disabled" : "active", fire_count: 0, last_fired_at: null, note: "", ...clientize(body, mine) };
    RULES = [r, ...RULES];
    return r;
  }
  if (path === "/user/rules/preview" && method === "POST") { validateRule(body, mine); return previewConds(clientize(body, mine)); }
  if ((m = /^\/user\/rules\/([0-9a-f-]{36})$/.exec(path))) {
    if (method === "DELETE") { RULES = RULES.filter((r) => r.id !== m[1]); return { ok: true }; }
    if (method === "PUT") { validateRule(body, mine); RULES = RULES.map((r) => (r.id === m[1] ? { ...r, ...clientize(body, mine), status: body.enabled ? "active" : "disabled" } : r)); return RULES.find((r) => r.id === m[1]); }
  }
  if (path === "/user/rule-events") return { items: EVENTS.slice(0, Number(params.limit) || 50) };
  return undefined;
}
