// Mô hình/nhãn dùng chung cho trang Sự cố (không chứa React). Thời gian hiển thị theo giờ Việt Nam (UTC+7, không đổi giờ mùa hè).
import { AlertOctagon, AlertTriangle, Info } from "lucide-react";

export const SEV = {
  critical: { tone: "bad", icon: AlertOctagon, label: "Nghiêm trọng", rank: 2 },
  warning: { tone: "warn", icon: AlertTriangle, label: "Cảnh báo", rank: 1 },
  info: { tone: "info", icon: Info, label: "Thông tin", rank: 0 },
};
export const sevOf = (s) => SEV[s] || SEV.info;

export const STATUS = [
  { id: "open", label: "Mới", count: "open" },
  { id: "ack", label: "Đã nhận", count: "ack" },
  { id: "snoozed", label: "Tạm hoãn", count: "snoozed" },
  { id: "resolved", label: "Đã đóng", count: "resolved_24h", sub: "24 giờ qua" },
];
export const STATUS_TONE = { open: "bad", ack: "info", snoozed: "mute", resolved: "ok" };

export const KIND_OPTS = [
  { value: "", label: "Mọi loại" },
  { value: "rule", label: "Luật tuân thủ" },
  { value: "budget", label: "Ngân sách" },
  { value: "ea", label: "Mất kết nối EA" },
  { value: "other", label: "Khác" },
];
export const KIND_LABEL = Object.fromEntries(KIND_OPTS.filter((o) => o.value).map((o) => [o.value, o.label]));

export const EVENT_VN = {
  opened: "Mở sự cố", ack: "Đã nhận", assign: "Giao việc", snooze: "Tạm hoãn", unsnooze: "Hết hạn tạm hoãn", note: "Ghi chú",
  resolve: "Đã đóng", reopen: "Mở lại", auto_resolve: "Tự đóng", escalate: "Nâng mức",
};
export const EVENT_TONE = { opened: "bad", escalate: "bad", ack: "info", assign: "info", note: "mute", snooze: "mute", unsnooze: "warn", resolve: "ok", auto_resolve: "ok", reopen: "warn" };

export const SNOOZE_MIN = 5;
export const SNOOZE_MAX = 10080;
export const clampSnooze = (m) => Math.max(SNOOZE_MIN, Math.min(SNOOZE_MAX, Math.round(Number(m) || 0)));

const VN_OFFSET = 7 * 3600e3;
/** Số phút đến 08:00 sáng kế tiếp theo giờ Việt Nam (tối thiểu 5 phút). */
export function minutesToMorning(now = Date.now()) {
  const vn = new Date(now + VN_OFFSET);
  let t = Date.UTC(vn.getUTCFullYear(), vn.getUTCMonth(), vn.getUTCDate(), 8, 0, 0) - VN_OFFSET;
  if (t - now < SNOOZE_MIN * 60e3) t += 86400e3;
  return clampSnooze(Math.ceil((t - now) / 60e3));
}
export const morningLabel = (now = Date.now()) => new Date(now + minutesToMorning(now) * 60e3).toLocaleString("vi-VN", { timeZone: "Asia/Ho_Chi_Minh", hour12: false, weekday: "short", day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" });

export const UNITS = [{ id: "m", label: "phút", k: 1 }, { id: "h", label: "giờ", k: 60 }, { id: "d", label: "ngày", k: 1440 }];

/** "3 giờ 5 phút" từ số phút. */
export function durVN(min) {
  const m = Math.max(0, Math.round(min));
  if (m < 60) return `${m} phút`;
  if (m < 1440) { const h = Math.floor(m / 60), r = m % 60; return r ? `${h} giờ ${r} phút` : `${h} giờ`; }
  const d = Math.floor(m / 1440), h = Math.round((m % 1440) / 60);
  return h ? `${d} ngày ${h} giờ` : `${d} ngày`;
}
/** Còn bao lâu đến mốc `until` (ISO) -> "còn 2 giờ 10 phút" | "sắp hết". */
export function leftVN(until, now = Date.now()) {
  const x = until ? Date.parse(until) : NaN;
  if (!Number.isFinite(x)) return "";
  const m = (x - now) / 60e3;
  return m <= 0.5 ? "sắp hết hạn" : `còn ${durVN(Math.ceil(m))}`;
}
/** "mở 12 phút trước" */
export function openedVN(t, now = Date.now()) {
  const x = t ? Date.parse(t) : NaN;
  if (!Number.isFinite(x)) return "—";
  const s = Math.max(0, (now - x) / 1000);
  if (s < 60) return "vừa mở";
  if (s < 3600) return `${Math.round(s / 60)} phút trước`;
  if (s < 86400) return `${Math.round(s / 3600)} giờ trước`;
  return `${Math.round(s / 86400)} ngày trước`;
}

export const isActive = (inc) => inc && inc.status !== "resolved";
export const autoClosed = (inc) => inc?.status === "resolved" && inc.resolved_by === "auto";
export const closerLabel = (inc) => (inc?.resolved_by === "auto" ? "Tự động (điều kiện đã hết)" : inc?.resolved_by || "—");

/** Lọc phía trình duyệt theo ô tìm kiếm (tiêu đề, chi tiết, mã tài khoản, nhãn, người phụ trách). */
export function matchQuery(inc, q, acct) {
  const s = (q || "").trim().toLowerCase();
  if (!s) return true;
  return [inc.title, inc.detail, inc.account_id, inc.assignee_label, acct?.label, acct?.client_name].some((v) => v && String(v).toLowerCase().includes(s));
}
export const chunk = (a, n) => { const o = []; for (let i = 0; i < a.length; i += n) o.push(a.slice(i, i + n)); return o; };
