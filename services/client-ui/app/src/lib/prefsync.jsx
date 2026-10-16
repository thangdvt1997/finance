// Đồng bộ cài đặt giữa các thiết bị: GET/PUT /v1/user/client-prefs {rev, data}.
//  - localStorage vẫn là bản làm việc (offline chạy bình thường); máy chủ chỉ là bản chia sẻ.
//  - Sau đăng nhập: kéo bản máy chủ, áp dụng khoá khác biệt mà máy này CHƯA sửa tay; khoá máy này vừa sửa thắng và được đẩy lên.
//  - Đẩy lên có debounce ~1,5 s, một yêu cầu tại một thời điểm; 409 -> kéo bản mới, trộn (khoá sửa tay ở máy này thắng), thử lại tối đa 3 lần.
//  - Backend chưa có (404/403/405/501): chạy im lặng như trước (chỉ lưu máy này), trạng thái "unavailable".
//  - Khoá đồng bộ: lang, theme, density, tz, num, watchlist. Các khoá khác trên máy chủ (notif, layout...) được GIỮ NGUYÊN khi ghi.
import { useEffect, useSyncExternalStore } from "react";
import { api, apiWrite } from "./api";
import { lget, lset, ldel, onLocalWrite } from "./lstore";
import { DEFAULTS, usePrefs } from "./prefs";
import { useAuth } from "./auth";

export const SYNC_KEYS = ["lang", "theme", "density", "tz", "num", "watchlist"];
const PREFS_KEY = "tc-prefs", WL_KEY = "tc-wl2", STATE_KEY = "tc-prefsync";
const DEBOUNCE = 1500;
const eq = (a, b) => JSON.stringify(a) === JSON.stringify(b);
const okWatch = (w) => w && typeof w === "object" && Array.isArray(w.groups) && w.groups.length > 0;

const OK_VAL = {
  lang: (v) => v === "vi" || v === "en", theme: (v) => ["auto", "light", "dark"].includes(v), density: (v) => v === "comfortable" || v === "compact",
  tz: (v) => typeof v === "string" && v.length < 64, num: (v) => v === "en" || v === "vi", watchlist: okWatch,
};

// ---- trạng thái hiển thị (Hồ sơ) ----
let st = { status: "idle", at: null }; // idle | syncing | synced | offline | unavailable
const subs = new Set();
const setSt = (patch) => { st = { ...st, ...patch }; subs.forEach((f) => f()); };
const subscribe = (f) => { subs.add(f); return () => subs.delete(f); };
export const useSyncStatus = () => useSyncExternalStore(subscribe, () => st, () => st);

// ---- lõi ----
let enabled = false, started = null, applier = null, rev = 0, serverData = {}, base = {}, timer = null, running = false, again = false, uid = "";

const localSnap = () => {
  const p = { ...DEFAULTS, ...(lget(PREFS_KEY, {}) || {}) };
  const o = {};
  for (const k of SYNC_KEYS) if (k !== "watchlist") o[k] = p[k];
  const wl = lget(WL_KEY, null);
  if (okWatch(wl)) o.watchlist = wl;
  return o;
};
const saveState = () => lset(STATE_KEY, { uid, rev, base });
const dirtyKeys = (cur) => SYNC_KEYS.filter((k) => cur[k] !== undefined && !eq(cur[k], base[k]));
const valid = (data) => { const o = {}; for (const k of SYNC_KEYS) if (data && data[k] !== undefined && OK_VAL[k](data[k])) o[k] = data[k]; return o; };

function failure(e) {
  const s = e?.status;
  if (s === 401) { enabled = false; setSt({ status: "idle" }); return; }
  if (s === 403 || s === 404 || s === 405 || s === 501 || s === 422) { enabled = false; setSt({ status: "unavailable" }); return; }
  setSt({ status: "offline" });
  clearTimeout(timer); timer = setTimeout(push, 30_000); // lỗi mạng/5xx/429: thử lại sau
}

async function pull() {
  setSt({ status: "syncing" });
  let r;
  try { r = await api("/user/client-prefs"); } catch (e) { failure(e); return false; }
  enabled = true;
  rev = Number(r?.rev) || 0;
  serverData = r?.data && typeof r.data === "object" ? r.data : {};
  const prev = lget(STATE_KEY, null);
  const known = prev && prev.uid === uid ? prev.base || {} : null; // null = máy này chưa từng đồng bộ cho tài khoản này
  const cur = localSnap();
  const sv = valid(serverData);
  const patch = {}, nb = {};
  for (const k of SYNC_KEYS) {
    if (sv[k] === undefined) continue; // máy chủ chưa có -> bản máy này thắng (được đẩy lên)
    if (eq(sv[k], cur[k])) { nb[k] = sv[k]; continue; }
    const edited = known ? known[k] !== undefined && !eq(cur[k], known[k]) : false; // sửa tay ở máy này mà chưa đẩy
    if (edited) continue;
    patch[k] = sv[k]; nb[k] = sv[k];
  }
  base = nb;
  if (Object.keys(patch).length) applier?.(patch);
  saveState();
  if (dirtyKeys(localSnap()).length) { schedule(); } else setSt({ status: "synced", at: Date.now() });
  return true;
}

function schedule() {
  if (!enabled) return;
  clearTimeout(timer);
  timer = setTimeout(push, DEBOUNCE);
  if (st.status !== "syncing") setSt({ status: "syncing" });
}

async function push() {
  if (!enabled) return;
  if (running) { again = true; return; }
  running = true;
  try {
    for (let attempt = 0; attempt < 4; attempt++) {
      const cur = localSnap();
      const dk = dirtyKeys(cur);
      if (!dk.length) { setSt({ status: "synced", at: Date.now() }); return; }
      const mine = Object.fromEntries(dk.map((k) => [k, cur[k]]));
      try {
        const res = await apiWrite("PUT", "/user/client-prefs", { rev, data: { ...serverData, ...mine } });
        rev = Number(res?.rev) || rev + 1;
        serverData = res?.data && typeof res.data === "object" ? res.data : { ...serverData, ...mine };
        base = { ...base, ...mine };
        saveState();
      } catch (e) {
        if (e?.status !== 409) { failure(e); return; }
        // xung đột rev: kéo bản mới; khoá chưa sửa ở máy này lấy theo máy chủ, khoá đang sửa giữ của máy này
        let r;
        try { r = await api("/user/client-prefs"); } catch (e2) { failure(e2); return; }
        rev = Number(r?.rev) || rev + 1;
        serverData = r?.data && typeof r.data === "object" ? r.data : {};
        const sv = valid(serverData), patch = {};
        for (const k of SYNC_KEYS) {
          if (dk.includes(k) || sv[k] === undefined) continue;
          if (!eq(sv[k], cur[k])) patch[k] = sv[k];
          base[k] = sv[k];
        }
        if (Object.keys(patch).length) applier?.(patch);
        saveState();
      }
    }
    setSt({ status: "offline" });
  } finally {
    running = false;
    if (again) { again = false; schedule(); }
  }
}

onLocalWrite((key) => { if (enabled && (key === PREFS_KEY || key === WL_KEY)) schedule(); });

function start(userId, apply) {
  applier = apply;
  if (started === userId) return;
  started = userId; uid = userId; enabled = false; rev = 0; serverData = {}; base = {};
  pull();
}
function stop() {
  started = null; enabled = false; applier = null; clearTimeout(timer);
  setSt({ status: "idle", at: null });
}
/** Xoá dấu vết đồng bộ khi đăng xuất (không xoá cài đặt cục bộ). */
export const resetSync = () => { stop(); ldel(STATE_KEY); };
export const syncNow = () => (started ? (enabled ? push().then(pull) : pull()) : undefined);

/** Gắn một lần trong cây (main.jsx): đăng nhập xong -> kéo/đẩy; quay lại tab/có mạng -> kéo lại. */
export function PrefSync() {
  const a = useAuth();
  const { applyRemote } = usePrefs();
  const userId = a.status === "authed" && a.me?.role !== "master" && !a.me?.mustChange ? String(a.me?.userId ?? "") : "";
  useEffect(() => {
    if (!userId) { if (started) stop(); return undefined; }
    start(userId, applyRemote);
    const again2 = () => { if (document.visibilityState === "visible" && started && enabled && !running) pull(); };
    const online = () => { if (started) (enabled ? push().then(pull) : pull()); };
    document.addEventListener("visibilitychange", again2);
    addEventListener("online", online);
    return () => { document.removeEventListener("visibilitychange", again2); removeEventListener("online", online); };
  }, [userId, applyRemote]);
  return null;
}
