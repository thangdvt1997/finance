import { useMemo } from "react";
import { useAuth } from "./auth";
import { t } from "./i18n";
import { useAccountSnaps } from "./queries";

export const ORDER_KINDS = { buy_limit: "Buy Limit", sell_limit: "Sell Limit", buy_stop: "Buy Stop", sell_stop: "Sell Stop", get other() { return t("Lệnh chờ"); } };
export const sideOf = (p) => (typeof p.side === "string" ? p.side.toLowerCase() : p.type === 1 ? "sell" : "buy");
const isOrder = (p) => /^(buy|sell)_(limit|stop)/.test(String(p?.kind || "")) || p?.pending === true;

/** Quy đổi snapshot thành số liệu hiển thị. Nguồn: /v1/accounts (đã lọc theo phiên). Chấp nhận `orders` hoặc mục `kind: *_limit|*_stop` trong positions. */
export function deriveView(snap) {
  if (!snap) return null;
  const raw = snap.positions || [];
  const positions = raw.filter((p) => !isOrder(p));
  const orders = [...(snap.orders || []), ...raw.filter(isOrder)];
  const floating = positions.reduce((s, p) => s + (Number(p.profit) || 0), 0);
  const equity = snap.equity ?? null, margin = snap.margin ?? null, balance = snap.balance ?? null;
  const free = equity != null && margin != null ? equity - margin : null;
  const level = margin ? (equity / margin) * 100 : null; // margin = 0 -> không có vị thế dùng margin
  return {
    equity, balance, margin, free, level, floating, positions, orders, ts: snap.ts, platform: snap.platform,
    hasOrdersFeed: Array.isArray(snap.orders) || raw.some(isOrder),
    lots: positions.reduce((s, p) => s + (Number(p.volume ?? p.lots) || 0), 0),
  };
}

/** Margin level -> mức độ cảnh báo dễ hiểu (ngưỡng tham khảo phổ biến: call ~100%, cảnh giác < 200%). */
export function marginTone(level) {
  if (level == null) return { tone: "up", key: "safe", label: t("Không có vị thế dùng margin"), color: "var(--up)" };
  if (level < 100) return { tone: "down", key: "crit", label: t("Nguy hiểm: sát hoặc dưới mức margin call"), color: "var(--down)" };
  if (level < 150) return { tone: "down", key: "high", label: t("Rất thấp: dễ bị đóng lệnh tự động"), color: "var(--down)" };
  if (level < 300) return { tone: "accent", key: "warn", label: t("Thấp: cần theo dõi sát"), color: "var(--accent)" };
  return { tone: "up", key: "safe", label: t("An toàn"), color: "var(--up)" };
}

/** Tài khoản đang chọn + snapshot + số liệu dẫn xuất. */
export function useActiveAccount() {
  const { active } = useAuth();
  const q = useAccountSnaps();
  const snap = useMemo(() => (q.data || []).find((s) => s.account_id === active?.id) || null, [q.data, active?.id]);
  const view = useMemo(() => deriveView(snap), [snap]);
  return { acc: active, q, snap, view };
}
