// Lưu cấu hình biểu đồ theo người dùng: BẢN VẼ theo (mã, khung) và MẪU (template). Nguồn chân lý = máy chủ (`user_prefs.chart`,
// qua lib/prefs.js, có rev/xung đột); localStorage luôn giữ bản sao để dùng khi máy chủ lỗi hoặc chưa tải (fallback).
// Giới hạn: toàn bộ prefs <= 16KB, nên phần `chart` có ngân sách ~4.800 ký tự (dùng chung 16KB với watchlists + terminal); vượt thì bỏ bản vẽ CŨ NHẤT khỏi máy chủ (vẫn còn ở localStorage).
import { useMemo } from "react";
import { lget, lset } from "../../lib/lstore";
import { mutatePrefs, usePrefsState } from "../../lib/prefs";

export const CHART_BUDGET = 4800;
export const dkey = (symbol, tf) => `${symbol}|${tf}`;
const LOCAL_DRAW = (symbol, tf) => `ts-draw2:${symbol}:${tf}`;
const OLD_DRAW = (symbol, tf) => `ts-draw:${symbol}:${tf}`;
export const TPL_LOCAL = "ts-chart-tpl-v1";

const r6 = (p) => Math.round(p * 1e7) / 1e7;
/** Nén bản vẽ để vừa ngân sách (bỏ khoá mặc định, làm tròn giá). */
export function packDrawings(list) {
  return (list || []).map((d) => {
    const o = { i: d.id, y: d.type, p: d.pts.map((q) => [q.t, r6(q.p)]) };
    if (d.style && Object.keys(d.style).length) o.s = d.style;
    if (d.name) o.n = d.name;
    if (d.locked) o.l = 1;
    if (d.hidden) o.h = 1;
    return o;
  });
}
export function unpackDrawings(arr) {
  if (!Array.isArray(arr)) return [];
  return arr.filter((o) => o && o.y && Array.isArray(o.p)).map((o) => ({
    id: String(o.i || Math.random().toString(36).slice(2, 9)), type: o.y, pts: o.p.map(([t, p]) => ({ t, p })), style: o.s || {},
    ...(o.n ? { name: o.n } : {}), ...(o.l ? { locked: true } : {}), ...(o.h ? { hidden: true } : {}),
  }));
}

/** Đọc bản vẽ cục bộ: { ts, list } (hỗ trợ khoá cũ chỉ có mảng). */
export function readLocalDrawings(symbol, tf) {
  const v = lget(LOCAL_DRAW(symbol, tf), null);
  if (v && Array.isArray(v.list)) return v;
  const old = lget(OLD_DRAW(symbol, tf), null);
  return { ts: 0, list: Array.isArray(old) ? old : [] };
}
export function writeLocalDrawings(symbol, tf, list, ts) { lset(LOCAL_DRAW(symbol, tf), { ts, list }); }

/** Trạng thái prefs (loaded/available/prefs/status) để quyết định đọc/ghi máy chủ. */
export function useChartPrefs() { return usePrefsState(); }

/** Ghi bản vẽ lên máy chủ (debounce nằm trong mutatePrefs). Trả false nếu máy chủ chưa sẵn sàng/không vừa ngân sách. */
export function saveDrawingsServer(symbol, tf, list, ts) {
  const key = dkey(symbol, tf);
  return mutatePrefs((p) => {
    const chart = { ...(p.chart || {}) }, draw = { ...(chart.draw || {}) };
    if (!list.length) delete draw[key]; else draw[key] = { u: ts, d: packDrawings(list) };
    chart.draw = draw;
    while (JSON.stringify(chart).length > CHART_BUDGET) {
      const olds = Object.entries(draw).filter(([k]) => k !== key).sort((a, b) => (a[1].u || 0) - (b[1].u || 0));
      if (!olds.length) break;
      delete draw[olds[0][0]];
    }
    return { ...p, chart };
  });
}
export const serverDrawings = (prefs, symbol, tf) => prefs?.chart?.draw?.[dkey(symbol, tf)] || null;

// ---------- MẪU (template) ----------
/** Mẫu = { name, ts, type, ind:[{type,params,colors,width,visible}], style, signals, tool?:{ default style per tool } } */
export function readLocalTpl() { const v = lget(TPL_LOCAL, {}); return v && typeof v === "object" ? v : {}; }
export function useTemplates() {
  const st = useChartPrefs();
  const serverTpl = st.prefs?.chart?.tpl;
  return useMemo(() => {
    const local = readLocalTpl();
    const merged = { ...local };
    for (const [k, v] of Object.entries(serverTpl || {})) if (!merged[k] || (v.ts || 0) >= (merged[k].ts || 0)) merged[k] = v;
    return Object.values(merged).sort((a, b) => (b.ts || 0) - (a.ts || 0)).map((t) => ({ ...t, remote: !!serverTpl?.[t.name] }));
  }, [serverTpl, st.rev, st.status]); // eslint-disable-line react-hooks/exhaustive-deps
}
export function saveTemplate(tpl) {
  const t = { ...tpl, ts: Date.now() };
  const loc = readLocalTpl(); loc[t.name] = t; lset(TPL_LOCAL, loc);
  return mutatePrefs((p) => {
    const chart = { ...(p.chart || {}) }, tp = { ...(chart.tpl || {}) };
    tp[t.name] = t; chart.tpl = tp;
    while (JSON.stringify(chart).length > CHART_BUDGET && Object.keys(tp).length > 1) {
      const olds = Object.entries(tp).filter(([k]) => k !== t.name).sort((a, b) => (a[1].ts || 0) - (b[1].ts || 0));
      delete tp[olds[0][0]];
    }
    return { ...p, chart };
  });
}
export function deleteTemplate(name) {
  const loc = readLocalTpl(); delete loc[name]; lset(TPL_LOCAL, loc);
  return mutatePrefs((p) => {
    const chart = { ...(p.chart || {}) }, tp = { ...(chart.tpl || {}) };
    delete tp[name]; chart.tpl = tp;
    return { ...p, chart };
  });
}
const CFG_KEYS = ["type", "log", "auto", "volume", "signals", "serverPivot", "style", "sessions", "prevClose", "dayOpen", "pct", "events", "eventsAll", "news", "alerts", "boxSize", "corr", "corrWin"];
const LAYOUTS = ["1", "2v", "2h", "2x2", "1+3", "3x2"];
/** Kiểm tra JSON nhập vào (chống dữ liệu lạ): chỉ giữ trường mong đợi, giới hạn kích thước. */
export function sanitizeTemplate(o) {
  if (!o || typeof o !== "object" || typeof o.name !== "string" || !o.name.trim()) return null;
  const okType = (t) => typeof t === "string" && /^[a-z0-9]{2,20}$/.test(t);
  const plain = (v) => (v && typeof v === "object" && !Array.isArray(v) ? v : {});
  const ind = Array.isArray(o.ind) ? o.ind.filter((x) => x && okType(x.type)).slice(0, 12).map((x) => ({
    type: x.type, params: plain(x.params), colors: plain(x.colors), width: Number(x.width) || 1.5, visible: x.visible !== false,
  })) : [];
  const cfg = {};
  for (const k of CFG_KEYS) if (o.cfg && o.cfg[k] !== undefined) cfg[k] = o.cfg[k];
  if (cfg.type && !okType(cfg.type)) delete cfg.type;
  let ws = null;
  if (o.ws && LAYOUTS.includes(o.ws.layout) && Array.isArray(o.ws.cells)) {
    ws = { layout: o.ws.layout, cells: o.ws.cells.slice(0, 6).map((c) => ({ symbol: String(c.symbol || "").slice(0, 32), tf: String(c.tf || "H1").slice(0, 4), type: okType(c.type) ? c.type : "candles", grp: ["red", "blue", "green", "yellow"].includes(c.grp) ? c.grp : null })) };
  }
  const out = { name: o.name.trim().slice(0, 40), ts: Date.now(), cfg, ind };
  if (ws) out.ws = ws;
  if (JSON.stringify(out).length > 6000) return null;
  return out;
}
