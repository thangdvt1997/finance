// Truy vấn + tiện ích cho: Trung tâm thông báo, Giới hạn & mục tiêu do khách tự đặt, tuỳ chọn thông báo, thiết bị push.
// Hợp đồng backend: xem docs (GET /user/limits, PUT /user/limits, GET /user/notifications, POST /user/notifications/read, /user/client-prefs, /user/push/devices).
// Giới hạn chỉ NHẮC, không chặn lệnh.
import { useInfiniteQuery, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, apiWrite } from "./api";
import { t } from "./i18n";

// ---------------- Giới hạn & mục tiêu ----------------
export const LIMIT_KEYS = ["daily_loss_pct", "max_dd_pct", "min_margin_level", "max_orders_day", "monthly_target_pct"];

/** Mô tả từng loại giới hạn. `loose`: chiều giá trị làm giới hạn NỚI LỎNG hơn ("up" = tăng là nới, "down" = giảm là nới, null = đổi có hiệu lực ngay). */
export function limitMeta(k) {
  switch (k) {
    case "daily_loss_pct": return { key: k, label: t("Lỗ tối đa trong ngày"), short: t("Lỗ trong ngày"), unit: "%", loose: "up", min: 0.1, max: 50, int: false, hint: t("Báo khi tổng lỗ của ngày (giờ VN) chạm mức % số dư bạn đặt."), example: "3" };
    case "max_dd_pct": return { key: k, label: t("Sụt vốn tối đa từ đỉnh"), short: t("Sụt vốn"), unit: "%", loose: "up", min: 0.5, max: 90, int: false, hint: t("Báo khi vốn giảm so với đỉnh gần nhất vượt mức % bạn đặt."), example: "10" };
    case "min_margin_level": return { key: k, label: t("Mức margin tối thiểu"), short: t("Margin tối thiểu"), unit: "%", loose: "down", min: 50, max: 2000, int: false, hint: t("Báo khi mức margin (vốn / margin đã dùng) xuống dưới mức này."), example: "300" };
    case "max_orders_day": return { key: k, label: t("Số lệnh tối đa mỗi ngày"), short: t("Lệnh trong ngày"), unit: "n", loose: "up", min: 1, max: 1000, int: true, hint: t("Báo khi số lệnh mở trong ngày (giờ VN) chạm mức này, giúp tránh giao dịch quá đà."), example: "10" };
    case "monthly_target_pct": return { key: k, label: t("Mục tiêu lợi nhuận tháng"), short: t("Mục tiêu tháng"), unit: "%", loose: null, min: 0.1, max: 500, int: false, hint: t("Mục tiêu lãi trong tháng (% số dư đầu tháng). Đổi mục tiêu có hiệu lực ngay."), example: "5", target: true };
    default: return { key: k, label: k, short: k, unit: "%", loose: null, min: 0, max: 1e9, int: false, hint: "", example: "" };
  }
}

/** Đổi từ `cur` sang `next` (null = xoá) có phải NỚI LỎNG không? Nới lỏng chỉ có hiệu lực sau 24 giờ. */
export function isLoosening(k, cur, next) {
  const m = limitMeta(k);
  if (!m.loose) return false;
  if (cur == null) return false;       // đặt giới hạn mới = siết chặt
  if (next == null) return true;       // xoá giới hạn = nới lỏng hoàn toàn
  return m.loose === "up" ? next > cur : next < cur;
}

export const levelOf = (p) => p?.level || "unknown";

export const useLimits = (accountId) =>
  useQuery({
    queryKey: ["user-limits", accountId || ""],
    queryFn: ({ signal }) => api("/user/limits", { account_id: accountId }, signal),
    enabled: !!accountId, staleTime: 15_000, refetchInterval: 30_000, retry: false,
  });

export const useLimitHistory = (accountId, limit = 30) =>
  useQuery({
    queryKey: ["user-limits-history", accountId || "", limit],
    queryFn: ({ signal }) => api("/user/limits/history", { account_id: accountId, limit }, signal),
    // Máy chủ trả {items:[{key,ts,by,old_value,new_value,applied,effective_at}]}; mock trả mảng {old,new}. Chuẩn hoá về mảng {old,new}.
    select: (d) => (Array.isArray(d) ? d : d?.items || []).map((h) => ({ ...h, old: h.old ?? h.old_value ?? null, new: h.new ?? h.new_value ?? null })),
    enabled: !!accountId, staleTime: 15_000, retry: false,
  });

/** Đặt/xoá/huỷ-thay-đổi một giới hạn. value = số | null (xoá). Trả {key, applied, value, pending_value, effective_at}. */
export function useSaveLimit(accountId) {
  const qc = useQueryClient();
  return async (key, value) => {
    const r = await apiWrite("PUT", "/user/limits", { account_id: accountId, key, value });
    await Promise.all([qc.invalidateQueries({ queryKey: ["user-limits", accountId] }), qc.invalidateQueries({ queryKey: ["user-limits-history", accountId] })]);
    return r;
  };
}

// ---------------- Thông báo trên máy chủ ----------------
export const NOTIF_KINDS = ["rule", "limit", "report", "briefing", "support", "system"];
export function kindLabel(k) {
  switch (k) {
    case "rule": return t("Cảnh báo quy tắc");
    case "limit": return t("Giới hạn");
    case "report": return t("Báo cáo");
    case "briefing": return t("Bản tin");
    case "support": return t("Hỗ trợ");
    case "system": return t("Hệ thống");
    default: return k;
  }
}

const PAGE = 20;
export const useServerNotifications = ({ kind, unread } = {}) =>
  useInfiniteQuery({
    queryKey: ["user-notifs", kind || "", unread ? 1 : 0],
    queryFn: ({ pageParam, signal }) => api("/user/notifications", { kind: kind || undefined, unread: unread ? 1 : undefined, limit: PAGE, before: pageParam || undefined }, signal),
    initialPageParam: "",
    getNextPageParam: (last) => ((last?.items || []).length >= PAGE ? last.items[last.items.length - 1].id : undefined),
    staleTime: 10_000, refetchInterval: 30_000, retry: false,
  });

/** Chỉ số chưa đọc cho chuông (nhẹ: limit=1). */
export const useServerUnread = () =>
  useQuery({
    queryKey: ["user-notifs-unread"],
    queryFn: ({ signal }) => api("/user/notifications", { limit: 1 }, signal),
    select: (d) => d?.unread ?? 0,
    staleTime: 10_000, refetchInterval: 30_000, retry: false,
  });

export function useMarkServerRead() {
  const qc = useQueryClient();
  return async (arg) => {
    await apiWrite("POST", "/user/notifications/read", arg === "all" ? { all: true } : { ids: arg });
    await Promise.all([qc.invalidateQueries({ queryKey: ["user-notifs"] }), qc.invalidateQueries({ queryKey: ["user-notifs-unread"] })]);
  };
}

// ---------------- Tuỳ chọn + thiết bị push ----------------
export const useClientPrefs = () =>
  useQuery({ queryKey: ["user-client-prefs"], queryFn: ({ signal }) => api("/user/client-prefs", {}, signal), staleTime: 30_000, retry: false });

export function useSaveClientPrefs() {
  const qc = useQueryClient();
  return async (rev, data) => {
    const r = await apiWrite("PUT", "/user/client-prefs", { rev, data });
    qc.setQueryData(["user-client-prefs"], r?.data ? r : { rev: (rev || 0) + 1, data });
    return r;
  };
}

export const usePushDevices = () =>
  useQuery({ queryKey: ["user-push-devices"], queryFn: ({ signal }) => api("/user/push/devices", {}, signal), staleTime: 15_000, retry: false });

export function useRemovePushDevice() {
  const qc = useQueryClient();
  return async (id) => { await apiWrite("DELETE", `/user/push/devices/${encodeURIComponent(id)}`); await qc.invalidateQueries({ queryKey: ["user-push-devices"] }); };
}

/** sha256 hex của endpoint push của thiết bị này (để đánh dấu "thiết bị này"); null khi không khả dụng. */
export async function currentEndpointHash() {
  try {
    const reg = await navigator.serviceWorker.ready;
    const sub = await reg.pushManager.getSubscription();
    if (!sub?.endpoint || !crypto?.subtle) return null;
    const buf = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(sub.endpoint));
    return [...new Uint8Array(buf)].map((b) => b.toString(16).padStart(2, "0")).join("");
  } catch { return null; }
}

/** Tên thiết bị gọn từ user-agent (không lộ chuỗi UA dài). */
export function deviceName(ua = "") {
  const s = String(ua);
  const os = /Android/i.test(s) ? "Android" : /iPhone|iPad|iOS/i.test(s) ? "iOS" : /Windows/i.test(s) ? "Windows" : /Mac OS|Macintosh/i.test(s) ? "macOS" : /Linux/i.test(s) ? "Linux" : t("Thiết bị");
  const br = /Edg\//.test(s) ? "Edge" : /OPR\/|Opera/.test(s) ? "Opera" : /Firefox\//.test(s) ? "Firefox" : /Chrome\//.test(s) ? "Chrome" : /Safari\//.test(s) ? "Safari" : "";
  return br ? `${br} · ${os}` : os;
}
