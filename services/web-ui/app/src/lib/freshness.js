// Tính độ "tươi" của dữ liệu: nguồn + tuổi bản ghi, có xét thị trường nghỉ (cuối tuần/ngoài phiên) để không báo đỏ giả.
import { sessions } from "./session";

/** Ngưỡng (giây) gợi ý theo loại dữ liệu: ≤ warn: xanh, ≤ stale: vàng, > stale: đỏ. */
export const FRESH = {
  quote: { warnAfterS: 30, staleAfterS: 180 },
  bar: { warnAfterS: 300, staleAfterS: 1200 },
  account: { warnAfterS: 60, staleAfterS: 300 },
  analytics: { warnAfterS: 180, staleAfterS: 900 },
  news: { warnAfterS: 1800, staleAfterS: 7200 },
  calendar: { warnAfterS: 21600, staleAfterS: 172800 },
  experts: { warnAfterS: 86400, staleAfterS: 604800 },
  paper: { warnAfterS: 3600, staleAfterS: 21600 },
};

export function toMs(ts) {
  if (ts == null || ts === "") return null;
  const t = ts instanceof Date ? ts.getTime() : typeof ts === "number" ? (ts < 1e11 ? ts * 1000 : ts) : new Date(ts).getTime();
  return Number.isFinite(t) ? t : null;
}

/** Forex/kim loại: nghỉ từ T6 22:00 UTC đến CN 22:00 UTC (xấp xỉ). Crypto 24/7. VN/US theo phiên sàn. */
export function marketClosed(symbol, nowMs = Date.now()) {
  if (!symbol) return false;
  if (/^(BTC|ETH|SOL|XRP|BNB|DOGE|ADA)/.test(symbol)) return false;
  const d = new Date(nowMs);
  if (symbol.startsWith("VN:")) return !sessions(d).find((s) => s.id === "hanoi")?.open;
  if (symbol.startsWith("US:")) return !sessions(d).find((s) => s.id === "ny")?.open;
  const day = d.getUTCDay(), h = d.getUTCHours() + d.getUTCMinutes() / 60;
  return (day === 5 && h >= 22) || day === 6 || (day === 0 && h < 22);
}

/** -> { level: ok|warn|stale|idle|none, ageS } */
export function freshness({ ts, nowMs, warnAfterS = 30, staleAfterS = 180, closed = false }) {
  const t = toMs(ts);
  if (t == null) return { level: "none", ageS: null };
  const ageS = Math.max(0, (nowMs - t) / 1000);
  if (ageS <= warnAfterS) return { level: "ok", ageS };
  if (closed) return { level: "idle", ageS };
  return { level: ageS <= staleAfterS ? "warn" : "stale", ageS };
}

export function ageText(ageS) {
  if (ageS == null) return "chưa có";
  if (ageS < 5) return "vừa xong";
  if (ageS < 60) return `${Math.round(ageS)} giây trước`;
  if (ageS < 3600) return `${Math.round(ageS / 60)} phút trước`;
  if (ageS < 86400) return `${Math.round(ageS / 3600)} giờ trước`;
  return `${Math.round(ageS / 86400)} ngày trước`;
}
