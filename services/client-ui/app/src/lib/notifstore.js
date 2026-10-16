// Trung tâm thông báo trong ứng dụng: kho nhỏ (useSyncExternalStore) + toast + thông báo hệ điều hành (nếu được cấp quyền).
// Lưu tối đa 60 mục (chỉ tiêu đề/nội dung ngắn, không số dư) theo từng người dùng; xoá khi đăng xuất.
import { useSyncExternalStore } from "react";
import { lget, lset, ldel } from "./lstore";

let uid = "";
let items = [];          // {id, ts, level: info|warn|crit, kind: alert|system|server, title, body, read}
let toasts = [];         // {id, title, body, level}
const toastSeen = new Set();
const subs = new Set();
const emit = () => subs.forEach((f) => f());
const keyOf = () => `tc-notif:${uid || "anon"}`;
const persist = () => lset(keyOf(), items.slice(0, 60).map(({ id, ts, level, kind, title, body, read }) => ({ id, ts, level, kind, title, body, read })));

export function bindUser(userId) {
  if (userId === uid) return;
  uid = userId || "";
  items = uid ? lget(keyOf(), []).filter((x) => x && x.id) : [];
  toasts = [];
  emit();
}
export function clearNotifications() { items = []; toasts = []; ldel(keyOf()); emit(); }

async function osNotify(title, body, tag) {
  try {
    if (typeof Notification === "undefined" || Notification.permission !== "granted" || !document.hidden) return;
    const reg = await navigator.serviceWorker?.getRegistration?.("/c/");
    if (reg?.showNotification) await reg.showNotification(title, { body, tag, icon: "/c/icons/icon-192.png", badge: "/c/icons/icon-192.png", data: { url: "/c/#/thong-bao" } });
    else new Notification(title, { body, tag, icon: "/c/icons/icon-192.png" });
  } catch { /* trình duyệt không cho phép: bỏ qua */ }
}

/** Thêm thông báo. dedupe: không thêm nếu cùng id đã có (vd sự kiện máy chủ). */
export function pushNotification({ id, level = "info", kind = "alert", title, body = "", toast = true, ts = Date.now(), persist: keep = true }) {
  const nid = id || `${kind}:${ts}:${Math.random().toString(36).slice(2, 7)}`;
  if (!keep) { // chỉ hiện toast/thông báo hệ điều hành (nội dung đã nằm trên máy chủ, không lưu cục bộ)
    if (toastSeen.has(nid)) return false;
    toastSeen.add(nid);
    if (toastSeen.size > 200) toastSeen.delete(toastSeen.values().next().value);
  } else {
    if (items.some((x) => x.id === nid)) return false;
    items = [{ id: nid, ts, level, kind, title, body, read: false }, ...items].slice(0, 60);
    persist();
  }
  if (toast) {
    toasts = [...toasts, { id: nid, title, body, level }].slice(-3);
    setTimeout(() => dismissToast(nid), level === "crit" ? 12000 : 7000);
  }
  osNotify(title, body, nid);
  emit();
  return true;
}
export function dismissToast(id) { toasts = toasts.filter((t) => t.id !== id); emit(); }
export function markAllRead() { items = items.map((x) => ({ ...x, read: true })); persist(); emit(); }
export function markRead(id) { items = items.map((x) => (x.id === id ? { ...x, read: true } : x)); persist(); emit(); }
export function removeNotification(id) { items = items.filter((x) => x.id !== id); persist(); emit(); }

const sub = (f) => { subs.add(f); return () => subs.delete(f); };
export const useNotifItems = () => useSyncExternalStore(sub, () => items);
export const useToasts = () => useSyncExternalStore(sub, () => toasts);
export const useUnread = () => useSyncExternalStore(sub, () => items.reduce((n, x) => n + (x.read ? 0 : 1), 0));

export const pushSupported = () => typeof Notification !== "undefined" && "serviceWorker" in navigator;
export async function askPermission() {
  if (typeof Notification === "undefined") return "unsupported";
  try { return await Notification.requestPermission(); } catch { return Notification.permission; }
}
