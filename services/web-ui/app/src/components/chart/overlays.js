// Lớp phủ trên biểu đồ (Series Primitive của lightweight-charts): vùng phiên Tokyo/London/New York/VN + đường mở/đóng phiên,
// sự kiện lịch kinh tế HIGH + tin quan trọng trên trục thời gian, đường CẢNH BÁO GIÁ của người dùng (kéo để đổi giá / bấm để tạo),
// và ký hiệu X/O của Point & Figure. Chỉ vẽ + sự kiện chuột; mọi thay đổi (tạo/sửa cảnh báo) do trang cha gọi API /v1/user/rules.
const hexA = (hex, a) => {
  const m = /^#([0-9a-f]{6})$/i.exec(hex || "");
  if (!m) return hex;
  const n = parseInt(m[1], 16);
  return `rgba(${(n >> 16) & 255},${(n >> 8) & 255},${n & 255},${a})`;
};

export const SESSIONS = [
  { id: "tokyo", label: "Tokyo", tz: "Asia/Tokyo", open: [9, 0], close: [18, 0], color: "#5aa9ff" },
  { id: "london", label: "London", tz: "Europe/London", open: [8, 0], close: [16, 30], color: "#f0b84f" },
  { id: "newyork", label: "New York", tz: "America/New_York", open: [8, 0], close: [17, 0], color: "#2bd08f" },
  { id: "vn", label: "Phiên VN", tz: "Asia/Ho_Chi_Minh", open: [9, 0], close: [15, 0], color: "#ff5c7a" },
];

const dtf = {};
function offsetMs(tz, utcMs) {
  const f = dtf[tz] || (dtf[tz] = new Intl.DateTimeFormat("en-US", { timeZone: tz, hourCycle: "h23", year: "numeric", month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit", second: "2-digit" }));
  const o = {};
  for (const p of f.formatToParts(new Date(utcMs))) o[p.type] = Number(p.value);
  return Date.UTC(o.year, o.month - 1, o.day, o.hour, o.minute, o.second) - Math.floor(utcMs / 1000) * 1000;
}
/** Epoch (giây) của giờ địa phương y-m-d hh:mm trong múi giờ tz (xử lý DST). */
export function zonedEpoch(tz, y, m, d, hh, mm) {
  const guess = Date.UTC(y, m, d, hh, mm);
  let t = guess - offsetMs(tz, guess);
  t = guess - offsetMs(tz, t);
  return Math.floor(t / 1000);
}

export class OverlayEngine {
  constructor({ container, onAlertMove, onAlertCreate, onHover }) {
    this.el = container;
    this.cb = { onAlertMove: onAlertMove || (() => {}), onAlertCreate: onAlertCreate || (() => {}), onHover: onHover || (() => {}) };
    this.s = {
      sessions: { on: false, ids: ["tokyo", "london", "newyork"], lines: true }, T: [], step: 3600, tfSec: 3600,
      marks: [], alerts: [], alertMode: false, pnf: null, fmt: (p) => String(p),
      colors: { up: "#2bd08f", down: "#ff5c7a", fg: "#d6dfeb", panel: "#0e141c", muted: "#8191a5", accent: "#f0b84f", line: "#243040" },
    };
    this.chart = null; this.series = null; this.req = () => {};
    this.drag = null; this.swallow = false; this.hoverKey = null;
    this.prim = {
      attached: (p) => { this.chart = p.chart; this.series = p.series; this.req = p.requestUpdate; },
      detached: () => { this.req = () => {}; },
      updateAllViews: () => {},
      paneViews: () => [this.bottomView, this.topView],
    };
    const mk = (z, fn) => ({ zOrder: () => z, renderer: () => ({ draw: (target) => target.useMediaCoordinateSpace(({ context, mediaSize }) => fn.call(this, context, mediaSize.width, mediaSize.height)) }) });
    this.bottomView = mk("bottom", this.paintBottom);
    this.topView = mk("top", this.paintTop);
    this._bind();
  }
  attach(chart, series) { this.detach(); this.chart = chart; this.series = series; series.attachPrimitive(this.prim); this.attached = series; }
  detach() { try { this.attached?.detachPrimitive(this.prim); } catch { /* series đã gỡ */ } this.attached = null; }
  destroy() { this.detach(); this._unbind(); }
  set(patch) {
    if (patch.T) this.s.T = patch.T;
    Object.assign(this.s, patch);
    this.req();
  }
  redraw() { this.req(); }

  // ---------- toạ độ ----------
  _logical(t) {
    const T = this.s.T, n = T.length, st = this.s.step;
    if (!n) return 0;
    if (t <= T[0]) return (t - T[0]) / st;
    if (t >= T[n - 1]) return n - 1 + (t - T[n - 1]) / st;
    let lo = 0, hi = n - 1;
    while (hi - lo > 1) { const m = (lo + hi) >> 1; if (T[m] <= t) lo = m; else hi = m; }
    return lo + (t - T[lo]) / (T[hi] - T[lo]);
  }
  _x(t) { const v = this.chart?.timeScale().logicalToCoordinate(this._logical(t)); return v == null ? null : v; }
  _y(p) { const v = this.series?.priceToCoordinate(p); return v == null ? null : v; }
  _timeAt(x) {
    const T = this.s.T, n = T.length, lg = this.chart?.timeScale().coordinateToLogical(x);
    if (!n || lg == null) return null;
    if (lg <= 0) return T[0] + lg * this.s.step;
    if (lg >= n - 1) return T[n - 1] + (lg - (n - 1)) * this.s.step;
    const k = Math.floor(lg);
    return T[k] + (lg - k) * (T[k + 1] - T[k]);
  }
  _size() {
    try { const z = this.chart.paneSize(0); if (z?.width) return { w: z.width, h: z.height }; } catch { /* cũ */ }
    return { w: Math.max(0, this.el.clientWidth - 60), h: this.el.clientHeight };
  }

  // ---------- vẽ ----------
  paintBottom(ctx, W, H) {
    const { sessions, T, tfSec } = this.s;
    if (!this.chart || !sessions.on || !T.length || tfSec > 14400 || this.s.nonTime) return;
    const t0 = this._timeAt(0), t1 = this._timeAt(W);
    if (t0 == null || t1 == null) return;
    const days = (t1 - t0) / 86400;
    if (days > 90) return;
    const list = SESSIONS.filter((x) => sessions.ids.includes(x.id));
    const d0 = new Date((t0 - 86400) * 1000), d1 = (t1 + 86400) * 1000;
    ctx.save();
    ctx.font = "10.5px 'Inter Variable', system-ui, sans-serif"; ctx.textBaseline = "top";
    const cur = new Date(Date.UTC(d0.getUTCFullYear(), d0.getUTCMonth(), d0.getUTCDate()));
    const rows = {};
    for (let guard = 0; cur.getTime() <= d1 && guard < 200; guard++, cur.setUTCDate(cur.getUTCDate() + 1)) {
      const dow = cur.getUTCDay();
      if (dow === 0 || dow === 6) continue;
      const y = cur.getUTCFullYear(), m = cur.getUTCMonth(), dd = cur.getUTCDate();
      list.forEach((ss, idx) => {
        const a = zonedEpoch(ss.tz, y, m, dd, ss.open[0], ss.open[1]), b = zonedEpoch(ss.tz, y, m, dd, ss.close[0], ss.close[1]);
        const x1 = this._x(a), x2 = this._x(b);
        if (x1 == null || x2 == null || x2 < 0 || x1 > W) return;
        ctx.fillStyle = hexA(ss.color, 0.05);
        ctx.fillRect(x1, 0, x2 - x1, H);
        if (sessions.lines) {
          ctx.strokeStyle = hexA(ss.color, 0.55); ctx.lineWidth = 1;
          ctx.setLineDash([]); ctx.beginPath(); ctx.moveTo(Math.round(x1) + 0.5, 0); ctx.lineTo(Math.round(x1) + 0.5, H); ctx.stroke();
          ctx.setLineDash([3, 4]); ctx.beginPath(); ctx.moveTo(Math.round(x2) + 0.5, 0); ctx.lineTo(Math.round(x2) + 0.5, H); ctx.stroke(); ctx.setLineDash([]);
        }
        const ly = 3 + idx * 12;
        if (x2 - x1 > 46 && (rows[idx] == null || x1 > rows[idx] + 4)) {
          ctx.fillStyle = hexA(ss.color, 0.95); ctx.fillText(ss.label, Math.max(2, x1 + 3), ly);
          rows[idx] = x1 + ctx.measureText(ss.label).width + 3;
        }
      });
    }
    ctx.restore();
  }

  paintTop(ctx, W, H) {
    if (!this.chart || !this.series) return;
    const c = this.s.colors;
    ctx.save();
    ctx.beginPath(); ctx.rect(0, 0, W, H); ctx.clip();
    // ---- Point & Figure ----
    const pnf = this.s.pnf;
    if (pnf?.cols?.length) {
      const sp = this.chart.timeScale().options().barSpacing || 8;
      const bw = Math.max(3, Math.min(28, sp * 0.86));
      ctx.lineWidth = Math.max(1, Math.min(2, bw / 8));
      for (const col of pnf.cols) {
        const x = this._x(col.t);
        if (x == null || x < -bw || x > W + bw) continue;
        for (let p = col.lo; p <= col.hi + pnf.box * 0.001; p += pnf.box) {
          const yTop = this._y(p + pnf.box), yBot = this._y(p);
          if (yTop == null || yBot == null) continue;
          const h = Math.abs(yBot - yTop), cy = (yTop + yBot) / 2, r = Math.max(2, Math.min(bw, h) * 0.42);
          if (col.dir > 0) {
            ctx.strokeStyle = c.up; ctx.beginPath();
            ctx.moveTo(x - r, cy - r); ctx.lineTo(x + r, cy + r); ctx.moveTo(x + r, cy - r); ctx.lineTo(x - r, cy + r); ctx.stroke();
          } else { ctx.strokeStyle = c.down; ctx.beginPath(); ctx.arc(x, cy, r, 0, Math.PI * 2); ctx.stroke(); }
        }
      }
    }
    // ---- sự kiện lịch HIGH / tin ----
    const marks = this.s.marks;
    let lastLabelEnd = -1e9;
    ctx.font = "10.5px 'Inter Variable', system-ui, sans-serif"; ctx.textBaseline = "middle";
    this._markBoxes = [];
    for (const mk of marks) {
      const x = this._x(mk.t);
      if (x == null || x < 0 || x > W) continue;
      if (mk.kind === "event") {
        ctx.strokeStyle = hexA(mk.color, 0.55); ctx.lineWidth = 1; ctx.setLineDash([2, 4]);
        ctx.beginPath(); ctx.moveTo(Math.round(x) + 0.5, 16); ctx.lineTo(Math.round(x) + 0.5, H); ctx.stroke(); ctx.setLineDash([]);
        const text = mk.short, w = ctx.measureText(text).width + 8;
        const show = x - 4 > lastLabelEnd;
        ctx.fillStyle = hexA(mk.color, show ? 0.92 : 0.7);
        ctx.beginPath();
        if (show) {
          ctx.rect(x - 1, 2, w, 14); ctx.fill(); ctx.fillStyle = "#101418"; ctx.fillText(text, x + 3, 9.5);
          lastLabelEnd = x + w;
          this._markBoxes.push({ x1: x - 1, x2: x + w, y1: 2, y2: 16, mk });
        } else { ctx.rect(x - 1, 2, 3, 14); ctx.fill(); this._markBoxes.push({ x1: x - 3, x2: x + 4, y1: 2, y2: 16, mk }); }
      } else {
        const y = H - 12;
        ctx.fillStyle = hexA(mk.color, 0.9); ctx.beginPath();
        ctx.moveTo(x, y - 5); ctx.lineTo(x + 4, y); ctx.lineTo(x, y + 5); ctx.lineTo(x - 4, y); ctx.closePath(); ctx.fill();
        this._markBoxes.push({ x1: x - 6, x2: x + 6, y1: y - 7, y2: y + 7, mk });
      }
    }
    // ---- cảnh báo giá ----
    for (const a of this.s.alerts) {
      const price = this.drag?.id === a.id ? this.drag.price : a.price;
      const y = this._y(price);
      if (y == null || y < -2 || y > H + 2) continue;
      const col = a.color || c.accent;
      ctx.strokeStyle = col; ctx.lineWidth = 1.2; ctx.setLineDash([7, 4]);
      ctx.beginPath(); ctx.moveTo(0, Math.round(y) + 0.5); ctx.lineTo(W, Math.round(y) + 0.5); ctx.stroke(); ctx.setLineDash([]);
      const text = `Cảnh báo ${a.label ? a.label + " · " : ""}${this.s.fmt(price)}`;
      const w = ctx.measureText(text).width + 22;
      ctx.fillStyle = hexA(c.panel, 0.92); ctx.fillRect(W - w - 4, y - 9, w, 18);
      ctx.strokeStyle = col; ctx.lineWidth = 1; ctx.strokeRect(W - w - 4 + 0.5, y - 8.5, w - 1, 17);
      // chuông
      ctx.fillStyle = col; ctx.beginPath(); ctx.arc(W - w + 6, y - 1, 4, Math.PI, 0); ctx.lineTo(W - w + 10, y + 3); ctx.lineTo(W - w + 2, y + 3); ctx.closePath(); ctx.fill();
      ctx.fillRect(W - w + 4, y + 4, 4, 1.5);
      ctx.fillStyle = c.fg; ctx.textAlign = "left"; ctx.fillText(text, W - w + 14, y);
    }
    ctx.restore();
  }

  // ---------- chuột ----------
  _bind() {
    const el = this.el;
    this._h = {
      down: (e) => this._down(e),
      move: (e) => this._move(e),
      up: () => this._up(),
      block: (e) => { if (this.swallow) { e.stopPropagation(); if (e.cancelable && e.type === "touchstart") e.preventDefault(); } },
      leave: () => { if (this.hoverKey) { this.hoverKey = null; this.cb.onHover(null); } },
    };
    el.addEventListener("pointerdown", this._h.down, true);
    el.addEventListener("pointermove", this._h.move, true);
    el.addEventListener("pointerleave", this._h.leave, true);
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
    el.removeEventListener("mousedown", h.block, true);
    el.removeEventListener("touchstart", h.block, { capture: true });
    window.removeEventListener("pointerup", h.up, true);
    window.removeEventListener("pointercancel", h.up, true);
    window.removeEventListener("pointermove", h.move, true);
  }
  _lw() { try { const o = this.chart.priceScale("left"); return o.options().visible ? o.width() : 0; } catch { return 0; } }
  _pos(e) { const r = this.el.getBoundingClientRect(); return { x: e.clientX - r.left - this._lw(), y: e.clientY - r.top }; }
  _in(p) { const s = this._size(); return p.x >= 0 && p.y >= 0 && p.x <= s.w && p.y <= s.h; }
  _hitAlert(p) {
    for (const a of this.s.alerts) { const y = this._y(a.price); if (y != null && Math.abs(y - p.y) <= 6) return a; }
    return null;
  }
  _down(e) {
    if (!this.chart || e.button !== 0 || e.target.closest?.("[data-pc-ui]")) return;
    const p = this._pos(e);
    if (!this._in(p)) return;
    if (this.s.alertMode) {
      e.stopImmediatePropagation(); e.stopPropagation(); this.swallow = true;
      const price = this.series.coordinateToPrice(p.y);
      if (price != null) this.cb.onAlertCreate(price);
      return;
    }
    const a = this._hitAlert(p);
    if (a && !this.s.noDrag) {
      e.stopImmediatePropagation(); e.stopPropagation(); this.swallow = true;
      this.drag = { id: a.id, price: a.price, moved: false };
      window.addEventListener("pointermove", this._h.move, true);
    }
  }
  _move(e) {
    if (!this.chart) return;
    const p = this._pos(e);
    if (this.drag) {
      const price = this.series.coordinateToPrice(p.y);
      if (price != null) { this.drag.price = price; this.drag.moved = true; this.redraw(); }
      return;
    }
    // hover: tooltip cho mốc sự kiện/tin + con trỏ trên đường cảnh báo
    const hit = this._markBoxes?.find((b) => p.x >= b.x1 && p.x <= b.x2 && p.y >= b.y1 && p.y <= b.y2);
    const key = hit ? `${hit.mk.kind}${hit.mk.t}${hit.mk.title}` : null;
    if (key !== this.hoverKey) { this.hoverKey = key; this.cb.onHover(hit ? { mk: hit.mk, x: p.x, y: p.y } : null); }
    const onAlert = this._in(p) && this._hitAlert(p);
    this.el.classList.toggle("pc-hit", !!onAlert);
  }
  _up() {
    if (this.drag) {
      const d = this.drag;
      this.drag = null;
      window.removeEventListener("pointermove", this._h.move, true);
      if (d.moved) this.cb.onAlertMove(d.id, d.price);
      this.redraw();
    }
    if (this.swallow) setTimeout(() => { this.swallow = false; }, 0);
  }
}
