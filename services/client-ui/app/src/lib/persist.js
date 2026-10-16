// Lưu cache TanStack Query vào IndexedDB CHỈ cho dữ liệu dùng chung (thị trường, tin, lịch, phân tích, bản tin).
// KHÔNG BAO GIỜ lưu dữ liệu theo tài khoản (accounts, equity, risk, journal, user). Xoá sạch khi đăng xuất/đổi người dùng.
import { dehydrate, hydrate } from "@tanstack/react-query";

const DB = "tc-cache", STORE = "kv", KEY = "shared-v1", MAX_AGE = 6 * 3600e3;
const SHARED = new Set(["symbols", "quotes", "bars", "bars-pro", "news", "calendar", "risk-all", "an-overview", "an-screener", "an-sym", "briefing-latest"]);
const isShared = (q) => {
  const k = q.queryKey?.[0];
  return q.state.status === "success" && (SHARED.has(k) || (typeof k === "string" && (k.startsWith("an-symbol-") || k.startsWith("risk-") && k !== "risk-account" && !k.startsWith("risk-account-"))));
};

const open = () => new Promise((res, rej) => {
  if (typeof indexedDB === "undefined") return rej(new Error("no idb"));
  const r = indexedDB.open(DB, 1);
  r.onupgradeneeded = () => r.result.createObjectStore(STORE);
  r.onsuccess = () => res(r.result); r.onerror = () => rej(r.error);
});
const tx = async (mode, fn) => { const db = await open(); return new Promise((res, rej) => { const t = db.transaction(STORE, mode); const out = fn(t.objectStore(STORE)); t.oncomplete = () => { db.close(); res(out?.result); }; t.onerror = () => rej(t.error); }); };

export async function restoreCache(client) {
  try {
    const rec = await tx("readonly", (s) => s.get(KEY));
    if (!rec || Date.now() - rec.ts > MAX_AGE) return;
    hydrate(client, rec.state);
  } catch { /* không có IndexedDB: bỏ qua */ }
}
export async function clearPersisted() { try { await tx("readwrite", (s) => s.delete(KEY)); } catch { /* bỏ qua */ } }

let timer = 0;
export function startPersist(client) {
  const save = () => {
    clearTimeout(timer);
    timer = setTimeout(async () => {
      try {
        const state = dehydrate(client, { shouldDehydrateQuery: isShared });
        state.queries = state.queries.slice(0, 80).map((q) => ({ ...q, state: { ...q.state, fetchStatus: "idle" } }));
        await tx("readwrite", (s) => s.put({ ts: Date.now(), state }, KEY));
      } catch { /* đầy bộ nhớ: bỏ qua */ }
    }, 4000);
  };
  const off = client.getQueryCache().subscribe((e) => { if (e.type === "updated" && e.action?.type === "success") save(); });
  return () => { off(); clearTimeout(timer); };
}
