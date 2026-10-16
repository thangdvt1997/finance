import { useLayoutEffect, useRef, useState } from "react";
import { BookOpen, Check, Info } from "lucide-react";
import { Chip, cn } from "../ui";
import { Dialog } from "../dialog";
import { FIXED_NOTE, pc, sgn, useMethodology } from "../../lib/trackrecord";
import { clean } from "../../lib/format";
import "./experts.css";

export function FixedNote({ className }) {
  return (
    <div role="note" className={cn("xp-banner", className)}>
      <Info size={15} aria-hidden="true" />
      <div><b>{FIXED_NOTE}</b> Không phải khuyến nghị đầu tư; hệ thống chỉ ghi nhận và chấm điểm ý kiến công khai, không đặt lệnh.</div>
    </div>
  );
}

export function Rank({ row }) {
  if (row.status !== "rated" || row.rank == null) return <span className="xp-rank none" title="Chưa đủ mẫu: không xếp hạng" aria-label="Chưa xếp hạng">—</span>;
  return <span className={cn("xp-rank", row.rank <= 3 && "top")} aria-label={`Hạng ${row.rank}`}>{row.rank}</span>;
}

/** "chưa đủ mẫu 12/30" + thanh tiến độ (chỉ khi thiếu mẫu); đủ mẫu: "n quan điểm đã chấm". */
export function Progress({ row, minN = 30 }) {
  const n = row.n ?? 0, need = minN;
  if (row.status === "rated") return <div className="xp-prog"><span><b className="num">{n}</b> quan điểm đã chấm</span></div>;
  const w = Math.min(100, (n / need) * 100);
  return (
    <div className="xp-prog">
      <span>Chưa đủ mẫu <b className="num">{n}/{need}</b></span>
      <div className="bar" role="progressbar" aria-valuemin={0} aria-valuemax={need} aria-valuenow={n} aria-label={`Tiến độ mẫu ${n} trên ${need}`}><i style={{ width: `${w}%` }} /></div>
    </div>
  );
}

export function BeatsBadge({ row }) {
  if (!row.beats_baseline || row.status !== "rated") return null;
  return <span className="xp-badge" title="Vượt ngẫu nhiên sau hiệu chỉnh đa kiểm định (BH-FDR): q < 0,10, khoảng tin cậy hit-rate nằm trên 50% và lợi suất trung bình dương."><Check size={12} aria-hidden="true" />Vượt ngẫu nhiên (q&lt;0,10)</span>;
}

/** Khoảng tin cậy nằm ngang (dumbbell nhỏ) với đường tham chiếu 50%. lo/hi/v trong 0..1. */
export function IntervalBar({ lo, hi, v, ref0 = 0.5, min = 0.2, max = 0.8, width = 120, height = 18, tone, hollow, label }) {
  if (v == null || lo == null || hi == null) return <span className="text-faint" aria-label="Chưa có dữ liệu">—</span>;
  const x = (a) => 3 + ((Math.max(min, Math.min(max, a)) - min) / (max - min)) * (width - 6);
  const col = tone === "up" ? "var(--up)" : tone === "down" ? "var(--down)" : "var(--muted)";
  const cy = height / 2;
  return (
    <svg className="xp-iv" width={width} height={height} viewBox={`0 0 ${width} ${height}`} role="img" aria-label={label || `Hit-rate ${pc(v)}, khoảng tin cậy ${pc(lo)} đến ${pc(hi)}, so với ${pc(ref0, 0)}`}>
      <line className="ref" x1={x(ref0)} x2={x(ref0)} y1={1} y2={height - 1} />
      <line className="seg" x1={x(lo)} x2={x(hi)} y1={cy} y2={cy} stroke={col} opacity={hollow ? 0.55 : 1} strokeDasharray={hollow ? "3 2" : undefined} />
      <line x1={x(lo)} x2={x(lo)} y1={cy - 4} y2={cy + 4} stroke={col} strokeWidth="2" strokeLinecap="round" />
      <line x1={x(hi)} x2={x(hi)} y1={cy - 4} y2={cy + 4} stroke={col} strokeWidth="2" strokeLinecap="round" />
      <circle cx={x(v)} cy={cy} r="4" fill={hollow ? "var(--panel)" : col} stroke={col} strokeWidth="2" />
    </svg>
  );
}

export function HitCell({ row, width = 120 }) {
  const rated = row.status === "rated";
  return (
    <span className="xp-hit">
      <span className="num v">{pc(row.hit_rate)}</span>
      <IntervalBar lo={row.ci_low} hi={row.ci_high} v={row.hit_rate} tone={row.beats_baseline && rated ? "up" : ""} hollow={!rated} width={width} />
    </span>
  );
}

export const retCell = (row) => (row.mean_ret_pct == null ? "—" : <span className={cn("num", row.mean_ret_pct > 0 ? "up" : row.mean_ret_pct < 0 ? "down" : "")} title={row.ret_ci_low != null ? `KTC 95%: ${sgn(row.ret_ci_low)} … ${sgn(row.ret_ci_high)}` : undefined}>{sgn(row.mean_ret_pct)}</span>);

export function ScoreBar({ v, dim }) {
  if (v == null) return <span className="text-faint">—</span>;
  const n = Math.max(0, Math.min(100, v));
  return (
    <div className="flex items-center gap-2 min-w-[88px]" title={`Điểm uy tín ${Math.round(n)}/100 (co về 50 khi ít bằng chứng)`}>
      <div className="flex-1 h-[6px] rounded bg-line"><div className="h-full rounded" style={{ width: `${Math.max(2, n)}%`, background: dim ? "var(--faint)" : n >= 60 ? "var(--info)" : "var(--muted)" }} /></div>
      <span className="num text-[12px] w-[26px] text-right">{Math.round(n)}</span>
    </div>
  );
}

export function useWidth(ref) {
  const [w, setW] = useState(0);
  useLayoutEffect(() => {
    if (!ref.current) return;
    const ro = new ResizeObserver((e) => setW(Math.round(e[0].contentRect.width)));
    ro.observe(ref.current);
    setW(Math.round(ref.current.getBoundingClientRect().width));
    return () => ro.disconnect();
  }, [ref]);
  return w;
}

/**
 * Đường + dải (SVG tự vẽ, màu từ CSS var). pts: [{t, y, lo?, hi?, mid?}], ref0: đường tham chiếu (vd 0,5 hoặc 0).
 * tip(p) -> mảng chuỗi cho tooltip. Hover/chạm/phím ←→ để đọc từng điểm.
 */
export function BandChart({ pts, ref0, yFmt, height = 170, tone = "var(--info)", bandTone = "var(--muted)", bandLabel, lineLabel, tip, label, yMin, yMax }) {
  const box = useRef(null);
  const w = useWidth(box);
  const [hi, setHi] = useState(null);
  const H = height, L = 44, R = 8, T = 8, B = 20;
  if (!pts?.length) return <div className="xp-empty">Chưa có điểm dữ liệu.</div>;
  const ys = pts.flatMap((p) => [p.y, p.lo, p.hi, p.mid].filter((v) => v != null)).concat(ref0 != null ? [ref0] : []);
  let a = yMin ?? Math.min(...ys), b = yMax ?? Math.max(...ys);
  if (a === b) { a -= 1; b += 1; }
  const pad = (b - a) * 0.06; a = yMin ?? a - pad; b = yMax ?? b + pad;
  const t0 = +new Date(pts[0].t), t1 = +new Date(pts[pts.length - 1].t) || t0 + 1;
  const X = (t) => L + ((+new Date(t) - t0) / Math.max(1, t1 - t0)) * Math.max(10, w - L - R);
  const Y = (v) => T + (1 - (v - a) / (b - a)) * (H - T - B);
  const path = (k) => pts.filter((p) => p[k] != null).map((p, i) => `${i ? "L" : "M"}${X(p.t).toFixed(1)},${Y(p[k]).toFixed(1)}`).join("");
  const bandPts = pts.filter((p) => p.lo != null && p.hi != null);
  const band = bandPts.length > 1 ? `${bandPts.map((p, i) => `${i ? "L" : "M"}${X(p.t).toFixed(1)},${Y(p.hi).toFixed(1)}`).join("")}${[...bandPts].reverse().map((p) => `L${X(p.t).toFixed(1)},${Y(p.lo).toFixed(1)}`).join("")}Z` : "";
  const ticks = Array.from({ length: 4 }, (_, i) => a + ((b - a) * i) / 3);
  const near = (clientX) => { const r = box.current.getBoundingClientRect(); const px = clientX - r.left; let best = 0, d = 1e9; pts.forEach((p, i) => { const dd = Math.abs(X(p.t) - px); if (dd < d) { d = dd; best = i; } }); setHi(best); };
  const cur = hi != null ? pts[hi] : null;
  const dtf = (t) => new Date(t).toLocaleDateString("vi-VN", { day: "2-digit", month: "2-digit" });
  return (
    <div>
      <div className="xp-chart" ref={box} onPointerMove={(e) => near(e.clientX)} onPointerLeave={() => setHi(null)} onPointerDown={(e) => near(e.clientX)}
        tabIndex={0} role="group" aria-label={`${label}. Dùng phím mũi tên trái/phải để đọc từng điểm.`}
        onKeyDown={(e) => { if (e.key === "ArrowLeft") { e.preventDefault(); setHi((h) => Math.max(0, (h ?? pts.length) - 1)); } else if (e.key === "ArrowRight") { e.preventDefault(); setHi((h) => Math.min(pts.length - 1, (h ?? -1) + 1)); } else if (e.key === "Escape") setHi(null); }}
        onBlur={() => setHi(null)}>
        {w > 0 && (
          <svg width={w} height={H} viewBox={`0 0 ${w} ${H}`} aria-hidden="true">
            <g className="grid ax">{ticks.map((v, i) => <g key={i}><line x1={L} x2={w - R} y1={Y(v)} y2={Y(v)} /><text x={L - 5} y={Y(v) + 3.5} textAnchor="end">{yFmt(v)}</text></g>)}</g>
            <g className="ax"><text x={L} y={H - 5}>{dtf(pts[0].t)}</text><text x={w - R} y={H - 5} textAnchor="end">{dtf(pts[pts.length - 1].t)}</text></g>
            {band && <path d={band} fill={bandTone} opacity="0.22" />}
            {pts.some((p) => p.mid != null) && <path d={path("mid")} fill="none" stroke={bandTone} strokeWidth="1" strokeDasharray="3 3" opacity=".8" />}
            {ref0 != null && <line x1={L} x2={w - R} y1={Y(ref0)} y2={Y(ref0)} stroke="var(--fg)" strokeOpacity=".45" strokeDasharray="4 3" />}
            <path d={path("y")} fill="none" stroke={tone} strokeWidth="2" strokeLinejoin="round" strokeLinecap="round" />
            {cur && <g><line x1={X(cur.t)} x2={X(cur.t)} y1={T} y2={H - B} stroke="var(--fg)" strokeOpacity=".4" /><circle cx={X(cur.t)} cy={Y(cur.y)} r="4" fill={tone} stroke="var(--panel)" strokeWidth="2" /></g>}
          </svg>
        )}
        {cur && (
          <div className="xp-tip" style={{ left: Math.max(4, Math.min(w - 190, X(cur.t) + 8)) }}>
            {tip(cur).map((s, i) => <div key={i}>{s}</div>)}
          </div>
        )}
      </div>
      <div className="xp-legend">
        <span><i style={{ background: tone }} />{lineLabel}</span>
        {band && <span><i className="band" style={{ background: bandTone }} />{bandLabel}</span>}
        {ref0 != null && <span><i style={{ background: "var(--fg)", opacity: 0.5 }} />Mốc tham chiếu {yFmt(ref0)}</span>}
      </div>
    </div>
  );
}

const DROP = new Set(["method_version", "as_of", "disclaimer"]);
function Node({ v, d = 0 }) {
  if (v == null) return null;
  if (typeof v === "string" || typeof v === "number") return <p>{clean(String(v))}</p>;
  if (Array.isArray(v)) {
    if (v.every((x) => typeof x === "string" || typeof x === "number")) return <ul>{v.map((x, i) => <li key={i}>{clean(String(x))}</li>)}</ul>;
    return <>{v.map((x, i) => <Node key={i} v={x} d={d + 1} />)}</>;
  }
  if (typeof v === "object") {
    const head = v.title || v.name || v.k || v.key;
    const body = v.text ?? v.desc ?? v.description ?? v.v ?? v.value;
    if (head && body !== undefined) return <div><h3>{clean(String(head))}</h3><Node v={body} d={d + 1} /></div>;
    const GENERIC = new Set(["summary", "sections", "items", "text", "notes", "overview", "steps", "points"]); // khoá chung chung: không in tên khoá tiếng Anh
    return <>{Object.entries(v).filter(([k]) => !DROP.has(k)).map(([k, x]) => (d > 2 || typeof x === "string" || typeof x === "number") ? <p key={k}>{!GENERIC.has(k) && <b>{k.replace(/_/g, " ")}: </b>}{clean(String(x))}</p> : <div key={k}>{!GENERIC.has(k) && <h3>{k.replace(/_/g, " ")}</h3>}<Node v={x} d={d + 1} /></div>)}</>;
  }
  return null;
}
const FALLBACK = ["Quan điểm có hướng được chấm bằng lợi suất giả định: vào ở giá mở cửa nến ngày kế tiếp sau lúc ghi nhận, thoát sau 1/5/21 nến ngày (không nhìn trước tương lai).",
  "Chỉ xếp hạng khi đủ mẫu (mặc định 30 quan điểm độc lập). Dưới ngưỡng: hiển thị số liệu thô, không xếp hạng.",
  "Hit-rate so với 50% bằng khoảng tin cậy Wilson; huy hiệu 'Vượt ngẫu nhiên' chỉ khi q-value (BH-FDR) < 0,10.",
  "Điểm uy tín 0-100 co về 50 khi ít bằng chứng."];

export function MethodDialog({ open, onClose }) {
  const q = useMethodology(open);
  const d = q.data;
  const body = d ? Object.fromEntries(Object.entries(d).filter(([k]) => !DROP.has(k))) : null;
  return (
    <Dialog open={open} onClose={onClose} title="Phương pháp chấm điểm chuyên gia" description={FIXED_NOTE}>
      <div className="xp-meth">
        {q.isPending && open && <p>Đang tải…</p>}
        {body && Object.keys(body).length > 0 && <Node v={body} />}
        {(q.isError || (body && Object.keys(body).length === 0)) && <><p>Không tải được mô tả chi tiết từ máy chủ; tóm tắt:</p><ul>{FALLBACK.map((s) => <li key={s}>{s}</li>)}</ul></>}
        {d?.method_version && <p className="xp-note">Phiên bản phương pháp: {String(d.method_version)}</p>}
      </div>
    </Dialog>
  );
}

export function MethodButton({ className }) {
  const [open, setOpen] = useState(false);
  return (
    <>
      <button type="button" className={cn("btn", className)} onClick={() => setOpen(true)} aria-haspopup="dialog"><BookOpen size={14} aria-hidden="true" /> Phương pháp</button>
      <MethodDialog open={open} onClose={() => setOpen(false)} />
    </>
  );
}

export const StatusChip = ({ status }) => (status === "rated" ? <Chip>Đủ mẫu</Chip> : <Chip tone="accent">Chưa đủ mẫu</Chip>);
