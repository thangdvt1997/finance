// Tuỳ chọn người dùng lưu phía máy chủ (/user/prefs): giao diện, nhóm theo dõi, thanh nav.
// Kho ngoài React (useSyncExternalStore) + lưu trễ (debounce) + xử lý xung đột rev (409).
import { useMemo, useSyncExternalStore } from "react";
import { api, apiWrite, WATCH } from "./api";

export const MAX_GROUPS = 20;
export const MAX_SYMBOLS = 100;
export const SYM_RE = /^[A-Za-z0-9:._-]{1,32}$/;
const MAX_JSON = 15500; // máy chủ giới hạn 16KB

let S = { loaded: false, available: true, rev: 0, prefs: {}, status: "idle", message: "" };
const subs = new Set();
const set = (patch) => { S = { ...S, ...patch }; subs.forEach((f) => f()); };
const subscribe = (f) => { subs.add(f); return () => subs.delete(f); };
export const usePrefsState = () => useSyncExternalStore(subscribe, () => S);
export const getPrefsState = () => S;

// ----- giao diện: áp ngay + nhớ localStorage để lần sau không nháy -----
export function applyTheme(t) {
  if (t !== "dark" && t !== "light") return;
  document.documentElement.dataset.theme = t;
  try { localStorage.setItem("ts-theme", t); } catch { /* chế độ ẩn danh */ }
  dispatchEvent(new CustomEvent("ts-theme", { detail: t }));
}

let pending = []; // các hàm sửa prefs chưa được máy chủ xác nhận (áp lại sau khi xung đột)
let timer = null;
let inflight = false;
let again = false;

export async function loadPrefs() {
  try {
    const r = await api("/user/prefs");
    pending = [];
    set({ loaded: true, available: true, rev: r.rev ?? 0, prefs: r.prefs || {}, status: "idle", message: "" });
    applyTheme(r.prefs?.theme);
    return true;
  } catch (e) {
    set({ loaded: true, available: false, status: "error", message: e?.message || "Không tải được tuỳ chọn." });
    return false;
  }
}
let started = false;
export function startPrefs() {
  if (started) return;
  started = true;
  loadPrefs();
}

/** Sửa prefs theo hàm fn(prefs) -> prefs mới; lưu lên máy chủ sau ~700ms. */
export function mutatePrefs(fn) {
  const next = fn(S.prefs || {});
  const size = JSON.stringify(next).length;
  if (size > MAX_JSON) {
    set({ status: "error", message: "Danh sách quá lớn (giới hạn 16KB). Bớt mã hoặc nhóm rồi thử lại." });
    return false;
  }
  pending.push(fn);
  set({ prefs: next, status: "dirty", message: "" });
  clearTimeout(timer);
  timer = setTimeout(flush, 700);
  return true;
}

export async function flush() {
  clearTimeout(timer);
  if (inflight) { again = true; return; }
  if (!S.available) {
    if (!(await loadPrefs())) return;
    // đã nối lại được: áp lại thay đổi cục bộ lên bản máy chủ
    return reapply(true);
  }
  inflight = true;
  const batch = pending;
  pending = [];
  set({ status: "saving", message: "" });
  try {
    const r = await apiWrite("PUT", "/user/prefs", { rev: S.rev, prefs: S.prefs });
    const quiet = pending.length === 0;
    set({ rev: r.rev, prefs: quiet && r.prefs ? r.prefs : S.prefs, status: quiet ? "saved" : "dirty", message: "" });
  } catch (e) {
    pending = batch.concat(pending);
    if (e.status === 409) {
      try {
        const r = await api("/user/prefs");
        set({ rev: r.rev ?? 0, prefs: r.prefs || {} });
        inflight = false;
        reapply(false);
        return;
      } catch { /* rơi xuống báo lỗi */ }
    }
    set({ status: "error", message: e.message });
  }
  inflight = false;
  if (again) { again = false; flush(); }
}
function reapply(silent) {
  let p = S.prefs || {};
  for (const fn of pending) p = fn(p);
  set({ prefs: p, status: pending.length ? "conflict" : "idle", message: silent ? "" : "Dữ liệu đã đổi ở nơi khác; đã tải lại bản mới và áp lại thay đổi của bạn." });
  if (pending.length) timer = setTimeout(flush, 300);
}

// ----- Giao diện lưu trong prefs -----
// Máy chủ chưa sẵn sàng thì không đẩy lên (giao diện vẫn nhớ qua localStorage).
export const savePref = (key, value) => { if (S.loaded && S.available) mutatePrefs((p) => ({ ...p, [key]: value })); };

// ----- Nhóm theo dõi -----
export const watchlistsOf = (prefs) => (Array.isArray(prefs?.watchlists) ? prefs.watchlists : []);
export function activeGroup(prefs) {
  const ws = watchlistsOf(prefs);
  return ws.find((w) => w.id === prefs?.active_watchlist) || ws[0] || null;
}
export function newGroupId() {
  return `g${Date.now().toString(36)}${Math.random().toString(36).slice(2, 6)}`.slice(0, 32);
}

/** Danh sách mã dùng cho băng giá / bảng giá; trả WATCH khi chưa có nhóm. Tham chiếu ổn định khi nội dung không đổi. */
export function useWatchSymbols() {
  const st = usePrefsState();
  const g = activeGroup(st.prefs);
  const key = g?.symbols?.length ? g.symbols.join(",") : "";
  return useMemo(() => (key ? key.split(",") : WATCH), [key]);
}
