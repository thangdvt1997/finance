// Quy tắc cảnh báo của người dùng: truy vấn, định nghĩa điều kiện, tóm tắt tiếng Việt, kiểm tra hợp lệ.
import { useQuery } from "@tanstack/react-query";
import { api } from "./api";

export const useRules = () =>
  useQuery({ queryKey: ["user-rules"], queryFn: ({ signal }) => api("/user/rules", {}, signal), staleTime: 10_000, refetchInterval: 30_000, retry: false });
export const useRuleEvents = (rule_id, limit = 100) =>
  useQuery({ queryKey: ["user-rule-events", rule_id || "", limit], queryFn: ({ signal }) => api("/user/rule-events", { rule_id, limit }, signal), staleTime: 10_000, refetchInterval: 30_000, retry: false });

export const MAX_COND = 8;
export const CHANNELS = { ntfy: "ntfy (đẩy lên điện thoại)", log: "Nhật ký hệ thống", telegram: "Telegram" };
export const TF_LIST = ["M1", "M5", "M15", "H1", "H4", "D1"];

export const OPS = { gte: "≥", lte: "≤", cross_up: "cắt lên trên", cross_down: "cắt xuống dưới", abs_gte: "|biến động| ≥", flip_up: "đổi dấu sang dương", flip_down: "đổi dấu sang âm" };
export const IND = {
  rsi: ["RSI", "0–100"], adx: ["ADX", "độ mạnh xu hướng"], stoch_k: ["Stochastic %K", "0–100"], bb_pctb: ["Bollinger %B", "0–1"],
  ema200_dist_pct: ["Khoảng cách EMA200", "%"], atr_pct: ["ATR", "% giá"], macd_hist: ["MACD histogram", ""], heat: ["Điểm nóng (heat)", ""], bias: ["Thiên hướng (bias)", ""],
};
export const STATE_FIELDS = {
  trend: ["Xu hướng", { up: "Tăng", down: "Giảm", side: "Đi ngang" }],
  momentum: ["Động lượng", { overbought: "Quá mua", oversold: "Quá bán", bullish: "Tăng", bearish: "Giảm", neutral: "Trung tính" }],
  volatility: ["Biến động", { squeeze: "Nén chặt", high: "Cao", normal: "Bình thường", low: "Thấp" }],
};
export const ACC_METRICS = { margin_level: ["Margin level", "%"], equity_drawdown_24h: ["Sụt vốn 24h từ đỉnh", "%"], floating_pl_pct: ["Lãi/lỗ đang mở", "% số dư"] };
export const COND_TYPES = {
  price: "Giá", pct_change: "% thay đổi giá", indicator: "Chỉ báo kỹ thuật", state: "Trạng thái kỹ thuật",
  news_window: "Tin kinh tế", sentiment: "Sentiment tin tức", account: "Tài khoản MT (chỉ đọc)",
};
export const LEVELS = { info: ["Thông tin", ""], warn: ["Cảnh báo", "accent"], crit: ["Nghiêm trọng", "down"] };
export const STATUS = { active: ["Đang chạy", "up"], fired: ["Đã kích hoạt", "accent"], expired: ["Hết hạn", ""], disabled: ["Đã tắt", ""] };

export const newCond = (type, symbol = "EURUSD") => {
  switch (type) {
    case "price": return { type, symbol, op: "gte", value: "" };
    case "pct_change": return { type, symbol, window_min: "60", op: "abs_gte", value: "0.5" };
    case "indicator": return { type, symbol, tf: "H1", field: "rsi", op: "gte", value: "70" };
    case "state": return { type, symbol, tf: "H1", field: "trend", is: "up" };
    case "news_window": return { type, impact: "high", within_min: "30", country: "", phase: "upcoming" };
    case "sentiment": return { type, symbol, window_h: "6", op: "gte", value: "0.3" };
    case "account": return { type, account_id: "", metric: "margin_level", op: "lte", value: "150" };
    default: return { type: "price", symbol, op: "gte", value: "" };
  }
};

export const emptyForm = () => ({
  name: "", enabled: true, logic: "and", conditions: [newCond("price")], mode: "once", cooldown_min: "60",
  expires_local: "", level: "warn", channels: ["ntfy", "log"], note: "",
});

// --- giờ VN (UTC+7, không DST) <-> datetime-local ---
export const isoToLocal = (iso) => (iso ? new Date(Date.parse(iso) + 7 * 3600e3).toISOString().slice(0, 16) : "");
export const localToIso = (v) => { const t = Date.parse(`${v}:00Z`); return Number.isNaN(t) ? null : new Date(t - 7 * 3600e3).toISOString(); };

const s = (v) => (v == null ? "" : String(v));
export function ruleToForm(r) {
  return {
    name: r.name || "", enabled: !!r.enabled, logic: r.logic || "and",
    conditions: (r.conditions || []).map((c) => Object.fromEntries(Object.entries(c).map(([k, v]) => [k, typeof v === "number" ? s(v) : v ?? ""]))),
    mode: r.mode || "once", cooldown_min: s(r.cooldown_min ?? 60), expires_local: isoToLocal(r.expires_at),
    level: r.level || "warn", channels: r.channels || [], note: r.note || "",
  };
}
/** Rule đã lưu -> RuleIn (để bật/tắt mà giữ nguyên phần còn lại). */
export const ruleToIn = (r, patch = {}) => ({
  name: r.name, enabled: r.enabled, logic: r.logic, conditions: r.conditions, mode: r.mode, cooldown_min: r.cooldown_min ?? 60,
  expires_at: r.expires_at ?? null, level: r.level, channels: r.channels, note: r.note || "", ...patch,
});

const SYM = /^[A-Za-z0-9:._-]{1,32}$/;
const num = (v) => (v === "" || v == null ? NaN : Number(v));
const intIn = (v, a, b) => { const n = num(v); return Number.isInteger(n) && n >= a && n <= b; };

/** Form -> { payload, errors }; errors: { "name": "...", "conditions.0.value": "..." } */
export function buildPayload(f) {
  const errors = {};
  const name = f.name.trim();
  if (!name) errors.name = "Nhập tên quy tắc.";
  else if (name.length > 80) errors.name = "Tên tối đa 80 ký tự.";
  if (!f.conditions.length) errors.conditions = "Cần ít nhất 1 điều kiện.";
  if (f.conditions.length > MAX_COND) errors.conditions = `Tối đa ${MAX_COND} điều kiện.`;
  const conditions = f.conditions.map((c, i) => {
    const e = (k, m) => { errors[`conditions.${i}.${k}`] = m; };
    const o = { ...c };
    const needSym = () => { o.symbol = (c.symbol || "").trim(); if (!SYM.test(o.symbol)) e("symbol", "Mã không hợp lệ (vd EURUSD, VN:FPT)."); };
    const needVal = (lo, hi) => {
      const n = num(c.value);
      if (Number.isNaN(n)) e("value", "Nhập một số."); else if (lo != null && n < lo) e("value", `Giá trị tối thiểu ${lo}.`); else if (hi != null && n > hi) e("value", `Giá trị tối đa ${hi}.`);
      o.value = n;
    };
    switch (c.type) {
      case "price": needSym(); needVal(); break;
      case "pct_change": needSym(); needVal(); if (!intIn(c.window_min, 1, 1440)) e("window_min", "Cửa sổ 1–1440 phút."); o.window_min = num(c.window_min); break;
      case "indicator": needSym(); needVal(); break;
      case "state": needSym(); break;
      case "news_window":
        if (!intIn(c.within_min, 5, 720)) e("within_min", "Từ 5 đến 720 phút.");
        o.within_min = num(c.within_min);
        o.country = (c.country || "").trim().toUpperCase();
        if (!o.country) delete o.country; else if (!/^[A-Z]{2,3}$/.test(o.country)) e("country", "Mã nước 2–3 chữ cái (vd US).");
        break;
      case "sentiment":
        needSym();
        if (!intIn(c.window_h, 1, 72)) e("window_h", "Cửa sổ 1–72 giờ.");
        o.window_h = num(c.window_h);
        if (String(c.op).startsWith("flip")) delete o.value; else needVal(-1, 1);
        break;
      case "account":
        o.account_id = (c.account_id || "").trim();
        if (!o.account_id) delete o.account_id;
        needVal();
        break;
      default: break;
    }
    return o;
  });
  const cd = num(f.cooldown_min);
  if (f.mode === "repeat" && !(Number.isInteger(cd) && cd >= 1 && cd <= 1440)) errors.cooldown_min = "Thời gian chờ 1–1440 phút.";
  let expires_at = null;
  if (f.expires_local) {
    expires_at = localToIso(f.expires_local);
    if (!expires_at) errors.expires_local = "Ngày giờ không hợp lệ.";
    else if (Date.parse(expires_at) <= Date.now()) errors.expires_local = "Thời điểm hết hạn phải ở tương lai.";
  }
  if (!f.channels.length) errors.channels = "Chọn ít nhất 1 kênh.";
  if ((f.note || "").length > 200) errors.note = "Ghi chú tối đa 200 ký tự.";
  return {
    errors,
    payload: {
      name, enabled: !!f.enabled, logic: f.logic, conditions, mode: f.mode,
      cooldown_min: f.mode === "repeat" ? cd : Number.isFinite(cd) ? Math.min(1440, Math.max(1, Math.round(cd))) : 60,
      expires_at, level: f.level, channels: f.channels, note: (f.note || "").trim(),
    },
  };
}

/** Lỗi 422 của máy chủ -> { errors: {path: msg}, general: [msg] } */
export function mapServerErrors(e) {
  const errors = {}, general = [];
  const d = e?.detail;
  if (Array.isArray(d)) {
    for (const x of d) {
      const path = (x.loc || []).filter((p) => p !== "body").join(".");
      if (path) errors[path] ??= x.msg; else general.push(x.msg);
    }
  } else if (typeof d === "string") general.push(d);
  else general.push(e?.message || "Lỗi không xác định.");
  return { errors, general };
}

const sl = (x) => (x || "").replace(/^(VN|US):/, "");
const n = (v) => (typeof v === "number" ? +v.toPrecision(8) : v);
/** Tóm tắt một điều kiện bằng tiếng Việt. */
export function summarize(c) {
  const sym = sl(c.symbol);
  switch (c.type) {
    case "price": return `Giá ${sym} ${OPS[c.op] || c.op} ${n(c.value)}`;
    case "pct_change": return `${sym} ${c.op === "abs_gte" ? "biến động tuyệt đối ≥" : OPS[c.op]} ${n(c.value)}% trong ${c.window_min} phút`;
    case "indicator": return `${IND[c.field]?.[0] || c.field} (${c.tf}) ${sym} ${OPS[c.op]} ${n(c.value)}`;
    case "state": { const f = STATE_FIELDS[c.field]; return `${f?.[0] || c.field} ${c.tf} của ${sym} là "${f?.[1]?.[c.is] || c.is}"`; }
    case "news_window": return `Tin tác động ${c.impact === "high" ? "cao" : "vừa"}${c.country ? ` (${c.country})` : ""} ${c.phase === "active" ? "đang trong cửa sổ T-15..T+30" : `sắp ra trong ${c.within_min} phút`}`;
    case "sentiment": return c.op?.startsWith("flip") ? `Sentiment ${sym} (${c.window_h}h) ${OPS[c.op]}` : `Sentiment ${sym} (${c.window_h}h) ${OPS[c.op]} ${n(c.value)}`;
    case "account": return `${ACC_METRICS[c.metric]?.[0] || c.metric} (${c.account_id || "mọi tài khoản"}) ${OPS[c.op]} ${n(c.value)}${ACC_METRICS[c.metric]?.[1]?.startsWith("%") ? "%" : ""}`;
    default: return c.type;
  }
}

export const PRESETS = [
  { id: "price", title: "Giá vượt ngưỡng", sub: "Giá chạm hoặc vượt một mức", build: (sym = "EURUSD") => ({ name: `${sl(sym)} chạm ngưỡng giá`, conditions: [newCond("price", sym)], level: "warn" }) },
  { id: "rsi", title: "RSI quá mua", sub: "RSI H1 ≥ 70", build: (sym = "EURUSD") => ({ name: `${sl(sym)} RSI quá mua`, conditions: [newCond("indicator", sym)], mode: "repeat", cooldown_min: "240", level: "info" }) },
  { id: "news", title: "Tin cao sắp ra", sub: "Tin tác động cao trong 30 phút tới", build: () => ({ name: "Tin tác động cao sắp ra", conditions: [newCond("news_window")], mode: "repeat", cooldown_min: "60", level: "warn" }) },
  { id: "margin", title: "Margin thấp", sub: "Margin level ≤ 150%", build: () => ({ name: "Margin level thấp", conditions: [newCond("account")], mode: "repeat", cooldown_min: "30", level: "crit", channels: ["ntfy", "log", "telegram"] }) },
  { id: "move", title: "Biến động mạnh", sub: "Giá đổi ≥ 0,5% trong 60 phút", build: (sym = "XAUUSD") => ({ name: `${sl(sym)} biến động mạnh`, conditions: [newCond("pct_change", sym)], mode: "repeat", cooldown_min: "60", level: "warn" }) },
  { id: "dd", title: "Sụt vốn 24h", sub: "Equity giảm ≥ 5% từ đỉnh 24h", build: () => ({ name: "Sụt vốn trong 24h", conditions: [{ ...newCond("account"), metric: "equity_drawdown_24h", op: "gte", value: "5" }], level: "crit", channels: ["ntfy", "log", "telegram"] }) },
];
