// Dữ liệu GIẢ cho chế độ ?mock=1 (yêu cầu quản trị) + báo cáo mẫu (backend báo cáo theo khách hàng chưa có).
import { ApiError } from "./api";

const iso = (ms) => new Date(ms).toISOString();
let TICKETS = [
  { id: "t-1001", category: "stale_data", message: "Giá vàng trên app chậm hơn MT khoảng 2 phút.", status: "answered", reply: "Đã kiểm tra: kết nối bị chậm tạm thời, đã khôi phục. Cảm ơn bạn đã báo.", created_at: iso(Date.now() - 3 * 86400e3), updated_at: iso(Date.now() - 3 * 86400e3 + 5400e3) },
];
let lastSend = 0, burst = 0;

/** Trả undefined nếu không xử lý. */
export async function handleToday(method, path, params, body) {
  if (path === "/user/tickets" && method === "GET") return { items: TICKETS };
  if (path === "/user/tickets" && method === "POST") {
    const now = Date.now();
    burst = now - lastSend < 60e3 ? burst + 1 : 1; lastSend = now;
    if (burst > 3) throw new ApiError(429, "Quá nhiều yêu cầu, đợi vài giây rồi thử lại.", "rate_limited", 30);
    if (!body?.message || body.message.length > 1000) throw new ApiError(422, "Dữ liệu không hợp lệ.");
    const t = { id: `t-${1002 + TICKETS.length}`, category: body.category, message: body.message, status: "open", reply: null, created_at: iso(now), updated_at: iso(now) };
    TICKETS = [t, ...TICKETS];
    return { id: t.id, status: "open" };
  }
  return undefined;
}

/** Báo cáo MẪU cho màn "Báo cáo của tôi" khi backend chưa có API. Số liệu bịa, deterministic theo kỳ. */
export function sampleReports(nowMs = Date.now()) {
  const day = 86400e3;
  const d0 = new Date(nowMs); d0.setUTCHours(0, 0, 0, 0);
  const out = [];
  const fmt = (ms) => new Date(ms).toISOString().slice(0, 10);
  const mk = (kind, period, i, scale) => {
    const k = ((i * 7919) % 17) - 6;
    return { id: `${kind}-${period}`, kind, period, status: "sample", pnl: +(k * 23.7 * scale).toFixed(2), trades: 3 + ((i * 5) % 9) * Math.ceil(scale), win_rate: 38 + ((i * 11) % 40), max_dd_pct: +(0.6 + ((i * 3) % 7) * 0.4).toFixed(1), currency: "USD" };
  };
  for (let i = 1; i <= 7; i++) out.push(mk("daily", fmt(d0.getTime() - i * day), i, 1));
  for (let i = 1; i <= 4; i++) out.push(mk("weekly", fmt(d0.getTime() - i * 7 * day), i + 3, 5));
  for (let i = 1; i <= 3; i++) { const m = new Date(Date.UTC(d0.getUTCFullYear(), d0.getUTCMonth() - i, 1)); out.push(mk("monthly", m.toISOString().slice(0, 7), i + 9, 20)); }
  return out;
}
