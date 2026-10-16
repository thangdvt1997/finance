// Kho workspace của Terminal (ngoài React, useSyncExternalStore). Lưu: localStorage ngay + máy chủ (prefs.tm, giới hạn 16KB chung) sau ~800ms.
import { useSyncExternalStore } from "react";
import { mutatePrefs } from "../lib/prefs";
import { toast } from "../ux/bus";
import { WIDGETS } from "./registry";
import { TEMPLATES, DEFAULT_SET, buildWidgets } from "./defaults";

export const COLS = 24, ROW_H = 28, MARGIN = 8;
export const CHANNELS = [
  { id: "red", label: "Đỏ", color: "#ff5c7a" }, { id: "orange", label: "Cam", color: "#ff9f43" }, { id: "yellow", label: "Vàng", color: "#f0b84f" },
  { id: "green", label: "Xanh lá", color: "#2bd08f" }, { id: "cyan", label: "Lục lam", color: "#2ec4d6" }, { id: "blue", label: "Xanh dương", color: "#5aa9ff" },
  { id: "purple", label: "Tím", color: "#a78bfa" },
];
export const chColor = (id) => CHANNELS.find((c) => c.id === id)?.color;

const LS_KEY = "ts-tm1";
const LIMITS = { ws: 12, widgets: 40, name: 40 };
const SERVER_MAX = 11000; // chừa chỗ cho nhóm theo dõi/tuỳ chọn khác trong prefs 16KB
const rnd = () => Math.random().toString(36).slice(2, 8);
export const nid = () => rnd();
const int = (v, lo, hi, d) => { const n = Math.round(Number(v)); return Number.isFinite(n) ? Math.min(hi, Math.max(lo, n)) : d; };

function cleanWidget(w) {
  if (!w || typeof w.t !== "string") return null;
  const def = WIDGETS[w.t];
  const o = { i: String(w.i || nid()).slice(0, 12), t: w.t.slice(0, 40), x: int(w.x, 0, COLS - 1, 0), y: int(w.y, 0, 400, 0), w: int(w.w, 1, COLS, def?.defaultSize.w || 8), h: int(w.h, 1, 60, def?.defaultSize.h || 8) };
  if (w.c && typeof w.c === "object" && !Array.isArray(w.c) && Object.keys(w.c).length) o.c = w.c;
  if (CHANNELS.some((c) => c.id === w.k)) o.k = w.k;
  if (typeof w.n === "string" && w.n.trim()) o.n = w.n.slice(0, 60);
  return o;
}
function cleanWs(w, fallbackName) {
  const widgets = (Array.isArray(w?.x) ? w.x : []).slice(0, LIMITS.widgets).map(cleanWidget).filter(Boolean);
  const ids = new Set();
  for (const x of widgets) { while (ids.has(x.i)) x.i = nid(); ids.add(x.i); }
  const ch = {};
  if (w?.c && typeof w.c === "object") for (const c of CHANNELS) if (typeof w.c[c.id] === "string" && w.c[c.id].length <= 40) ch[c.id] = w.c[c.id];
  return { n: String(w?.n || fallbackName || "Workspace").slice(0, LIMITS.name), l: !!w?.l, x: widgets, c: ch };
}
function cleanState(raw) {
  if (!raw || typeof raw !== "object" || !raw.w || typeof raw.w !== "object") return null;
  const ws = {}, order = [];
  for (const id of Array.isArray(raw.o) ? raw.o : Object.keys(raw.w)) {
    if (!raw.w[id] || ws[id] || order.length >= LIMITS.ws) continue;
    ws[id] = cleanWs(raw.w[id]);
    order.push(id);
  }
  if (!order.length) return null;
  return { a: ws[raw.a] ? raw.a : order[0], o: order, w: ws };
}

function defaults() {
  const ws = {}, order = [];
  for (const id of DEFAULT_SET) {
    const t = TEMPLATES.find((x) => x.id === id);
    ws[id] = { n: t.name, l: false, x: buildWidgets(t, nid), c: {} };
    order.push(id);
  }
  return { a: order[0], o: order, w: ws };
}
function readLocal() { try { return cleanState(JSON.parse(localStorage.getItem(LS_KEY))); } catch { return null; } }

const init = readLocal();
let S = { ...(init || defaults()), serverSynced: false, save: "idle", note: "", kiosk: false, rot: 0, maxId: null };
let edited = !!init; // đã có dữ liệu người dùng (cục bộ)
const subs = new Set();
const emit = () => subs.forEach((f) => f());
const set = (p) => { S = { ...S, ...p }; emit(); };
const subscribe = (f) => { subs.add(f); return () => subs.delete(f); };
export const useTerminal = () => useSyncExternalStore(subscribe, () => S);
export const getTerminal = () => S;

// ---- lưu ----
const snapshot = () => ({ v: 1, a: S.a, o: S.o, w: S.w });
let timer = null;
let prefsAvail = false;
function schedule() {
  edited = true;
  try { localStorage.setItem(LS_KEY, JSON.stringify(snapshot())); } catch { /* chế độ ẩn danh */ }
  clearTimeout(timer);
  timer = setTimeout(pushServer, 800);
  S = { ...S, save: "dirty", note: "" };
}
function pushServer() {
  if (!prefsAvail) { set({ save: "local", note: "Chỉ lưu trên trình duyệt này (chưa nối được máy chủ)." }); return; }
  const snap = snapshot();
  const size = JSON.stringify(snap).length;
  if (size > SERVER_MAX) { set({ save: "local", note: `Cấu hình lớn (${(size / 1024).toFixed(1)}KB > ${(SERVER_MAX / 1024).toFixed(0)}KB) nên chỉ lưu trên máy này. Bớt widget hoặc ghi chú để đồng bộ.` }); return; }
  const ok = mutatePrefs((p) => ({ ...p, tm: snap }));
  set(ok ? { save: "saved", note: "" } : { save: "local", note: "Tuỳ chọn máy chủ đầy, chỉ lưu cục bộ." });
}
/** Gọi khi prefs máy chủ đã tải (available = máy chủ dùng được). Nhận bản máy chủ nếu người dùng chưa chỉnh gì; ngược lại đẩy bản cục bộ lên. */
export function syncFromServer(prefs, available) {
  prefsAvail = !!available;
  if (S.serverSynced) return;
  const remote = cleanState(prefs?.tm);
  if (remote && S.save !== "dirty") {
    S = { ...S, ...remote, serverSynced: true, save: "saved" };
    try { localStorage.setItem(LS_KEY, JSON.stringify(snapshot())); } catch { /* bỏ */ }
    edited = true;
    emit();
    return;
  }
  S = { ...S, serverSynced: true };
  if (edited && available) { schedule(); }
  emit();
}

// ---- thao tác workspace ----
const mut = (fn) => { const next = fn(S); if (next) { S = { ...S, ...next }; schedule(); emit(); } };
const patchWs = (id, fn) => mut((s) => (s.w[id] ? { w: { ...s.w, [id]: fn(s.w[id]) } } : null));

export const setActive = (id, persist = true) => {
  if (!S.w[id] || S.a === id) return;
  if (persist) mut(() => ({ a: id })); else set({ a: id });
};
export function addWorkspace(tplId = "blank", name) {
  if (S.o.length >= LIMITS.ws) { set({ note: `Tối đa ${LIMITS.ws} workspace.` }); return null; }
  const tpl = TEMPLATES.find((t) => t.id === tplId) || TEMPLATES[TEMPLATES.length - 1];
  const id = `w${rnd()}`;
  mut((s) => ({ w: { ...s.w, [id]: { n: (name || tpl.name).slice(0, LIMITS.name), l: false, x: buildWidgets(tpl, nid), c: {} } }, o: [...s.o, id], a: id }));
  return id;
}
export function duplicateWorkspace(id) {
  const w = S.w[id];
  if (!w || S.o.length >= LIMITS.ws) return null;
  const nidv = `w${rnd()}`;
  const copy = JSON.parse(JSON.stringify(w));
  copy.n = `${w.n} (bản sao)`.slice(0, LIMITS.name);
  copy.x.forEach((x) => { x.i = nid(); });
  mut((s) => { const o = [...s.o]; o.splice(o.indexOf(id) + 1, 0, nidv); return { w: { ...s.w, [nidv]: copy }, o, a: nidv }; });
  return nidv;
}
export function removeWorkspace(id) {
  if (S.o.length <= 1) return;
  const saved = S.w[id], at = S.o.indexOf(id);
  mut((s) => { const w = { ...s.w }; delete w[id]; const o = s.o.filter((x) => x !== id); return { w, o, a: s.a === id ? o[Math.max(0, at - 1)] : s.a }; });
  toast({ tone: "info", title: "Đã xoá workspace", body: saved?.n, ttl: 9000, actionLabel: "Hoàn tác", onAction: () => mut((s) => { if (s.w[id] || s.o.length >= LIMITS.ws) return null; const o = [...s.o]; o.splice(Math.min(at, o.length), 0, id); return { w: { ...s.w, [id]: saved }, o, a: id }; }) });
}
export const renameWorkspace = (id, name) => { const n = String(name || "").trim().slice(0, LIMITS.name); if (n) patchWs(id, (w) => ({ ...w, n })); };
export const setLocked = (id, l) => patchWs(id, (w) => ({ ...w, l: !!l }));
export function moveWorkspace(id, dir) {
  mut((s) => { const o = [...s.o]; const i = o.indexOf(id), j = i + dir; if (i < 0 || j < 0 || j >= o.length) return null; [o[i], o[j]] = [o[j], o[i]]; return { o }; });
}
export function resetWorkspace(id, tplId) {
  const tpl = TEMPLATES.find((t) => t.id === (tplId || id)) || TEMPLATES.find((t) => t.id === "overview");
  const before = S.w[id];
  patchWs(id, (w) => ({ ...w, x: buildWidgets(tpl, nid), c: {} }));
  if (before) toast({ tone: "info", title: "Đã đặt lại workspace theo mẫu", body: tpl.name, ttl: 9000, actionLabel: "Hoàn tác", onAction: () => patchWs(id, () => before) });
}

// ---- thao tác widget ----
export function addWidget(wsId, type, over = {}) {
  const def = WIDGETS[type];
  const w = S.w[wsId];
  if (!def || !w) return null;
  if (w.x.length >= LIMITS.widgets) { set({ note: `Tối đa ${LIMITS.widgets} widget mỗi workspace.` }); return null; }
  const id = nid();
  const bottom = w.x.reduce((m, x) => Math.max(m, x.y + x.h), 0);
  const item = { i: id, t: type, x: 0, y: bottom, w: def.defaultSize.w, h: def.defaultSize.h, ...over };
  patchWs(wsId, (ws) => ({ ...ws, x: [...ws.x, item] }));
  return id;
}
export function removeWidget(wsId, iid) {
  const it = S.w[wsId]?.x.find((x) => x.i === iid);
  if (!it) return;
  patchWs(wsId, (w) => ({ ...w, x: w.x.filter((x) => x.i !== iid) }));
  toast({ tone: "info", title: "Đã xoá widget", body: it.n || WIDGETS[it.t]?.title || it.t, ttl: 7000, actionLabel: "Hoàn tác", onAction: () => patchWs(wsId, (w) => (w.x.some((x) => x.i === iid) ? w : { ...w, x: [...w.x, it] })) });
}
export function duplicateWidget(wsId, iid) {
  const w = S.w[wsId]; const src = w?.x.find((x) => x.i === iid);
  if (!src || w.x.length >= LIMITS.widgets) return null;
  const id = nid();
  const copy = { ...JSON.parse(JSON.stringify(src)), i: id, y: src.y + src.h };
  patchWs(wsId, (ws) => ({ ...ws, x: [...ws.x, copy] }));
  return id;
}
export function updateWidget(wsId, iid, patch) {
  patchWs(wsId, (w) => ({ ...w, x: w.x.map((x) => {
    if (x.i !== iid) return x;
    const n = { ...x };
    if ("cfg" in patch) { const c = { ...(x.c || {}), ...patch.cfg }; for (const k of Object.keys(c)) if (c[k] === undefined) delete c[k]; if (Object.keys(c).length) n.c = c; else delete n.c; }
    if ("channel" in patch) { if (patch.channel) n.k = patch.channel; else delete n.k; }
    if ("title" in patch) { const t = String(patch.title || "").trim().slice(0, 60); if (t) n.n = t; else delete n.n; }
    if ("size" in patch) { n.w = int(patch.size.w, 1, COLS, n.w); n.h = int(patch.size.h, 1, 60, n.h); }
    return n;
  }) }));
}
/** Cập nhật vị trí/kích thước từ lưới; bỏ qua khi không đổi (tránh vòng lưu). */
export function applyLayout(wsId, layout) {
  const w = S.w[wsId];
  if (!w) return;
  let changed = false;
  const x = w.x.map((it) => {
    const l = layout.find((q) => q.i === it.i);
    if (!l || (l.x === it.x && l.y === it.y && l.w === it.w && l.h === it.h)) return it;
    changed = true;
    return { ...it, x: l.x, y: l.y, w: l.w, h: l.h };
  });
  if (changed) patchWs(wsId, (ws) => ({ ...ws, x }));
}
export function setChannelSymbol(wsId, ch, symbol) {
  if (!ch || !symbol) return;
  patchWs(wsId, (w) => (w.c[ch] === symbol ? w : { ...w, c: { ...w.c, [ch]: String(symbol).slice(0, 40) } }));
}

// ---- nhập/xuất ----
export function exportJSON(ids) {
  const list = ids || S.o;
  const w = {};
  for (const id of list) if (S.w[id]) w[id] = S.w[id];
  return JSON.stringify({ app: "terminal", v: 1, a: list[0], o: list, w }, null, 1);
}
export function importJSON(text) {
  let raw;
  try { raw = JSON.parse(text); } catch { return { error: "Tệp không phải JSON hợp lệ." }; }
  const st = cleanState(raw);
  if (!st) return { error: "Không thấy workspace nào trong tệp." };
  let added = 0;
  mut((s) => {
    const w = { ...s.w }, o = [...s.o];
    for (const id of st.o) {
      if (o.length >= LIMITS.ws) break;
      const nidv = w[id] ? `w${rnd()}` : id;
      const ws = st.w[id];
      ws.x.forEach((x) => { x.i = nid(); });
      w[nidv] = ws; o.push(nidv); added++;
    }
    return { w, o, a: o[o.length - 1] };
  });
  return { added };
}

// ---- toàn màn hình / trình chiếu ----
export function setKiosk(on) {
  document.documentElement.classList.toggle("tm-kiosk", !!on);
  if (on) { try { document.documentElement.requestFullscreen?.().catch(() => {}); } catch { /* bỏ */ } }
  else if (document.fullscreenElement) { try { document.exitFullscreen?.().catch(() => {}); } catch { /* bỏ */ } }
  set({ kiosk: !!on });
}
export const setRotate = (sec) => set({ rot: sec });
export const setMax = (id) => set({ maxId: id });
export const clearNote = () => set({ note: "" });
