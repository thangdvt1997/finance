// Biểu đồ chọn khoảng nến + đánh dấu ví dụ cho AI Training Class (lightweight-charts). CHỈ nghiên cứu/paper, không đặt lệnh.
// Cách dùng: chọn công cụ -> bấm trên biểu đồ (đỉnh/đáy/điểm vào: 1 chạm; sóng/vùng/khoảng nến: 2 chạm = đầu và cuối). Bấm "Xong" để đính vào tin nhắn.
import { useEffect, useRef, useState } from "react";
import { createChart, CandlestickSeries, createSeriesMarkers, CrosshairMode } from "lightweight-charts";
import { api } from "../../lib/api";
import { toBars } from "../chart/chartData";

const css = (n) => getComputedStyle(document.documentElement).getPropertyValue(n).trim();
export const KINDS = [
  ["khoang", "Khoảng nến", 2], ["song", "Sóng", 2], ["dinh", "Đỉnh", 1], ["day", "Đáy", 1], ["vung", "Vùng cung/cầu", 2], ["diem-vao", "Điểm vào", 1],
];
const KIND_EN = { khoang: "Bar range", song: "Wave", dinh: "Peak", day: "Trough", vung: "Supply/demand zone", "diem-vao": "Entry point" };
export const kindLabel = (k, en) => (en ? KIND_EN[k] : KINDS.find((x) => x[0] === k)?.[1]) || k;
const TFS = ["M15", "H1", "H4", "D1"];

export default function ExampleChart({ symbol: sym0 = "EURUSD", tf: tf0 = "H1", en, onDone, onClose }) {
  const box = useRef(null), refs = useRef({}), [sym, setSym] = useState(sym0), [tf, setTf] = useState(tf0);
  const [bars, setBars] = useState([]), [err, setErr] = useState(null), [kind, setKind] = useState("khoang");
  const [anns, setAnns] = useState([]), [pending, setPending] = useState(null), [note, setNote] = useState("");
  const [, force] = useState(0);
  const cur = useRef({ kind, pending }); cur.current = { kind, pending };
  const L = (vi, e) => (en ? e : vi);

  useEffect(() => {
    let off = false; setErr(null);
    api("/bars", { symbol: sym, tf, limit: 300, order: "desc" }).then((d) => { if (!off) setBars(toBars(d.items || d.bars || (Array.isArray(d) ? d : []))); }).catch((e) => !off && setErr(e.message));
    return () => { off = true; };
  }, [sym, tf]);

  useEffect(() => {
    const chart = createChart(box.current, {
      autoSize: true, layout: { background: { color: "transparent" }, textColor: css("--muted"), fontSize: 11 },
      grid: { vertLines: { color: css("--line") }, horzLines: { color: css("--line") } }, crosshair: { mode: CrosshairMode.Normal },
      localization: { locale: "vi-VN" }, rightPriceScale: { borderColor: css("--line2") }, timeScale: { borderColor: css("--line2"), timeVisible: true },
    });
    const s = chart.addSeries(CandlestickSeries, { upColor: css("--up"), downColor: css("--down"), wickUpColor: css("--up"), wickDownColor: css("--down"), borderVisible: false });
    refs.current = { chart, s, mk: createSeriesMarkers(s, []) };
    const redraw = () => force((x) => x + 1);
    chart.timeScale().subscribeVisibleLogicalRangeChange(redraw);
    chart.subscribeClick((p) => {
      if (!p.time || !p.point) return;
      const price = s.coordinateToPrice(p.point.y); if (price == null) return;
      const pt = { t: p.time, p: +price.toFixed(5) }; const { kind: k, pending: pd } = cur.current; const need = KINDS.find((x) => x[0] === k)[2];
      if (need === 1) { setAnns((a) => [...a, { kind: k, a: pt }]); return; }
      if (!pd) setPending(pt); else { setAnns((a) => [...a, { kind: k, a: pd, b: pt }]); setPending(null); }
    });
    return () => { chart.remove(); refs.current = {}; };
  }, []);

  useEffect(() => { const { s, chart } = refs.current; if (!s) return; s.setData(bars.map((b) => ({ time: b.t, open: b.o, high: b.h, low: b.l, close: b.c }))); chart.timeScale().fitContent(); }, [bars]);
  useEffect(() => {
    const { mk } = refs.current; if (!mk) return;
    const ms = []; const col = { dinh: css("--down"), day: css("--up"), "diem-vao": css("--accent") };
    for (const x of anns) if (col[x.kind]) ms.push({ time: x.a.t, position: x.kind === "dinh" ? "aboveBar" : "belowBar", shape: x.kind === "dinh" ? "arrowDown" : x.kind === "day" ? "arrowUp" : "circle", color: col[x.kind], text: kindLabel(x.kind, en) });
    if (pending) ms.push({ time: pending.t, position: "inBar", shape: "square", color: css("--info"), text: "1" });
    ms.sort((a, b) => a.time - b.time); mk.setMarkers(ms);
  }, [anns, pending, en]);

  const px = (pt) => { const { chart, s } = refs.current; if (!chart) return null; const x = chart.timeScale().timeToCoordinate(pt.t), y = s.priceToCoordinate(pt.p); return x == null || y == null ? null : { x, y }; };
  const shapes = anns.filter((a) => a.b).map((a, i) => ({ a, i, p1: px(a.a), p2: px(a.b) })).filter((x) => x.p1 && x.p2);
  const done = () => onDone?.({ symbol: sym, tf, annotations: anns.map((a) => ({ kind: a.kind, t1: new Date(a.a.t * 1000).toISOString(), p1: a.a.p, ...(a.b ? { t2: new Date(a.b.t * 1000).toISOString(), p2: a.b.p } : {}) })), note });
  const clr = css("--accent");

  return (
    <div className="grid gap-2" aria-label={L("Biểu đồ chọn ví dụ", "Example chart")}>
      <div className="flex flex-wrap gap-1 items-center">
        <select className="cr-inp cr-sel" value={sym} onChange={(e) => setSym(e.target.value)} aria-label={L("Mã", "Symbol")}>{["EURUSD", "GBPUSD", "USDJPY", "XAUUSD", "AUDUSD", "USDCAD"].concat(["EURUSD", "GBPUSD", "USDJPY", "XAUUSD", "AUDUSD", "USDCAD"].includes(sym0) ? [] : [sym0]).map((s) => <option key={s}>{s}</option>)}</select>
        <select className="cr-inp cr-sel" value={tf} onChange={(e) => setTf(e.target.value)} aria-label="TF">{TFS.map((t) => <option key={t}>{t}</option>)}</select>
        {KINDS.map(([k]) => <button key={k} type="button" className={`btn ${kind === k ? "" : "ghost"}`} aria-pressed={kind === k} onClick={() => { setKind(k); setPending(null); }}>{kindLabel(k, en)}</button>)}
      </div>
      <div className="relative cr-chart" role="img" aria-label={L("Biểu đồ nến", "Candles")}>
        <div ref={box} className="absolute inset-0" />
        <svg className="absolute inset-0 pointer-events-none" width="100%" height="100%" aria-hidden="true">
          {shapes.map(({ a, i, p1, p2 }) => a.kind === "song"
            ? <line key={i} x1={p1.x} y1={p1.y} x2={p2.x} y2={p2.y} stroke={clr} strokeWidth="2" />
            : <rect key={i} x={Math.min(p1.x, p2.x)} y={a.kind === "khoang" ? 0 : Math.min(p1.y, p2.y)} width={Math.abs(p2.x - p1.x)} height={a.kind === "khoang" ? "100%" : Math.abs(p2.y - p1.y)} fill={clr} fillOpacity="0.14" stroke={clr} strokeDasharray="4 3" />)}
        </svg>
        {err && <div className="absolute inset-0 grid place-items-center text-[12.5px] text-muted">{err}</div>}
      </div>
      <p className="m-0 text-[12px] text-muted">{pending ? L("Bấm điểm thứ hai để kết thúc.", "Click the second point to finish.") : L("Chọn công cụ rồi bấm trên biểu đồ (công cụ 2 điểm: bấm đầu rồi cuối).", "Pick a tool, then click the chart (two-point tools: click start then end).")}</p>
      <input className="cr-inp" value={note} onChange={(e) => setNote(e.target.value.slice(0, 300))} placeholder={L("Ghi chú cho AI (vì sao đây là ví dụ đúng/sai…)", "Note for the AI (why this is a right/wrong example…)")} aria-label={L("Ghi chú", "Note")} />
      <div className="flex gap-2 flex-wrap">
        <button type="button" className="btn" disabled={!anns.length} onClick={done}>{L("Xong, đính vào tin nhắn", "Done, attach to message")}</button>
        <button type="button" className="btn ghost" disabled={!anns.length} onClick={() => { setAnns((a) => a.slice(0, -1)); setPending(null); }}>{L("Hoàn tác", "Undo")}</button>
        <button type="button" className="btn ghost" onClick={onClose}>{L("Đóng", "Close")}</button>
        <span className="text-[12px] text-muted self-center">{anns.length} {L("đánh dấu", "marks")}</span>
      </div>
    </div>
  );
}
