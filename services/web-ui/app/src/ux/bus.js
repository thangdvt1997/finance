// Toast + Trung tâm thông báo (kho ngoài React). Một đường duy nhất cho mọi thông báo: toast, âm báo, thông báo trình duyệt, chuông.
import { useSyncExternalStore } from "react";
import { getSettings } from "./settings";
import { beep } from "./sound";

const NKEY = "ts-notif";
const MAX_N = 200;
const MAX_AGE = 14 * 86400e3;

// ---------- Toast ----------
let toasts = [];
const tsubs = new Set();
const temit = () => tsubs.forEach((f) => f());
let tid = 0;
/** toast({tone: info|ok|warn|error, title, body, ttl, href, actionLabel, onAction}) -> id */
export function toast(t) {
  const id = ++tid;
  const item = { id, tone: "info", ttl: 6000, ...t };
  toasts = [...toasts.filter((x) => !(t.key && x.key === t.key)), item].slice(-4);
  temit();
  if (item.ttl > 0) setTimeout(() => dismissToast(id), item.ttl);
  return id;
}
export function dismissToast(id) { const n = toasts.filter((x) => x.id !== id); if (n.length !== toasts.length) { toasts = n; temit(); } }
export const useToasts = () => useSyncExternalStore((f) => { tsubs.add(f); return () => tsubs.delete(f); }, () => toasts, () => toasts);

// ---------- Thông báo ----------
function load() {
  try {
    const r = JSON.parse(localStorage.getItem(NKEY) || "null");
    if (r && Array.isArray(r.items)) return { items: r.items.filter((x) => Date.now() - x.ts < MAX_AGE).slice(0, MAX_N), lastOpen: r.lastOpen || 0 };
  } catch { /* hỏng -> bỏ */ }
  return { items: [], lastOpen: 0 };
}
let N = load();
const nsubs = new Set();
let snap = { items: N.items, unread: N.items.filter((x) => !x.read).length };
function save() {
  snap = { items: N.items, unread: N.items.filter((x) => !x.read).length };
  try { localStorage.setItem(NKEY, JSON.stringify(N)); } catch { /* đầy bộ nhớ */ }
  nsubs.forEach((f) => f());
}
export const useNotifications = () => useSyncExternalStore((f) => { nsubs.add(f); return () => nsubs.delete(f); }, () => snap, () => snap);

export const CATS = { alert: "Cảnh báo", news: "Tin quan trọng", expert: "Chuyên gia", system: "Hệ thống" };
const SEV_TONE = { crit: "error", warn: "warn", info: "info" };

/** notify({key, cat: alert|news|expert|system, sev: info|warn|crit, title, body, href, ts, quiet}) — quiet = chỉ ghi vào chuông, không toast/âm. */
export function notify(n) {
  const key = n.key || `${n.cat}:${n.title}:${Math.floor((n.ts || Date.now()) / 60000)}`;
  if (N.items.some((x) => x.key === key)) return false;
  const ts = n.ts || Date.now();
  const item = { id: `${ts}-${Math.random().toString(36).slice(2, 7)}`, key, cat: n.cat || "system", sev: n.sev || "info", title: String(n.title || "").slice(0, 200), body: String(n.body || "").slice(0, 600), href: n.href || "", ts, read: !!n.read };
  N = { ...N, items: [item, ...N.items].sort((a, b) => b.ts - a.ts).slice(0, MAX_N) };
  save();
  const s = getSettings();
  if (!n.quiet && !item.read && s.notifCats?.[item.cat] !== false) {
    if (s.toasts) toast({ tone: SEV_TONE[item.sev] || "info", title: item.title, body: item.body, href: item.href, key: `n:${key}`, ttl: item.sev === "crit" ? 12000 : 7000 });
    if (s.sound) beep(item.sev, s.soundVol);
    if (s.browserNotif && typeof Notification !== "undefined" && Notification.permission === "granted" && document.visibilityState === "hidden") {
      try { const nt = new Notification(item.title, { body: item.body, tag: key, silent: !s.sound }); nt.onclick = () => { focus(); if (item.href) location.hash = item.href.replace(/^#?/, "#"); }; } catch { /* một số trình duyệt di động chặn */ }
    }
  }
  return true;
}
export function markRead(id) { N = { ...N, items: N.items.map((x) => (x.id === id ? { ...x, read: true } : x)) }; save(); }
export function markAllRead() { N = { ...N, items: N.items.map((x) => (x.read ? x : { ...x, read: true })), lastOpen: Date.now() }; save(); }
export function removeNotif(id) { N = { ...N, items: N.items.filter((x) => x.id !== id) }; save(); }
export function clearNotifs() { N = { ...N, items: [] }; save(); }
export const lastOpen = () => N.lastOpen;
// đồng bộ giữa các tab
addEventListener("storage", (e) => { if (e.key === NKEY) { N = load(); save(); } });
