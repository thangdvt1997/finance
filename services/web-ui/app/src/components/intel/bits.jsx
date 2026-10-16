// Thành phần dùng chung của nhóm "intel": ô heat, treemap, danh sách ảo hoá, trạng thái gọn, chọn nhiều mã.
import { useEffect, useMemo, useRef, useState } from "react";
import * as echarts from "echarts/core";
import { TreemapChart } from "echarts/charts";
import { AlertTriangle, Inbox, RefreshCw } from "lucide-react";
import { EChart, css } from "../charts";
import { Skeleton, cn } from "../ui";
import { chartHref, fpct, heatClass, signCls } from "../../lib/intel";
import { lget, lset } from "../../lib/lstore";
import { time as fmtTime, dateTime } from "../../lib/format";

echarts.use([TreemapChart]);

/** % có dấu + màu tăng/giảm. */
export function Pct({ v, dp = 2, className }) {
  return <span className={cn("num", signCls(v), className)}>{fpct(v, dp)}</span>;
}

/** Ô heat: nền theo %, chữ luôn là con số (không chỉ dựa vào màu). */
export function HeatCell({ v, cap = 3, dp = 2, children, className, title }) {
  return <div className={cn("hc num", heatClass(v, cap), className)} title={title}>{children ?? fpct(v, dp)}</div>;
}

export function SymLink({ symbol, label, className }) {
  return <a href={chartHref(symbol)} className={cn("no-underline font-semibold hover:text-accent", className)} title={`Mở biểu đồ ${label || symbol}`}>{label || symbol}</a>;
}

/** Trạng thái: tải / lỗi (thử lại) / rỗng. Trả null khi có dữ liệu để component cha tự vẽ. */
export function QState({ q, empty = "Chưa có dữ liệu.", hint, rows = 5, isEmpty, compact }) {
  if (q.isPending) return <div className={compact ? "tm-pad" : "p-3"}><Skeleton rows={rows} /></div>;
  if (q.isError)
    return (
      <div role="alert" className={cn("flex flex-col items-start gap-2 text-[12.5px]", compact ? "tm-pad" : "p-3")}>
        <div className="flex items-center gap-2 text-down"><AlertTriangle size={15} aria-hidden="true" /> {q.error?.message || "Không tải được dữ liệu."}</div>
        {q.error?.status === 404 && <div className="text-faint">Máy chủ chưa có dữ liệu hoặc tính năng này chưa được bật.</div>}
        <button className="btn" onClick={() => q.refetch()}><RefreshCw size={13} aria-hidden="true" /> Thử lại</button>
      </div>
    );
  const d = q.data;
  const e = isEmpty ? isEmpty(d) : Array.isArray(d) ? d.length === 0 : d?.items ? d.items.length === 0 : !d;
  if (e)
    return (
      <div className={cn("flex flex-col items-start gap-1 text-muted text-[12.5px]", compact ? "tm-pad" : "p-3")}>
        <div className="flex items-center gap-2"><Inbox size={15} aria-hidden="true" /> {empty}</div>
        {hint && <div className="text-faint">{hint}</div>}
      </div>
    );
  return null;
}

/** Nhãn "cập nhật lúc" nhỏ gọn (giờ VN). */
export function AsOf({ ts, label = "Cập nhật", className }) {
  if (!ts) return null;
  return <span className={cn("text-[11px] text-faint num whitespace-nowrap", className)} title={dateTime(ts)}>{label} {fmtTime(ts)}</span>;
}

/** Treemap ECharts chung: items = [{name, label, value(size), pct, tip}] ; màu theo pct. */
export function HeatTreemap({ items, height = 420, cap = 4, onSelect, groupKey, ariaLabel = "Bản đồ nhiệt" }) {
  const build = () => {
    const bg = css("--bg"), fg = css("--fg"), line = css("--line2"), panel = css("--panel");
    const grouped = !!groupKey;
    const mk = (it) => ({
      name: it.label || it.name, full: it.name, value: Math.max(it.value || 0, 1e-9), pct: it.pct, tip: it.tip, key: it.key,
      itemStyle: { color: tileColor(it.pct, cap), borderColor: bg, borderWidth: 1 },
      label: { color: tileText(it.pct, cap) },
    });
    let data;
    if (grouped) {
      const by = new Map();
      for (const it of items) { const g = it[groupKey] || "Khác"; if (!by.has(g)) by.set(g, []); by.get(g).push(it); }
      data = [...by.entries()].map(([g, arr]) => ({ name: g, isGroup: true, children: arr.map(mk) }));
    } else data = items.map(mk);
    return {
      animation: false,
      tooltip: {
        confine: true, backgroundColor: panel, borderColor: line, textStyle: { color: fg, fontSize: 12 },
        formatter: (p) => (p.data?.isGroup ? `<b>${p.name}</b>` : `<b>${p.data.full || p.name}</b><br/>${fpct(p.data.pct)}${p.data.tip ? `<br/>${p.data.tip}` : ""}`),
      },
      series: [{
        type: "treemap", data, roam: false, nodeClick: false, breadcrumb: { show: false }, left: 0, right: 0, top: 0, bottom: 0, squareRatio: 1.15,
        label: { show: true, fontWeight: 600, fontSize: 12, overflow: "truncate", lineHeight: 15, formatter: (p) => (p.data.isGroup ? "" : `${p.name}\n${fpct(p.data.pct, 2)}`) },
        upperLabel: grouped ? { show: true, height: 20, color: fg, fontSize: 11.5, fontWeight: 650, formatter: "{b}" } : { show: false },
        itemStyle: { borderColor: bg, borderWidth: 1, gapWidth: 1 },
        levels: grouped
          ? [{ itemStyle: { borderColor: bg, borderWidth: 3, gapWidth: 3, color: "transparent" } }, { itemStyle: { borderColor: bg, borderWidth: 1, gapWidth: 1 } }]
          : [{ itemStyle: { borderColor: bg, borderWidth: 1, gapWidth: 1 } }],
      }],
    };
  };
  const wrap = useRef(null);
  useEffect(() => {
    if (!onSelect || !wrap.current) return;
    const inst = echarts.getInstanceByDom(wrap.current.querySelector('[role="img"]'));
    if (!inst) return;
    const h = (e) => { const k = e?.data?.key; if (k) onSelect(k); };
    inst.on("click", h);
    return () => { if (!inst.isDisposed()) inst.off("click", h); };
  }, [onSelect]);
  return (
    <div ref={wrap} className="flex flex-col" style={{ minHeight: height }}>
      <EChart build={build} deps={[items, cap, groupKey]} height={height} label={ariaLabel} />
    </div>
  );
}

const rgb = (hex) => { const s = hex.replace("#", ""); const v = s.length === 3 ? s.replace(/./g, "$&$&") : s; return [0, 2, 4].map((i) => parseInt(v.slice(i, i + 2), 16)); };
const mixv = (a, b, t) => a.map((x, i) => Math.round(x + (b[i] - x) * t));
const lum = ([r, g, b]) => (0.2126 * r + 0.7152 * g + 0.0722 * b) / 255;
function tileRgb(p, cap) {
  const n = rgb(css("--panel2") || "#131b26");
  if (p == null || Number.isNaN(p)) return n;
  const t = Math.min(Math.abs(p) / cap, 1);
  return mixv(n, rgb(css(p >= 0 ? "--up" : "--down") || "#888888"), 0.16 + 0.8 * t);
}
export const tileColor = (p, cap) => `rgb(${tileRgb(p, cap).join(",")})`;
export const tileText = (p, cap) => (lum(tileRgb(p, cap)) > 0.5 ? "#06100b" : "#ffffff");

/** Danh sách ảo hoá chiều cao hàng cố định: chỉ render phần nhìn thấy (+overscan). Cha phải có chiều cao cố định (flex-1 min-h-0). */
export function VirtualList({ count, rowHeight = 56, overscan = 8, render, className, role = "list", itemRole = "listitem", ariaLabel, onNearEnd, scrollRef }) {
  const el = useRef(null);
  const [st, setSt] = useState({ top: 0, h: 600 });
  useEffect(() => {
    const node = el.current;
    if (!node) return;
    if (scrollRef) scrollRef.current = node;
    const upd = () => setSt({ top: node.scrollTop, h: node.clientHeight });
    upd();
    const ro = new ResizeObserver(upd);
    ro.observe(node);
    node.addEventListener("scroll", upd, { passive: true });
    return () => { ro.disconnect(); node.removeEventListener("scroll", upd); };
  }, [scrollRef]);
  const start = Math.max(0, Math.floor(st.top / rowHeight) - overscan);
  const end = Math.min(count, Math.ceil((st.top + st.h) / rowHeight) + overscan);
  useEffect(() => { if (onNearEnd && count > 0 && end >= count - 3) onNearEnd(); }, [end, count]); // eslint-disable-line react-hooks/exhaustive-deps
  const rows = [];
  for (let i = start; i < end; i++) rows.push(<div key={i} role={itemRole} style={{ position: "absolute", top: i * rowHeight, left: 0, right: 0, height: rowHeight }}>{render(i)}</div>);
  return (
    <div ref={el} className={cn("overflow-auto relative min-h-0 flex-1", className)} role={role} aria-label={ariaLabel} tabIndex={0}>
      <div style={{ height: count * rowHeight, position: "relative" }}>{rows}</div>
    </div>
  );
}

/** Theo dõi media query (vd "(min-width: 1280px)"). */
export function useMedia(query) {
  const get = () => typeof matchMedia === "function" && matchMedia(query).matches;
  const [m, setM] = useState(get);
  useEffect(() => {
    if (typeof matchMedia !== "function") return undefined;
    const mq = matchMedia(query);
    const h = () => setM(mq.matches);
    h();
    mq.addEventListener("change", h);
    return () => mq.removeEventListener("change", h);
  }, [query]);
  return m;
}

/** State lưu localStorage (mỗi khoá 1 giá trị JSON nhỏ). */
export function useLocal(key, init) {
  const [v, setV] = useState(() => lget(key, init));
  const set = (x) => setV((cur) => { const n = typeof x === "function" ? x(cur) : x; lset(key, n); return n; });
  return [v, set];
}

/** Chọn nhiều mã từ danh sách symbol (checkbox có lọc). */
export function MultiSymbolPicker({ all, value, onChange, max = 30, className }) {
  const [text, setText] = useState("");
  const t = text.trim().toLowerCase();
  const list = useMemo(() => (all || []).filter((s) => !t || s.symbol.toLowerCase().includes(t) || (s.name || "").toLowerCase().includes(t)).slice(0, 120), [all, t]);
  const sel = new Set(value);
  const toggle = (s) => { const n = new Set(sel); if (n.has(s)) n.delete(s); else if (n.size < max) n.add(s); onChange([...n]); };
  return (
    <div className={cn("grid gap-2", className)}>
      <div className="flex items-center gap-2">
        <input type="search" className="field flex-1" placeholder="Lọc mã…" aria-label="Lọc mã" value={text} onChange={(e) => setText(e.target.value)} />
        <span className="text-[11px] text-faint whitespace-nowrap">{sel.size}/{max}</span>
        <button type="button" className="btn" onClick={() => onChange([])}>Bỏ chọn</button>
      </div>
      <div className="max-h-[220px] overflow-auto grid grid-cols-[repeat(auto-fill,minmax(8.5rem,1fr))] gap-x-2 gap-y-[2px]" role="group" aria-label="Danh sách mã">
        {list.map((s) => (
          <label key={s.symbol} className="flex items-center gap-1 text-[12px] cursor-pointer min-w-0">
            <input type="checkbox" checked={sel.has(s.symbol)} onChange={() => toggle(s.symbol)} style={{ accentColor: "var(--accent)" }} />
            <span className="truncate" title={s.name}>{s.symbol.replace(/^[A-Za-z]+:/, "")}</span>
          </label>
        ))}
      </div>
    </div>
  );
}
