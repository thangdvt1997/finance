// Lược đồ tham số mẫu luật + kiểm tra hợp lệ phía client (máy chủ vẫn là nguồn sự thật: services/auth/src/auth/fleet_rules.py).
export const DISCLAIMER_DEFAULT = "Luật của nhà cái/prop firm KHÁC NHAU và thay đổi theo thời gian (static/trailing, mốc reset ngày, cách tính nhất quán). Đây là công cụ THEO DÕI cấu hình được — hãy đặt tham số theo hợp đồng thực tế của từng khách.";
export const KINDS_FALLBACK = [
  { kind: "daily_loss", label: "Lỗ trong ngày" }, { kind: "max_drawdown", label: "Drawdown tối đa" }, { kind: "margin_level", label: "Margin level tối thiểu" },
  { kind: "best_day", label: "Ngày lãi tốt nhất / nhất quán" }, { kind: "max_trades_day", label: "Số lệnh/ngày" },
];

const TZ_RE = /^(UTC([+-]\d{1,2}(:\d{2})?)?|[A-Za-z]+(\/[A-Za-z_+\-0-9]+){1,2})$/;

// type: num | int | sel ; req: bắt buộc ; lo/hi: biên (đóng)
export const COMMON = [
  { key: "warn_usage_pct", label: "Ngưỡng vàng (% hạn mức)", type: "num", lo: 10, hi: 99, def: 70, unit: "%", hint: "Khi mức dùng hạn mức đạt giá trị này thì tài khoản chuyển sang “Sát ngưỡng” (vàng). Mặc định 70%. Đỏ (vi phạm) khi đạt 100%." },
  { key: "tz", label: "Múi giờ cắt ngày", type: "tz", def: "UTC", hint: "Múi giờ dùng để xác định “một ngày”. Nhập tên IANA (vd Europe/Prague, America/New_York) hoặc UTC+3. Mặc định UTC." },
  { key: "reset_hour", label: "Giờ reset trong ngày", type: "int", lo: 0, hi: 23, def: 0, unit: "giờ", hint: "Giờ (0–23, theo múi giờ ở trên) bắt đầu một ngày mới. Ví dụ prop firm cắt ngày 17:00 giờ New York thì đặt 17." },
];

export const FIELDS = {
  daily_loss: [
    { key: "limit_pct", label: "Hạn mức lỗ ngày", type: "num", lo: 0.1, hi: 100, req: true, unit: "%", def: 5, hint: "Lỗ tối đa trong một ngày, tính theo % của mốc cơ sở bên dưới. Lỗ đo bằng EQUITY nên gồm cả lệnh đang mở." },
    { key: "basis", label: "Mốc cơ sở", type: "sel", def: "day_start_equity", options: [["day_start_equity", "Equity đầu ngày"], ["initial_balance", "Số dư ban đầu"]], hint: "Hạn mức % tính trên equity tại mốc reset hằng ngày, hay trên số dư ban đầu cố định (nhập ở ô bên dưới)." },
    { key: "initial_balance", label: "Số dư ban đầu", type: "num", lo: 1, hi: 1e12, unit: "tiền tệ TK", showIf: (p) => p.basis === "initial_balance", reqIf: (p) => false, hint: "Số dư khởi điểm của tài khoản dùng làm mốc. Bỏ trống để hệ thống tự lấy số dư đầu tiên ghi nhận được." },
  ],
  max_drawdown: [
    { key: "limit_pct", label: "Hạn mức drawdown", type: "num", lo: 0.1, hi: 100, req: true, unit: "%", def: 10, hint: "Mức sụt giảm equity tối đa so với mốc (số dư ban đầu hoặc đỉnh equity), tính theo %." },
    { key: "mode", label: "Kiểu drawdown", type: "sel", def: "static", options: [["static", "Tĩnh (so với vốn ban đầu)"], ["trailing_eod", "Trailing cuối ngày"], ["trailing_intraday", "Trailing theo đỉnh equity"]], hint: "Tĩnh: sàn = vốn ban đầu × (1 − hạn mức). Trailing cuối ngày: sàn bám theo đỉnh equity cuối ngày. Trailing theo đỉnh: bám theo đỉnh equity tức thời." },
    { key: "initial_balance", label: "Số dư ban đầu", type: "num", lo: 1, hi: 1e12, unit: "tiền tệ TK", hint: "Vốn khởi điểm dùng làm mốc. Bỏ trống để hệ thống tự lấy số dư đầu tiên ghi nhận được." },
  ],
  margin_level: [
    { key: "min_level_pct", label: "Margin level tối thiểu", type: "num", lo: 10, hi: 100000, req: true, unit: "%", def: 150, hint: "Margin level (equity/margin đã dùng) không được thấp hơn mức này. Mức dùng hạn mức = mức tối thiểu ÷ margin level hiện tại." },
  ],
  best_day: [
    { key: "max_share_pct", label: "Ngày tốt nhất tối đa", type: "num", lo: 5, hi: 100, req: true, unit: "% tổng lãi", def: 40, hint: "Lãi của ngày tốt nhất không được vượt quá tỷ lệ này so với tổng lãi (luật nhất quán). Lãi ngày là xấp xỉ theo chênh equity, có thể gồm nạp/rút." },
    { key: "min_total_profit", label: "Tổng lãi tối thiểu để áp dụng", type: "num", lo: 0, hi: 1e12, def: 0, unit: "tiền tệ TK", hint: "Chỉ đánh giá khi tổng lãi đã vượt giá trị này (tránh báo động giả khi mới có lãi rất nhỏ). 0 = luôn đánh giá." },
  ],
  max_trades_day: [
    { key: "limit", label: "Số lệnh đóng tối đa mỗi ngày", type: "int", lo: 1, hi: 10000, req: true, unit: "lệnh", def: 50, hint: "Số deal đóng tối đa trong một ngày (theo mốc reset). Mức dùng hạn mức = số lệnh đã đóng ÷ hạn mức." },
  ],
};
export const fieldsOf = (kind) => [...(FIELDS[kind] || []), ...COMMON];

const isBlank = (v) => v === undefined || v === null || String(v).trim() === "";
/** Giá trị mặc định (chuỗi) cho form theo loại. */
export function defaults(kind) {
  const o = {};
  for (const f of fieldsOf(kind)) if (f.def !== undefined) o[f.key] = String(f.def);
  return o;
}
/** params từ máy chủ/mẫu gợi ý -> state form (chuỗi). */
export function toForm(kind, params = {}) {
  const o = defaults(kind);
  for (const f of fieldsOf(kind)) if (params[f.key] !== undefined && params[f.key] !== null) o[f.key] = String(params[f.key]);
  return o;
}
/** Kiểm tra hợp lệ -> {key: thông báo}. Chỉ kiểm các trường đang hiển thị. */
export function validate(kind, form) {
  const err = {};
  for (const f of fieldsOf(kind)) {
    if (f.showIf && !f.showIf(form)) continue;
    const v = form[f.key];
    if (isBlank(v)) { if (f.req) err[f.key] = "Bắt buộc nhập."; continue; }
    if (f.type === "sel") { if (!f.options.some((o) => o[0] === v)) err[f.key] = "Giá trị không hợp lệ."; continue; }
    if (f.type === "tz") { if (!TZ_RE.test(String(v).trim()) || String(v).trim().length > 40) err[f.key] = "Múi giờ không hợp lệ (vd UTC, UTC+3, Europe/Prague)."; continue; }
    const n = Number(v);
    if (!Number.isFinite(n)) { err[f.key] = "Phải là số."; continue; }
    if (f.type === "int" && !Number.isInteger(n)) { err[f.key] = "Phải là số nguyên."; continue; }
    if (n < f.lo || n > f.hi) err[f.key] = `Phải trong khoảng ${f.lo.toLocaleString("vi-VN")} – ${f.hi >= 1e12 ? "không giới hạn" : f.hi.toLocaleString("vi-VN")}.`;
  }
  return err;
}
/** state form -> params gửi máy chủ (chỉ trường hiển thị và có giá trị). */
export function toParams(kind, form) {
  const out = {};
  for (const f of fieldsOf(kind)) {
    if (f.showIf && !f.showIf(form)) continue;
    const v = form[f.key];
    if (isBlank(v)) continue;
    out[f.key] = f.type === "sel" ? v : f.type === "tz" ? String(v).trim() : Number(v);
  }
  return out;
}
const OPT = (kind, key, v) => (FIELDS[kind] || []).find((f) => f.key === key)?.options?.find((o) => o[0] === v)?.[1] || v;
/** Tóm tắt tham số một dòng. */
export function summarize(kind, p = {}) {
  const n = (x) => Number(x).toLocaleString("vi-VN", { maximumFractionDigits: 2 });
  const parts = [];
  if (kind === "daily_loss") parts.push(`${n(p.limit_pct)}%`, OPT(kind, "basis", p.basis || "day_start_equity"));
  else if (kind === "max_drawdown") parts.push(`${n(p.limit_pct)}%`, OPT(kind, "mode", p.mode || "static"));
  else if (kind === "margin_level") parts.push(`≥ ${n(p.min_level_pct)}%`);
  else if (kind === "best_day") parts.push(`≤ ${n(p.max_share_pct)}% tổng lãi`);
  else if (kind === "max_trades_day") parts.push(`≤ ${n(p.limit)} lệnh/ngày`);
  parts.push(`vàng ≥ ${n(p.warn_usage_pct ?? 70)}%`);
  if (p.tz) parts.push(`${p.tz} ${String(p.reset_hour ?? 0).padStart(2, "0")}:00`);
  return parts.join(" · ");
}
export const SCOPE_VN = { all: "Tất cả tài khoản", group: "Nhóm", tag: "Tag", account: "Tài khoản" };
