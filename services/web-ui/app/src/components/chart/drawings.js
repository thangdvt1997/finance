// Công cụ VẼ trên biểu đồ: Series Primitive chính thức của lightweight-charts (Apache-2.0, cùng cơ chế với plugin-examples
// của TradingView: trend-line, rectangle-drawing-tool, ...). Điểm neo lưu theo (thời gian, giá) nên đúng ở mọi khung/zoom.
// Engine tự xử lý chuột/cảm ứng: đặt điểm, chọn, kéo điểm neo, kéo cả hình, nam châm (snap OHLC), Undo.

import { geomExtra, paintExtra } from "./drawings2";

export const TOOLS = [
  { id: "cursor", label: "Con trỏ", pts: 0, key: "Esc" },
  { id: "trend", label: "Đường xu hướng", pts: 2, key: "D" },
  { id: "ray", label: "Tia", pts: 2, key: "Y" },
  { id: "extended", label: "Đường kéo dài", pts: 2, key: "E" },
  { id: "hline", label: "Đường ngang", pts: 1, key: "H" },
  { id: "vline", label: "Đường dọc", pts: 1, key: "V" },
  { id: "rect", label: "Hình chữ nhật", pts: 2, key: "R" },
  { id: "channel", label: "Kênh song song", pts: 3, key: "C" },
  { id: "fib", label: "Fibonacci thoái lui", pts: 2, key: "F" },
  { id: "fibext", label: "Fibonacci mở rộng", pts: 3, key: "X" },
  { id: "ruler", label: "Thước đo (giá, %, nến)", pts: 2, key: "M" },
  { id: "regression", label: "Kênh hồi quy tuyến tính", pts: 2, key: "", alt: "K" },
  { id: "pitchfork", label: "Pitchfork Andrews", pts: 3, key: "", alt: "P" },
  { id: "gannfan", label: "Gann fan", pts: 2, key: "", alt: "G" },
  { id: "triangle", label: "Tam giác", pts: 3, key: "", alt: "3" },
  { id: "elliott5", label: "Sóng Elliott đẩy (0-5)", pts: 6, key: "", alt: "E" },
  { id: "elliottabc", label: "Sóng Elliott điều chỉnh (ABC)", pts: 4, key: "", alt: "Q" },
  { id: "supply", label: "Vùng cung (supply)", pts: 2, key: "", alt: "U" },
  { id: "demand", label: "Vùng cầu (demand)", pts: 2, key: "", alt: "J" },
  { id: "arrow", label: "Mũi tên", pts: 2, key: "", alt: "W" },
  { id: "text", label: "Nhãn văn bản", pts: 1, key: "", alt: "B" },
  { id: "note", label: "Ghi chú", pts: 1, key: "", alt: "L" },
  { id: "fibarc", label: "Cung Fibonacci", pts: 2, key: "", alt: "I" },
  { id: "fibtime", label: "Vùng thời gian Fibonacci", pts: 2, key: "", alt: "Z" },
  { id: "projection", label: "Projection (chiếu đoạn giá)", pts: 3, key: "", alt: "O" },
  { id: "avwap", label: "VWAP neo (anchored)", pts: 1, key: "", alt: "A" },
  { id: "vprofile", label: "Volume profile (xấp xỉ)", pts: 2, key: "", alt: "Y" },
];
/** Nhóm công cụ cho thanh vẽ (flyout). */
export const TOOL_GROUPS = [
  { id: "lines", label: "Đường", tools: ["trend", "ray", "extended", "hline", "vline", "arrow", "channel", "regression", "pitchfork"] },
  { id: "fib", label: "Fibonacci & Gann", tools: ["fib", "fibext", "fibarc", "fibtime", "gannfan", "projection"] },
  { id: "shapes", label: "Hình & sóng", tools: ["rect", "triangle", "supply", "demand", "elliott5", "elliottabc"] },
  { id: "ann", label: "Chú thích", tools: ["text", "note", "ruler"] },
  { id: "vol", label: "Khối lượng", tools: ["avwap", "vprofile"] },
];
export const NEEDS_TEXT = new Set(["text", "note"]);
export const TOOL_BY_ALT = {};
const TOOL = Object.fromEntries(TOOLS.map((t) => [t.id, t]));
export const TOOL_BY_KEY = Object.fromEntries(TOOLS.filter((t) => t.key.length === 1).map((t) => [t.key.toLowerCase(), t.id]));
// Alt+chữ (kiểu TradingView): Alt+T đường xu hướng, Alt+F Fibonacci, Alt+H đường ngang, Alt+V đường dọc, ...
Object.assign(TOOL_BY_ALT, { t: "trend", f: "fib", h: "hline", v: "vline", r: "rect", c: "channel", x: "fibext", m: "ruler" },
  Object.fromEntries(TOOLS.filter((t) => t.alt).map((t) => [t.alt.toLowerCase(), t.id])));

export const DRAW_COLORS = ["#5aa9ff", "#f0b84f", "#2bd08f", "#ff5c7a", "#c792ea", "#4dd0e1", "#ff8a5c", "#8b98a8"];
const DEFAULT_COLOR = { trend: "#5aa9ff", ray: "#5aa9ff", extended: "#5aa9ff", hline: "#f0b84f", vline: "#f0b84f", rect: "#c792ea", channel: "#4dd0e1", fib: "#f0b84f", fibext: "#ff8a5c", ruler: "#2bd08f",
  regression: "#4dd0e1", pitchfork: "#c792ea", gannfan: "#f0b84f", triangle: "#5aa9ff", elliott5: "#2bd08f", elliottabc: "#ff8a5c", supply: "#ff5c7a", demand: "#2bd08f",
  arrow: "#f0b84f", text: "#d6dfeb", note: "#f0b84f", fibarc: "#c792ea", fibtime: "#8b98a8", projection: "#4dd0e1", avwap: "#ff8a5c", vprofile: "#5aa9ff" };
export const DEFAULT_COLORS = DEFAULT_COLOR;
export const FIB = [0, 0.236, 0.382, 0.5, 0.618, 0.786, 1, 1.272, 1.618];
export const FIBEXT = [0, 0.236, 0.382, 0.5, 0.618, 0.786, 1, 1.272, 1.618, 2, 2.618];
const FIB_COL = ["#8b98a8", "#ff5c7a", "#ff8a5c", "#2bd08f", "#4dd0e1", "#5aa9ff", "#8b98a8", "#c792ea", "#ff7ac6", "#f0b84f", "#aed581"];

const hexA = (hex, a) => {
  const m = /^#([0-9a-f]{6})$/i.exec(hex || "");
  if (!m) return hex;
  const n = parseInt(m[1], 16);
  return `rgba(${(n >> 16) & 255},${(n >> 8) & 255},${n & 255},${a})`;
};
const distSeg = (px, py, a, b) => {
  const dx = b.x - a.x, dy = b.y - a.y, L = dx * dx + dy * dy;
  let t = L ? ((px - a.x) * dx + (py - a.y) * dy) / L : 0;
  t = Math.max(0, Math.min(1, t));
  return Math.hypot(px - (a.x + t * dx), py - (a.y + t * dy));
};
const far = (a, b, k) => {
  const dx = b.x - a.x, dy = b.y - a.y, len = Math.hypot(dx, dy) || 1, K = k / len;
  return { x: a.x + dx * K, y: a.y + dy * K };
};
const inPoly = (p, pts) => {
  let c = false;
  for (let i = 0, j = pts.length - 1; i < pts.length; j = i++) {
    if (pts[i].y > p.y !== pts[j].y > p.y && p.x < ((pts[j].x - pts[i].x) * (p.y - pts[i].y)) / (pts[j].y - pts[i].y) + pts[i].x) c = !c;
  }
  return c;
};
const uid = () => Math.random().toString(36).slice(2, 9);
const fmtDur = (s) => {
  s = Math.abs(Math.round(s));
  const d = Math.floor(s / 86400), h = Math.floor((s % 86400) / 3600), m = Math.floor((s % 3600) / 60);
  return d ? `${d}n ${h}g` : h ? `${h}g ${m}p` : `${m}p`;
};

export class DrawingEngine {
  constructor({ container, onChange, onSelect, onToolDone, onEditText }) {
    this.el = container;
    this.onChange = onChange || (() => {});
    this.onSelect = onSelect || (() => {});
    this.onToolDone = onToolDone || (() => {});
    this.onEditText = onEditText || (() => {});
    this.future = [];
    this.drawings = [];
    this.draft = null;
    this.selectedId = null;
    this.hoverId = null;
    this.tool = "cursor";
    this.magnet = false;
    this.visible = true;
    this.T = []; this.bars = []; this.step = 3600;
    this.fmt = (p) => String(p);
    this.colors = { fg: "#d6dfeb", panel: "#0e141c", muted: "#8191a5" };
    this.history = [];
    this.drag = null;
    this.swallow = false;
    this.chart = null; this.series = null; this.req = () => {};
    this.prim = {
      attached: (p) => { this.chart = p.chart; this.series = p.series; this.req = p.requestUpdate; },
      detached: () => { this.req = () => {}; },
      updateAllViews: () => {},
      paneViews: () => [this.view],
    };
    this.view = {
      zOrder: () => "top",
      renderer: () => ({ draw: (target) => target.useMediaCoordinateSpace(({ context, mediaSize }) => this.paint(context, mediaSize.width, mediaSize.height)) }),
    };
    this._bind();
  }

  // ---------- vòng đời ----------
  attach(chart, series) {
    this.detach();
    this.chart = chart; this.series = series;
    series.attachPrimitive(this.prim);
    this.attachedSeries = series;
  }
  detach() {
    try { this.attachedSeries?.detachPrimitive(this.prim); } catch { /* series đã bị gỡ */ }
    this.attachedSeries = null;
  }
  destroy() {
    this.detach();
    this._unbind();
  }
  redraw() { this.req(); }

  // ---------- cấu hình ----------
  setBars(bars, stepSec) {
    this.bars = bars; this.T = bars.map((b) => b.t); this.step = stepSec || 3600;
    this.redraw();
  }
  setFormatter(fn) { this.fmt = fn; }
  setColors(c) { this.colors = c; this.redraw(); }
  setMagnet(v) { this.magnet = !!v; }
  /** Chế độ thụ động (replay chọn nến): không chọn/kéo hình vẽ, để sự kiện chuột đi tới biểu đồ. */
  setPassive(v) { this.passive = !!v; if (v) { this.draft = null; this.hoverId = null; this.el.classList.remove("pc-hit"); } this.redraw(); }
  setVisible(v) { this.visible = !!v; if (!v) this._select(null); this.redraw(); }
  setTool(id) {
    this.tool = TOOL[id] ? id : "cursor";
    this.draft = null;
    this.el.classList.toggle("pc-draw", this.tool !== "cursor");
    this.redraw();
  }
  load(list) {
    this.drawings = Array.isArray(list) ? list.filter((d) => TOOL[d?.type] && Array.isArray(d.pts)) : [];
    this.history = []; this.future = []; this.draft = null; this._select(null);
    this.redraw();
  }
  get() { return this.drawings; }
  /** Nạp lại KHÔNG xoá lịch sử (đồng bộ từ máy chủ). */
  replace(list) {
    this.drawings = Array.isArray(list) ? list.filter((d) => TOOL[d?.type] && Array.isArray(d.pts)) : [];
    if (this.selectedId && !this.selected()) this._select(null);
    this.redraw();
  }
  find(id) { return this.drawings.find((d) => d.id === id) || null; }
  /** Sửa bất kỳ hình theo id (đổi tên/khoá/ẩn/màu) và ghi lịch sử để Undo. */
  patch(id, patch, styleOnly) {
    const d = this.find(id);
    if (!d) return;
    this._push();
    if (styleOnly) d.style = { ...d.style, ...patch }; else Object.assign(d, patch);
    if (this.selectedId === id) this.onSelect({ ...d });
    this._commit();
  }
  remove(id) {
    if (!this.find(id)) return;
    this._push();
    this.drawings = this.drawings.filter((d) => d.id !== id);
    if (this.selectedId === id) this._select(null);
    this._commit();
  }
  select(id) { this._select(id); this.redraw(); }
  duplicateSelected() {
    const d = this.selected();
    if (!d) return;
    this._push();
    const dt = this.step * 3, nd = { ...JSON.parse(JSON.stringify(d)), id: uid(), locked: false };
    nd.pts = nd.pts.map((p) => ({ t: p.t + dt, p: p.p }));
    this.drawings.push(nd);
    this._select(nd.id);
    this._commit();
  }
  selected() { return this.drawings.find((d) => d.id === this.selectedId) || null; }

  // ---------- thao tác ----------
  _push() { this.history.push(JSON.stringify(this.drawings)); if (this.history.length > 60) this.history.shift(); this.future = []; }
  _commit() { this.onChange(this.drawings); this.redraw(); }
  undo() {
    const s = this.history.pop();
    if (s == null) return;
    this.future.push(JSON.stringify(this.drawings));
    this.drawings = JSON.parse(s);
    if (!this.selected()) this._select(null);
    this._commit();
  }
  redo() {
    const s = this.future.pop();
    if (s == null) return;
    this.history.push(JSON.stringify(this.drawings));
    this.drawings = JSON.parse(s);
    if (!this.selected()) this._select(null);
    this._commit();
  }
  canUndo() { return this.history.length > 0; }
  canRedo() { return this.future.length > 0; }
  removeSelected() {
    if (!this.selectedId || this.selected()?.locked) return;
    this._push();
    this.drawings = this.drawings.filter((d) => d.id !== this.selectedId);
    this._select(null);
    this._commit();
  }
  clearAll() {
    if (!this.drawings.length) return;
    this._push();
    this.drawings = [];
    this._select(null);
    this._commit();
  }
  patchSelected(patch) {
    const d = this.selected();
    if (!d || d.locked) return;
    this._push();
    d.style = { ...d.style, ...patch };
    this.onSelect({ ...d });
    this._commit();
  }
  cancel() {
    if (this.draft) { this.draft = null; this.redraw(); return true; }
    if (this.tool !== "cursor") { this.setTool("cursor"); this.onToolDone(); return true; }
    if (this.selectedId) { this._select(null); this.redraw(); return true; }
    return false;
  }
  _select(id) {
    if (this.selectedId === id) return;
    this.selectedId = id;
    this.onSelect(id ? { ...this.selected() } : null);
  }

  // ---------- toạ độ ----------
  _logical(t) {
    const T = this.T, n = T.length;
    if (!n) return 0;
    if (t <= T[0]) return (t - T[0]) / this.step;
    if (t >= T[n - 1]) return n - 1 + (t - T[n - 1]) / this.step;
    let lo = 0, hi = n - 1;
    while (hi - lo > 1) { const m = (lo + hi) >> 1; if (T[m] <= t) lo = m; else hi = m; }
    return lo + (t - T[lo]) / (T[hi] - T[lo]);
  }
  _time(x) {
    const T = this.T, n = T.length;
    if (!n) return 0;
    if (x <= 0) return T[0] + x * this.step;
    if (x >= n - 1) return T[n - 1] + (x - (n - 1)) * this.step;
    const k = Math.floor(x);
    return T[k] + (x - k) * (T[k + 1] - T[k]);
  }
  _x(t) { const v = this.chart?.timeScale().logicalToCoordinate(this._logical(t)); return v == null ? null : v; }
  _y(p) { const v = this.series?.priceToCoordinate(p); return v == null ? null : v; }
  _scr(pt) { const x = this._x(pt.t), y = this._y(pt.p); return x == null || y == null ? null : { x, y }; }
  _size() {
    try { const s = this.chart.paneSize(0); if (s?.width) return { w: s.width, h: s.height }; } catch { /* phiên bản cũ */ }
    return { w: Math.max(0, this.el.clientWidth - 60), h: this.el.clientHeight };
  }
  _lw() { try { const o = this.chart.priceScale("left"); return o.options().visible ? o.width() : 0; } catch { return 0; } }
  _pos(e) { const r = this.el.getBoundingClientRect(); return { x: e.clientX - r.left - this._lw(), y: e.clientY - r.top }; }
  _inPane(p) { const s = this._size(); return p.x >= 0 && p.y >= 0 && p.x <= s.w && p.y <= s.h; }
  /** vị trí màn hình -> điểm (t,p); nam châm gắn vào OHLC của nến gần nhất nếu đủ gần */
  _point(pos, snap = true) {
    const lg = this.chart.timeScale().coordinateToLogical(pos.x);
    let t = this._time(lg == null ? 0 : lg);
    let p = this.series.coordinateToPrice(pos.y);
    if (p == null) p = 0;
    if (snap && this.magnet && this.bars.length) {
      const i = Math.max(0, Math.min(this.bars.length - 1, Math.round(lg ?? 0)));
      const b = this.bars[i];
      let best = null, bd = 18;
      for (const v of [b.o, b.h, b.l, b.c]) {
        const y = this._y(v);
        if (y != null && Math.abs(y - pos.y) < bd) { bd = Math.abs(y - pos.y); best = v; }
      }
      if (best != null) { p = best; t = b.t; }
    }
    return { t, p };
  }

  // ---------- hình học (dùng chung cho vẽ + chạm) ----------
  _geom(d, W, H) {
    const S = d.pts.map((p) => this._scr(p));
    if (S.some((s) => !s)) return null;
    const a = S[0], b = S[1], big = (W + H) * 3;
    const shapes = [];
    switch (d.type) {
      case "trend": if (b) shapes.push({ k: "seg", a, b }); break;
      case "ray": if (b) shapes.push({ k: "seg", a, b: far(a, b, big) }); break;
      case "extended": if (b) shapes.push({ k: "seg", a: far(b, a, big), b: far(a, b, big) }); break;
      case "hline": shapes.push({ k: "seg", a: { x: 0, y: a.y }, b: { x: W, y: a.y } }); break;
      case "vline": shapes.push({ k: "seg", a: { x: a.x, y: 0 }, b: { x: a.x, y: H } }); break;
      case "rect": if (b) shapes.push({ k: "rect", x1: Math.min(a.x, b.x), y1: Math.min(a.y, b.y), x2: Math.max(a.x, b.x), y2: Math.max(a.y, b.y) }); break;
      case "channel": {
        if (!b) break;
        shapes.push({ k: "seg", a, b });
        const c = S[2];
        if (c) {
          const dx = b.x - a.x, yl = dx ? a.y + ((b.y - a.y) * (c.x - a.x)) / dx : a.y, off = c.y - yl;
          shapes.push({ k: "seg", a: { x: a.x, y: a.y + off }, b: { x: b.x, y: b.y + off } });
          shapes.push({ k: "mid", a: { x: a.x, y: a.y + off / 2 }, b: { x: b.x, y: b.y + off / 2 } });
          shapes.push({ k: "poly", pts: [a, b, { x: b.x, y: b.y + off }, { x: a.x, y: a.y + off }] });
        }
        break;
      }
      case "fib": case "fibext": {
        if (!b) break;
        const levels = d.type === "fib" ? FIB : FIBEXT;
        const p1 = d.pts[0].p, p2 = d.pts[1].p;
        let base, delta;
        if (d.type === "fib") { base = p2; delta = p1 - p2; } // 0 tại điểm cuối, 1 tại điểm đầu
        else {
          const c = d.pts[2];
          if (!c) { shapes.push({ k: "seg", a, b, dashed: true }); break; }
          base = c.p; delta = p2 - p1;
          shapes.push({ k: "seg", a, b, dashed: true });
          shapes.push({ k: "seg", a: b, b: S[2], dashed: true });
        }
        const x1 = Math.min(a.x, b.x), x2 = d.style?.extend === false ? Math.max(a.x, b.x) : W;
        levels.forEach((r, i) => {
          const price = base + delta * r, y = this._y(price);
          if (y == null) return;
          shapes.push({ k: "level", a: { x: x1, y }, b: { x: Math.max(x2, x1 + 1), y }, r, price, color: FIB_COL[i % FIB_COL.length], i });
        });
        if (d.type === "fib") shapes.push({ k: "seg", a, b, dashed: true });
        break;
      }
      case "ruler": if (b) shapes.push({ k: "rect", x1: Math.min(a.x, b.x), y1: Math.min(a.y, b.y), x2: Math.max(a.x, b.x), y2: Math.max(a.y, b.y), ruler: true }, { k: "seg", a, b }); break;
      default: shapes.push(...geomExtra(this, d, S, W, H)); break;
    }
    return { S, shapes };
  }
  _hit(pos) {
    const s = this._size();
    for (let i = this.drawings.length - 1; i >= 0; i--) {
      const d = this.drawings[i];
      if (d.hidden) continue;
      const g = this._geom(d, s.w, s.h);
      if (!g) continue;
      if (d.id === this.selectedId && !d.locked) {
        for (let k = 0; k < g.S.length; k++) if (Math.hypot(pos.x - g.S[k].x, pos.y - g.S[k].y) <= 10) return { d, handle: k };
      }
      for (const sh of g.shapes) {
        if (sh.k === "seg" || sh.k === "level" || sh.k === "mid") { if (distSeg(pos.x, pos.y, sh.a, sh.b) <= 6) return { d, handle: -1 }; }
        else if (sh.k === "rect") {
          if (d.type === "rect" || sh.ruler || sh.hit) { if (pos.x >= sh.x1 - 4 && pos.x <= sh.x2 + 4 && pos.y >= sh.y1 - 4 && pos.y <= sh.y2 + 4) return { d, handle: -1 }; }
        } else if (sh.k === "poly" && sh.hit) {
          if (inPoly(pos, sh.pts)) return { d, handle: -1 };
        } else if (sh.k === "path") {
          for (let q = 1; q < sh.pts.length; q++) if (distSeg(pos.x, pos.y, sh.pts[q - 1], sh.pts[q]) <= 6) return { d, handle: -1 };
        } else if (sh.k === "arc") {
          if (Math.abs(Math.hypot(pos.x - sh.cx, pos.y - sh.cy) - sh.r) <= 6) return { d, handle: -1 };
        } else if (sh.k === "vline") {
          if (Math.abs(pos.x - sh.x) <= 5) return { d, handle: -1 };
        }
      }
    }
    return null;
  }

  // ---------- vẽ ----------
  paint(ctx, W, H) {
    if (!this.visible || !this.chart || !this.series) return;
    const list = this.draft ? [...this.drawings, this._draftDrawing()].filter(Boolean) : this.drawings;
    for (const d of list) if (!d.hidden) this._paintOne(ctx, d, W, H);
    const sel = this.drawings.find((d) => d.id === this.selectedId);
    if (sel && !sel.hidden && !sel.locked) {
      const g = this._geom(sel, W, H);
      if (g) for (const p of g.S) {
        ctx.beginPath(); ctx.arc(p.x, p.y, 4.5, 0, Math.PI * 2);
        ctx.fillStyle = this.colors.panel; ctx.fill();
        ctx.lineWidth = 2; ctx.strokeStyle = sel.style?.color || "#5aa9ff"; ctx.stroke();
      }
    }
  }
  _draftDrawing() {
    const dr = this.draft;
    if (!dr) return null;
    const pts = dr.cur ? [...dr.pts, dr.cur] : dr.pts;
    return { id: "__draft", type: dr.type, pts, style: { color: DEFAULT_COLOR[dr.type], width: 1.5 }, draft: true };
  }
  _label(ctx, text, x, y, color, align = "left") {
    ctx.font = "11px 'Inter Variable', system-ui, sans-serif";
    const w = ctx.measureText(text).width + 8;
    const rx = align === "right" ? x - w : x;
    ctx.fillStyle = hexA(this.colors.panel, 0.85); ctx.fillRect(rx, y - 8, w, 16);
    ctx.fillStyle = color || this.colors.fg; ctx.textBaseline = "middle"; ctx.textAlign = "left";
    ctx.fillText(text, rx + 4, y);
  }
  _paintOne(ctx, d, W, H) {
    const g = this._geom(d, W, H);
    if (!g) return;
    const st = d.style || {}, col = st.color || DEFAULT_COLOR[d.type] || "#5aa9ff";
    const isSel = d.id === this.selectedId || d.id === this.hoverId;
    ctx.save();
    ctx.beginPath(); ctx.rect(0, 0, W, H); ctx.clip();
    ctx.lineWidth = (st.width || 1.5) + (isSel ? 0.5 : 0);
    ctx.strokeStyle = col; ctx.lineJoin = "round"; ctx.lineCap = "round";
    ctx.setLineDash(st.dash ? [6, 4] : []);
    // nền trước (poly / rect)
    for (const sh of g.shapes) {
      if (sh.k === "poly") { ctx.beginPath(); sh.pts.forEach((p, i) => (i ? ctx.lineTo(p.x, p.y) : ctx.moveTo(p.x, p.y))); ctx.closePath(); ctx.fillStyle = hexA(col, sh.fill || 0.1); ctx.fill(); }
      if (sh.k === "rect" && !sh.ruler && !sh.zone && !sh.box && !sh.frame) { ctx.fillStyle = hexA(col, 0.12); ctx.fillRect(sh.x1, sh.y1, sh.x2 - sh.x1, sh.y2 - sh.y1); ctx.strokeRect(sh.x1, sh.y1, sh.x2 - sh.x1, sh.y2 - sh.y1); }
    }
    if (d.type === "fib" || d.type === "fibext") {
      const lv = g.shapes.filter((s) => s.k === "level");
      for (let i = 1; i < lv.length; i++) {
        ctx.fillStyle = hexA(lv[i - 1].color, 0.07);
        ctx.fillRect(lv[i].a.x, Math.min(lv[i].a.y, lv[i - 1].a.y), lv[i].b.x - lv[i].a.x, Math.abs(lv[i].a.y - lv[i - 1].a.y));
      }
      for (const s of lv) {
        ctx.setLineDash([]); ctx.strokeStyle = s.color; ctx.lineWidth = 1;
        ctx.beginPath(); ctx.moveTo(s.a.x, s.a.y); ctx.lineTo(s.b.x, s.b.y); ctx.stroke();
        this._label(ctx, `${s.r} (${this.fmt(s.price)})`, Math.max(2, s.a.x), s.a.y - 9, s.color);
      }
    }
    ctx.strokeStyle = col; ctx.lineWidth = (st.width || 1.5) + (isSel ? 0.5 : 0);
    for (const sh of g.shapes) {
      if (sh.k === "seg" || sh.k === "mid") {
        ctx.setLineDash(sh.dashed || sh.proj || sh.k === "mid" || st.dash ? [6, 4] : []);
        if (sh.k === "mid") ctx.globalAlpha = 0.6;
        if (sh.color) ctx.strokeStyle = sh.color;
        if (sh.thin) ctx.lineWidth = Math.max(1, ((st.width || 1.5) + (isSel ? 0.5 : 0)) * 0.7);
        ctx.beginPath(); ctx.moveTo(sh.a.x, sh.a.y); ctx.lineTo(sh.b.x, sh.b.y); ctx.stroke();
        ctx.globalAlpha = 1; ctx.strokeStyle = col; ctx.lineWidth = (st.width || 1.5) + (isSel ? 0.5 : 0);
      }
    }
    ctx.setLineDash([]);
    paintExtra(this, ctx, d, g, col, W, H);
    if (d.type === "hline") this._label(ctx, this.fmt(d.pts[0].p), W - 4, g.S[0].y, col, "right");
    if (d.type === "ruler" && g.S[1]) this._paintRuler(ctx, d, g);
    ctx.restore();
  }
  _paintRuler(ctx, d, g) {
    const [a, b] = g.S, p1 = d.pts[0], p2 = d.pts[1];
    const dp = p2.p - p1.p, pc = p1.p ? (dp / p1.p) * 100 : 0, up = dp >= 0;
    const col = up ? "#2bd08f" : "#ff5c7a";
    const sh = g.shapes.find((s) => s.ruler);
    ctx.fillStyle = hexA(col, 0.12); ctx.fillRect(sh.x1, sh.y1, sh.x2 - sh.x1, sh.y2 - sh.y1);
    ctx.strokeStyle = col; ctx.lineWidth = 1; ctx.strokeRect(sh.x1, sh.y1, sh.x2 - sh.x1, sh.y2 - sh.y1);
    ctx.strokeStyle = col; ctx.lineWidth = 1.5; ctx.beginPath(); ctx.moveTo(a.x, a.y); ctx.lineTo(b.x, b.y); ctx.stroke();
    const bars = Math.round(this._logical(p2.t) - this._logical(p1.t));
    const l1 = `${dp >= 0 ? "+" : ""}${this.fmt(dp).replace(/^-/, "−")} (${pc >= 0 ? "+" : ""}${pc.toFixed(2)}%)`;
    const l2 = `${bars >= 0 ? "" : "−"}${Math.abs(bars)} nến · ${fmtDur(p2.t - p1.t)}`;
    const cx = (sh.x1 + sh.x2) / 2, cy = up ? sh.y1 - 22 : sh.y2 + 22;
    this._label(ctx, l1, cx - 60, cy - 9, col);
    this._label(ctx, l2, cx - 60, cy + 9, this.colors.muted);
  }

  // ---------- chuột / cảm ứng ----------
  _bind() {
    const el = this.el;
    this._h = {
      down: (e) => this._down(e),
      move: (e) => this._move(e),
      up: () => this._up(),
      block: (e) => { if (this.swallow) { e.stopPropagation(); if (e.cancelable && e.type === "touchstart") e.preventDefault(); } },
      leave: () => { if (this.hoverId) { this.hoverId = null; el.classList.remove("pc-hit"); this.redraw(); } },
      dbl: (e) => { if (this.tool === "cursor" && this._hitAt(e)) { e.stopPropagation(); } },
      dblclick: (e) => { const h = this.tool === "cursor" ? this._hitAt(e) : null; if (h && NEEDS_TEXT.has(h.d.type)) { e.stopPropagation(); this.onEditText({ ...h.d }); } },
    };
    el.addEventListener("pointerdown", this._h.down, true);
    el.addEventListener("pointermove", this._h.move, true);
    el.addEventListener("pointerleave", this._h.leave, true);
    el.addEventListener("dblclick", this._h.dblclick, true);
    el.addEventListener("mousedown", this._h.block, true);
    el.addEventListener("touchstart", this._h.block, { capture: true, passive: false });
    window.addEventListener("pointerup", this._h.up, true);
    window.addEventListener("pointercancel", this._h.up, true);
  }
  _unbind() {
    const el = this.el, h = this._h;
    el.removeEventListener("pointerdown", h.down, true);
    el.removeEventListener("pointermove", h.move, true);
    el.removeEventListener("pointerleave", h.leave, true);
    el.removeEventListener("dblclick", h.dblclick, true);
    el.removeEventListener("mousedown", h.block, true);
    el.removeEventListener("touchstart", h.block, { capture: true });
    window.removeEventListener("pointerup", h.up, true);
    window.removeEventListener("pointercancel", h.up, true);
  }
  _hitAt(e) { const p = this._pos(e); return this._inPane(p) ? this._hit(p) : null; }
  _swallow(e) { this.swallow = true; e.stopPropagation(); }

  _down(e) {
    if (!this.visible || this.passive || !this.chart || e.button !== 0) return;
    // thanh style nổi / nút nằm ngoài vùng biểu đồ: bỏ qua
    if (e.target.closest?.("[data-pc-ui]")) return;
    const pos = this._pos(e);
    if (!this._inPane(pos)) return;
    if (this.tool !== "cursor") {
      this._swallow(e);
      const pt = this._point(pos);
      if (!this.draft) this.draft = { type: this.tool, pts: [pt], cur: pt };
      else this.draft.pts.push(pt);
      const need = TOOL[this.tool].pts;
      if (this.draft.pts.length >= need) {
        this._push();
        const d = { id: uid(), type: this.draft.type, pts: this.draft.pts, style: { color: DEFAULT_COLOR[this.draft.type], width: 1.5, dash: false } };
        if (NEEDS_TEXT.has(d.type)) d.name = d.type === "note" ? "Ghi chú" : "Văn bản";
        this.drawings.push(d);
        this.draft = null;
        this.setTool("cursor");
        this._select(d.id);
        this.onToolDone();
        this._commit();
        if (NEEDS_TEXT.has(d.type)) this.onEditText({ ...d });
      } else this.redraw();
      return;
    }
    const hit = this._hit(pos);
    if (hit) {
      this._swallow(e);
      this._select(hit.d.id);
      if (hit.d.locked) { this.redraw(); return; }
      const lg = this.chart.timeScale().coordinateToLogical(pos.x) ?? 0;
      this.drag = {
        id: hit.d.id, handle: hit.handle, moved: false,
        lg0: lg, p0: this.series.coordinateToPrice(pos.y) ?? 0,
        orig: hit.d.pts.map((p) => ({ ...p })),
      };
      window.addEventListener("pointermove", this._h.move, true);
      this.redraw();
    } else if (this.selectedId) { this._select(null); this.redraw(); }
  }
  _move(e) {
    if (!this.chart) return;
    const pos = this._pos(e);
    if (this.drag) {
      const d = this.drawings.find((x) => x.id === this.drag.id);
      if (!d) return;
      if (!this.drag.moved) { this._pushPre(); this.drag.moved = true; }
      if (this.drag.handle >= 0) {
        const pt = this._point(pos);
        if (d.type === "hline") d.pts[0] = { t: d.pts[0].t, p: pt.p };
        else if (d.type === "vline") d.pts[0] = { t: pt.t, p: d.pts[0].p };
        else d.pts[this.drag.handle] = pt;
      } else {
        const lg = this.chart.timeScale().coordinateToLogical(pos.x) ?? this.drag.lg0;
        const p = this.series.coordinateToPrice(pos.y) ?? this.drag.p0;
        const dl = lg - this.drag.lg0, dp = p - this.drag.p0;
        d.pts = this.drag.orig.map((o) => ({
          t: d.type === "hline" ? o.t : this._time(this._logical(o.t) + dl),
          p: d.type === "vline" ? o.p : o.p + dp,
        }));
      }
      this.onSelect({ ...d });
      this.redraw();
      return;
    }
    if (this.draft) {
      this.draft.cur = this._inPane(pos) ? this._point(pos) : this.draft.cur;
      this.redraw();
      return;
    }
    if (this.tool === "cursor" && this.visible && !this.passive) {
      const hit = this._inPane(pos) ? this._hit(pos) : null;
      const id = hit?.d.id || null;
      if (id !== this.hoverId) { this.hoverId = id; this.el.classList.toggle("pc-hit", !!id); this.redraw(); }
    }
  }
  _pushPre() { if (this.drag) { const cur = this.drawings.map((d) => (d.id === this.drag.id ? { ...d, pts: this.drag.orig } : d)); this.history.push(JSON.stringify(cur)); this.future = []; if (this.history.length > 60) this.history.shift(); } }
  _up() {
    if (this.drag) {
      const moved = this.drag.moved;
      this.drag = null;
      window.removeEventListener("pointermove", this._h.move, true);
      if (moved) this._commit();
    }
    if (this.swallow) setTimeout(() => { this.swallow = false; }, 0);
  }
}
