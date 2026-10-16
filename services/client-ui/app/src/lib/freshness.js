// Tính độ "tươi" của dữ liệu: nguồn + tuổi bản ghi, có xét thị trường nghỉ (cuối tuần/ngoài phiên) để không báo đỏ giả.
import { sessions } from "./session";
import { t } from "./i18n";

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
  if (ageS == null) return t("chưa có");
  if (ageS < 5) return t("vừa xong");
  if (ageS < 60) return t("{n} giây trước", { n: Math.round(ageS) });
  if (ageS < 3600) return t("{n} phút trước", { n: Math.round(ageS / 60) });
  if (ageS < 86400) return t("{n} giờ trước", { n: Math.round(ageS / 3600) });
  return t("{n} ngày trước", { n: Math.round(ageS / 86400) });
}

/**
 * Trạng thái kết nối EA/dữ liệu của một tài khoản, suy ra từ tuổi snapshot (giây):
 *  on <= 90s · slow <= 10 phút · off > 10 phút · none = chưa từng nhận.
 * Khi thị trường đóng cửa (cuối tuần/ngoài phiên) mà snapshot chưa mới thì là "idle" (bình thường), không báo lỗi,
 * trừ khi đã quá 3 ngày. abnormal = true chỉ với slow/off/none.
 */
export function connStatus({ ts, nowMs = Date.now(), closed = false, latencyMs = null }) {
  const tm = toMs(ts);
  if (tm == null) return { state: "none", ageS: null, latencyMs, label: t("Chưa nhận dữ liệu từ EA"), abnormal: true };
  const ageS = Math.max(0, (nowMs - tm) / 1000);
  const lat = Number.isFinite(Number(latencyMs)) && latencyMs !== null ? Number(latencyMs) : null;
  if (ageS <= 90) return { state: "on", ageS, latencyMs: lat, label: t("EA đang kết nối"), abnormal: false };
  if (closed && ageS <= 3 * 86400) return { state: "idle", ageS, latencyMs: lat, label: t("Thị trường đóng cửa"), abnormal: false };
  if (ageS <= 600) return { state: "slow", ageS, latencyMs: lat, label: t("EA phản hồi chậm"), abnormal: true };
  return { state: "off", ageS, latencyMs: lat, label: t("EA mất kết nối"), abnormal: true };
}
