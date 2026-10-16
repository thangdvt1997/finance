// Công cụ vẽ MỞ RỘNG (kênh hồi quy, Pitchfork, Gann fan, tam giác, sóng Elliott, vùng cung/cầu, mũi tên, văn bản, ghi chú,
// cung/vùng thời gian Fibonacci, projection, anchored VWAP, volume profile). Tách khỏi drawings.js để file gốc gọn.
// engine = DrawingEngine; mọi hàm chỉ ĐỌC engine (toạ độ, nến) và trả hình học / vẽ lên canvas.
const hexA = (hex, a) => {
  const m = /^#([0-9a-f]{6})$/i.exec(hex || "");
  if (!m) return hex;
  const n = parseInt(m[1], 16);
  return `rgba(${(n >> 16) & 255},${(n >> 8) & 255},${n & 255},${a})`;
};
const far = (a, dir, k) => { const len = Math.hypot(dir.x, dir.y) || 1; return { x: a.x + (dir.x / len) * k, y: a.y + (dir.y / len) * k }; };

export const GANN = [[1, 1 / 8, "1×8"], [1, 1 / 4, "1×4"], [1, 1 / 3, "1×3"], [1, 1 / 2, "1×2"], [1, 1, "1×1"], [1 / 2, 1, "2×1"], [1 / 3, 1, "3×1"], [1 / 4, 1, "4×1"], [1 / 8, 1, "8×1"]];
export const GANN_COL = ["#8b98a8", "#c792ea", "#5aa9ff", "#4dd0e1", "#f0b84f", "#2bd08f", "#aed581", "#ff8a5c", "#ff5c7a"];
export const FIBARC = [0.382, 0.5, 0.618, 1, 1.618];
export const FIBTIME = [0, 1, 2, 3, 5, 8, 13, 21, 34, 55];
const ELLIOTT = { elliott5: ["0", "1", "2", "3", "4", "5"], elliottabc: ["0", "A", "B", "C"] };

/** Chỉ số nến gần thời gian t nhất (từ engine.T). */
function idxOf(eng, t) {
  const T = eng.T, n = T.length;
  if (!n) return 0;
  return Math.max(0, Math.min(n - 1, Math.round(eng._logical(t))));
}

/** Hồi quy tuyến tính của giá đóng theo chỉ số trong [i0,i1]. */
export function regression(bars, i0, i1) {
  const n = i1 - i0 + 1;
  if (n < 3) return null;
  let sx = 0, sy = 0, sxx = 0, sxy = 0;
  for (let i = i0; i <= i1; i++) { const x = i - i0, y = bars[i].c; sx += x; sy += y; sxx += x * x; sxy += x * y; }
  const den = n * sxx - sx * sx;
  if (!den) return null;
  const m = (n * sxy - sx * sy) / den, a = (sy - m * sx) / n;
  let ss = 0;
  for (let i = i0; i <= i1; i++) { const e = bars[i].c - (a + m * (i - i0)); ss += e * e; }
  return { a, m, sigma: Math.sqrt(ss / n), n };
}

/** Anchored VWAP từ nến i0: mảng giá trị theo chỉ số (null trước neo). Khối lượng 0 -> trọng số bằng nhau. */
export function anchoredVwap(bars, i0) {
  const out = new Array(bars.length).fill(null);
  let pv = 0, vv = 0;
  for (let i = i0; i < bars.length; i++) {
    const b = bars[i], tp = (b.h + b.l + b.c) / 3, w = b.v > 0 ? b.v : 1;
    pv += tp * w; vv += w; out[i] = pv / vv;
  }
  return out;
}

/** Volume profile: phân bổ khối lượng mỗi nến đều theo biên độ [low, high] vào `rows` mức giá. XẤP XỈ (không có dữ liệu tick). */
export function volumeProfile(bars, i0, i1, rows) {
  let lo = Infinity, hi = -Infinity;
  for (let i = i0; i <= i1; i++) { if (bars[i].l < lo) lo = bars[i].l; if (bars[i].h > hi) hi = bars[i].h; }
  if (!(hi > lo)) return null;
  const step = (hi - lo) / rows, vol = new Array(rows).fill(0);
  for (let i = i0; i <= i1; i++) {
    const b = bars[i], w = b.v > 0 ? b.v : 1;
    const r0 = Math.max(0, Math.min(rows - 1, Math.floor((b.l - lo) / step))), r1 = Math.max(0, Math.min(rows - 1, Math.floor((b.h - lo) / step - 1e-9)));
    const k = Math.max(1, r1 - r0 + 1);
    for (let r = r0; r <= Math.max(r0, r1); r++) vol[r] += w / k;
  }
  let poc = 0, tot = 0;
  for (let r = 0; r < rows; r++) { tot += vol[r]; if (vol[r] > vol[poc]) poc = r; }
  // vùng giá trị 70%: mở rộng từ POC sang hai phía theo bên có khối lượng lớn hơn
  let a = poc, b = poc, acc = vol[poc];
  while (acc < tot * 0.7 && (a > 0 || b < rows - 1)) {
    const up = b < rows - 1 ? vol[b + 1] : -1, dn = a > 0 ? vol[a - 1] : -1;
    if (up >= dn) { b++; acc += vol[b]; } else { a--; acc += vol[a]; }
  }
  return { lo, hi, step, vol, poc, va: [a, b], max: vol[poc], total: tot };
}

/** Hình học cho các loại mở rộng. S = điểm màn hình (đã chắc chắn không null). */
export function geomExtra(eng, d, S, W, H) {
  const a = S[0], b = S[1], c = S[2], big = (W + H) * 3, shapes = [];
  const bars = eng.bars;
  switch (d.type) {
    case "regression": {
      if (!b || bars.length < 3) break;
      let i0 = idxOf(eng, Math.min(d.pts[0].t, d.pts[1].t)), i1 = idxOf(eng, Math.max(d.pts[0].t, d.pts[1].t));
      if (i1 - i0 < 2) break;
      const rg = regression(bars, i0, i1);
      if (!rg) break;
      const k = d.style?.k || 2, ext = d.style?.extend === true ? Math.min(bars.length - 1, i1 + Math.round((i1 - i0) * 0.3)) : i1;
      const at = (i, off) => ({ x: eng._x(bars[Math.min(i, bars.length - 1)].t), y: eng._y(rg.a + rg.m * (i - i0) + off) });
      const P = (off) => [at(i0, off), at(ext, off)];
      const mid = P(0), up = P(k * rg.sigma), lo = P(-k * rg.sigma);
      if ([...mid, ...up, ...lo].some((p) => p.x == null || p.y == null)) break;
      shapes.push({ k: "poly", pts: [up[0], up[1], lo[1], lo[0]], fill: 0.1 });
      shapes.push({ k: "seg", a: up[0], b: up[1] }, { k: "seg", a: lo[0], b: lo[1] }, { k: "mid", a: mid[0], b: mid[1] });
      shapes.push({ k: "tag", x: up[1].x, y: up[1].y, text: `+${k}σ` }, { k: "tag", x: lo[1].x, y: lo[1].y, text: `−${k}σ` });
      shapes.push({ k: "tag", x: mid[1].x, y: mid[1].y, text: `R-hq (${rg.n} nến) σ=${eng.fmt(rg.sigma)}` });
      break;
    }
    case "pitchfork": {
      if (!b || !c) break;
      const m = { x: (b.x + c.x) / 2, y: (b.y + c.y) / 2 }, dir = { x: m.x - a.x, y: m.y - a.y };
      if (!dir.x && !dir.y) break;
      const L = (p) => ({ k: "seg", a: p, b: far(p, dir, big) });
      shapes.push({ k: "poly", pts: [b, far(b, dir, big), far(c, dir, big), c], fill: 0.07 });
      shapes.push({ k: "seg", a, b: far(a, dir, big) }, L(b), L(c), { k: "seg", a: b, b: c, dashed: true });
      break;
    }
    case "gannfan": {
      if (!b) break;
      const dx = b.x - a.x || 1, dy = b.y - a.y;
      GANN.forEach(([kx, ky, name], i) => {
        const v = { x: dx * kx, y: dy * ky };
        shapes.push({ k: "seg", a, b: far(a, v, big), color: GANN_COL[i], thin: i !== 4 });
        const t = far(a, v, Math.min(big, Math.hypot(v.x, v.y) * 1.0 + 40));
        shapes.push({ k: "tag", x: t.x, y: t.y, text: name, color: GANN_COL[i] });
      });
      break;
    }
    case "triangle": {
      if (!b) break;
      if (c) shapes.push({ k: "poly", pts: [a, b, c], fill: 0.12, hit: true });
      shapes.push({ k: "seg", a, b });
      if (c) shapes.push({ k: "seg", a: b, b: c }, { k: "seg", a: c, b: a });
      break;
    }
    case "elliott5": case "elliottabc": {
      const names = ELLIOTT[d.type];
      for (let i = 1; i < S.length; i++) shapes.push({ k: "seg", a: S[i - 1], b: S[i] });
      S.forEach((p, i) => shapes.push({ k: "tag", x: p.x, y: p.y + (isHigh(S, i) ? -12 : 12), text: `(${names[i] ?? i})`, center: true }));
      break;
    }
    case "supply": case "demand": {
      if (!b) break;
      const x2 = d.style?.extend === false ? Math.max(a.x, b.x) : W;
      shapes.push({ k: "rect", x1: Math.min(a.x, b.x), y1: Math.min(a.y, b.y), x2: Math.max(x2, Math.max(a.x, b.x)), y2: Math.max(a.y, b.y), zone: true, hit: true });
      break;
    }
    case "arrow": if (b) shapes.push({ k: "seg", a, b, arrow: true }); break;
    case "text": case "note": {
      const t = d.name || (d.type === "note" ? "Ghi chú" : "Văn bản"), w = Math.min(280, t.length * 6.6 + 14);
      const x1 = a.x, y1 = d.type === "note" ? a.y - 12 : a.y - 9;
      shapes.push({ k: "rect", x1, y1, x2: x1 + w, y2: y1 + (d.type === "note" ? 26 : 18), hit: true, box: true });
      break;
    }
    case "fibarc": {
      if (!b) break;
      const R = Math.hypot(b.x - a.x, b.y - a.y), ang = Math.atan2(a.y - b.y, a.x - b.x); // hướng từ B về A
      FIBARC.forEach((r, i) => shapes.push({ k: "arc", cx: b.x, cy: b.y, r: R * r, a0: ang - Math.PI / 2, a1: ang + Math.PI / 2, ratio: r, i }));
      shapes.push({ k: "seg", a, b, dashed: true });
      break;
    }
    case "fibtime": {
      if (!b) break;
      const u = b.x - a.x;
      if (!u) break;
      FIBTIME.forEach((n, i) => shapes.push({ k: "vline", x: a.x + n * u, y1: 0, y2: H, n, i }));
      shapes.push({ k: "seg", a, b, dashed: true });
      break;
    }
    case "projection": {
      if (!b) break;
      shapes.push({ k: "seg", a, b });
      if (c) {
        const e = { x: c.x + (b.x - a.x), y: c.y + (b.y - a.y) };
        shapes.push({ k: "seg", a: c, b: e, proj: true }, { k: "seg", a: b, b: c, dashed: true }, { k: "tag", x: e.x, y: e.y, text: `Mục tiêu ${eng.fmt(d.pts[2].p + (d.pts[1].p - d.pts[0].p))}` });
      }
      break;
    }
    case "avwap": {
      const i0 = idxOf(eng, d.pts[0].t);
      const key = `${bars.length}|${i0}|${bars[bars.length - 1]?.c}`;
      if (!eng._av || eng._av.key !== key || eng._av.bars !== bars) eng._av = { key, bars, arr: anchoredVwap(bars, i0) };
      const arr = eng._av.arr, pts = [];
      const stride = Math.max(1, Math.floor((bars.length - i0) / 700));
      for (let i = i0; i < bars.length; i += stride) {
        const x = eng._x(bars[i].t), y = eng._y(arr[i]);
        if (x == null || y == null || x < -40 || x > W + 40) continue;
        pts.push({ x, y });
      }
      const li = bars.length - 1, xl = eng._x(bars[li].t), yl = eng._y(arr[li]);
      if (xl != null && yl != null && (stride > 1 || !pts.length)) pts.push({ x: xl, y: yl });
      if (pts.length > 1) shapes.push({ k: "path", pts, label: `VWAP neo ${eng.fmt(arr[li])}` });
      shapes.push({ k: "anchor", x: a.x, y: a.y });
      break;
    }
    case "vprofile": {
      if (!b) break;
      let i0 = idxOf(eng, Math.min(d.pts[0].t, d.pts[1].t)), i1 = idxOf(eng, Math.max(d.pts[0].t, d.pts[1].t));
      if (i1 <= i0) break;
      const rows = Math.max(12, Math.min(48, Math.round(Math.abs(b.y - a.y) / 7)));
      const key = `${bars.length}|${i0}|${i1}|${rows}|${bars[bars.length - 1]?.v}`;
      if (!eng._vp || eng._vp.key !== key || eng._vp.bars !== bars) eng._vp = { key, bars, vp: volumeProfile(bars, i0, i1, rows) };
      const vp = eng._vp.vp;
      if (!vp) break;
      const x1 = Math.min(a.x, b.x), x2 = Math.max(a.x, b.x), maxW = Math.max(40, (x2 - x1) * (d.style?.wide ? 0.9 : 0.45));
      const out = [];
      for (let r = 0; r < vp.vol.length; r++) {
        const y1 = eng._y(vp.lo + (r + 1) * vp.step), y2 = eng._y(vp.lo + r * vp.step);
        if (y1 == null || y2 == null) continue;
        out.push({ y1, y2, w: (vp.vol[r] / vp.max) * maxW, va: r >= vp.va[0] && r <= vp.va[1], poc: r === vp.poc });
      }
      const pocY = eng._y(vp.lo + (vp.poc + 0.5) * vp.step);
      shapes.push({ k: "vp", x1, x2, rows: out, pocY, poc: vp.lo + (vp.poc + 0.5) * vp.step, vah: vp.lo + (vp.va[1] + 1) * vp.step, val: vp.lo + vp.va[0] * vp.step });
      shapes.push({ k: "rect", x1, y1: Math.min(a.y, b.y), x2, y2: Math.max(a.y, b.y), hit: true, frame: true });
      break;
    }
    default: break;
  }
  return shapes;
}
const isHigh = (S, i) => {
  const p = S[i], pv = S[i - 1], nx = S[i + 1];
  if (pv && nx) return p.y < pv.y && p.y < nx.y;
  if (pv) return p.y < pv.y;
  if (nx) return p.y < nx.y;
  return true;
};

/** Vẽ phần đặc thù của loại mở rộng (sau khi đã vẽ seg/poly chung). */
export function paintExtra(eng, ctx, d, g, col, W, H) {
  const st = d.style || {};
  const label = (t, x, y, c, al) => eng._label(ctx, t, x, y, c, al);
  for (const sh of g.shapes) {
    if (sh.k === "tag") {
      if (sh.center) {
        ctx.font = "600 11px 'Inter Variable', system-ui, sans-serif"; ctx.textAlign = "center"; ctx.textBaseline = "middle";
        ctx.fillStyle = sh.color || col; ctx.fillText(sh.text, sh.x, sh.y); ctx.textAlign = "left";
      } else label(sh.text, Math.min(W - 70, Math.max(2, sh.x + 4)), sh.y, sh.color || col);
    } else if (sh.k === "arc") {
      ctx.strokeStyle = hexA(col, 0.9); ctx.lineWidth = 1; ctx.setLineDash([]);
      ctx.beginPath(); ctx.arc(sh.cx, sh.cy, Math.max(1, sh.r), sh.a0, sh.a1); ctx.stroke();
      const lx = sh.cx + sh.r * Math.cos(sh.a0), ly = sh.cy + sh.r * Math.sin(sh.a0);
      label(String(sh.ratio), lx, ly, col);
    } else if (sh.k === "vline") {
      ctx.strokeStyle = hexA(col, sh.n === 0 ? 0.9 : 0.5); ctx.lineWidth = 1; ctx.setLineDash(sh.n === 0 ? [] : [3, 4]);
      ctx.beginPath(); ctx.moveTo(sh.x, sh.y1); ctx.lineTo(sh.x, sh.y2); ctx.stroke(); ctx.setLineDash([]);
      label(String(sh.n), sh.x + 2, 14, col);
    } else if (sh.k === "path") {
      ctx.strokeStyle = col; ctx.lineWidth = (st.width || 1.5) + 0.5; ctx.setLineDash([]); ctx.lineJoin = "round";
      ctx.beginPath(); sh.pts.forEach((p, i) => (i ? ctx.lineTo(p.x, p.y) : ctx.moveTo(p.x, p.y))); ctx.stroke();
      const e = sh.pts[sh.pts.length - 1];
      label(sh.label, Math.min(W - 4, e.x) - 4, e.y - 10, col, "right");
    } else if (sh.k === "anchor") {
      ctx.fillStyle = col; ctx.beginPath(); ctx.arc(sh.x, sh.y, 4, 0, Math.PI * 2); ctx.fill();
      ctx.strokeStyle = eng.colors.panel; ctx.lineWidth = 1.5; ctx.stroke();
    } else if (sh.k === "vp") {
      for (const r of sh.rows) {
        ctx.fillStyle = hexA(col, r.va ? 0.42 : 0.2);
        ctx.fillRect(sh.x1, Math.min(r.y1, r.y2) + 0.5, Math.max(0.5, r.w), Math.max(1, Math.abs(r.y2 - r.y1) - 1));
      }
      if (sh.pocY != null) {
        ctx.strokeStyle = "#f0b84f"; ctx.lineWidth = 1.2; ctx.setLineDash([]);
        ctx.beginPath(); ctx.moveTo(sh.x1, sh.pocY); ctx.lineTo(sh.x2, sh.pocY); ctx.stroke();
        label(`POC ${eng.fmt(sh.poc)}`, sh.x2 - 4, sh.pocY - 9, "#f0b84f", "right");
      }
    } else if (sh.k === "rect" && sh.zone) {
      const c2 = d.type === "supply" ? "#ff5c7a" : "#2bd08f";
      ctx.fillStyle = hexA(st.color || c2, 0.16); ctx.fillRect(sh.x1, sh.y1, sh.x2 - sh.x1, sh.y2 - sh.y1);
      ctx.strokeStyle = st.color || c2; ctx.lineWidth = 1; ctx.strokeRect(sh.x1, sh.y1, sh.x2 - sh.x1, sh.y2 - sh.y1);
      label(d.name || (d.type === "supply" ? "Vùng cung" : "Vùng cầu"), sh.x1 + 2, sh.y1 + 10, st.color || c2);
    } else if (sh.k === "rect" && sh.box) {
      const t = d.name || (d.type === "note" ? "Ghi chú" : "Văn bản");
      if (d.type === "note") {
        ctx.fillStyle = hexA(col, 0.9); ctx.fillRect(sh.x1, sh.y1, sh.x2 - sh.x1, sh.y2 - sh.y1);
        ctx.fillStyle = "#111"; ctx.font = "600 12px 'Inter Variable', system-ui, sans-serif"; ctx.textBaseline = "middle"; ctx.textAlign = "left";
        ctx.fillText(t, sh.x1 + 7, (sh.y1 + sh.y2) / 2, sh.x2 - sh.x1 - 10);
      } else {
        ctx.fillStyle = col; ctx.font = "600 13px 'Inter Variable', system-ui, sans-serif"; ctx.textBaseline = "middle"; ctx.textAlign = "left";
        ctx.fillText(t, sh.x1 + 2, (sh.y1 + sh.y2) / 2, sh.x2 - sh.x1);
      }
    } else if (sh.k === "seg" && sh.arrow) {
      const ang = Math.atan2(sh.b.y - sh.a.y, sh.b.x - sh.a.x), L = 11;
      ctx.fillStyle = col; ctx.beginPath();
      ctx.moveTo(sh.b.x, sh.b.y);
      ctx.lineTo(sh.b.x - L * Math.cos(ang - 0.4), sh.b.y - L * Math.sin(ang - 0.4));
      ctx.lineTo(sh.b.x - L * Math.cos(ang + 0.4), sh.b.y - L * Math.sin(ang + 0.4));
      ctx.closePath(); ctx.fill();
    }
  }
  if (d.name && !["text", "note", "supply", "demand"].includes(d.type) && g.S[0]) label(d.name, g.S[0].x + 6, g.S[0].y - 12, col);
}
