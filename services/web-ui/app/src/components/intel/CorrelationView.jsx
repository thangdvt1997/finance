// Ma trận tương quan tương tác (lợi suất log nến ngày) + tương quan lăn + cặp mạnh nhất/đối nghịch.
// Thống kê lịch sử, không phải khuyến nghị. Không hiển thị tên nguồn dữ liệu.
import { useEffect, useMemo, useRef, useState } from "react";
import * as echarts from "echarts/core";
import { AlertTriangle, ChevronDown, ChevronUp, X } from "lucide-react";
import { EChart, css } from "../charts";
import { Chip, Seg, cn } from "../ui";
import { useCorrelationMatrix, useRollingCorr } from "../../lib/intel";
import { useSymbols } from "../../lib/queries";
import { MultiSymbolPicker, QState, SymLink, useLocal } from "./bits";

const WINDOWS = [20, 60, 120, 250].map((v) => ({ value: v, label: `${v} phiên` }));
const METHODS = [{ value: "pearson", label: "Pearson" }, { value: "spearman", label: "Spearman" }];
const ROLL = [20, 30, 60].map((v) => ({ value: v, label: `${v}` }));
const PRESETS = [
  { id: "multi", label: "Đa tài sản", symbols: [] },
  { id: "fx", label: "Forex majors", symbols: ["EURUSD", "GBPUSD", "USDJPY", "AUDUSD", "USDCAD", "USDCHF", "NZDUSD"] },
  { id: "crypto", label: "Crypto top", symbols: ["CRYPTO:BTCUSDT", "CRYPTO:ETHUSDT", "CRYPTO:BNBUSDT", "CRYPTO:SOLUSDT", "CRYPTO:XRPUSDT", "CRYPTO:ADAUSDT", "CRYPTO:DOGEUSDT"] },
  { id: "us", label: "Cổ phiếu Mỹ", symbols: ["US:AAPL", "US:MSFT", "US:NVDA", "US:AMZN", "US:GOOGL", "US:META", "US:TSLA", "US:JPM"] },
  { id: "vn", label: "VN + quốc tế", symbols: ["VN:FPT", "VN:VNM", "VN:VCB", "VN:HPG", "US:SPY", "XAUUSD", "EURUSD", "CRYPTO:BTCUSDT"] },
];

const r2 = (v) => (v == null || Number.isNaN(v) ? "—" : `${v > 0 ? "+" : v < 0 ? "−" : ""}${Math.abs(v).toFixed(2)}`);
const shortSym = (s) => String(s || "").replace(/^[A-Za-z]+:/, "");
const corrTone = (v) => (Math.abs(v) >= 0.7 ? "mạnh" : Math.abs(v) >= 0.4 ? "vừa" : Math.abs(v) >= 0.2 ? "yếu" : "không đáng kể");

function Legend() {
  return (
    <div className="flex items-center gap-2 text-[11px] text-muted" role="img" aria-label="Chú giải thang tương quan từ −1 (ngược chiều) đến +1 (cùng chiều)">
      <span className="num whitespace-nowrap">−1 ngược chiều</span>
      <div className="h-[10px] flex-1 max-w-[260px] rounded-full" style={{ background: "linear-gradient(90deg, var(--info, #5aa9ff), var(--panel2), var(--accent))" }} />
      <span className="num whitespace-nowrap">+1 cùng chiều</span>
    </div>
  );
}

function RollingPanel({ a, b, label, onClose }) {
  const [win, setWin] = useState(30);
  const q = useRollingCorr(a, b, win, 250);
  const d = q.data;
  const series = useMemo(() => (d?.series || []).filter((p) => p.corr != null).map((p) => [p.t, p.corr]), [d]);
  const build = () => {
    const fg = css("--fg"), muted = css("--muted"), line = css("--line2"), panel = css("--panel");
    const acc = css("--accent") || "#f0b84f";
    return {
      animation: false,
      grid: { left: 8, right: 14, top: 14, bottom: 8, containLabel: true },
      tooltip: { trigger: "axis", confine: true, backgroundColor: panel, borderColor: line, textStyle: { color: fg, fontSize: 12 }, valueFormatter: (v) => r2(v) },
      xAxis: { type: "time", axisLine: { lineStyle: { color: line } }, axisLabel: { color: muted, fontSize: 11 }, splitLine: { show: false } },
      yAxis: { type: "value", min: -1, max: 1, interval: 0.5, axisLabel: { color: muted, fontSize: 11 }, splitLine: { lineStyle: { color: line, opacity: 0.5 } } },
      series: [{
        type: "line", data: series, showSymbol: false, smooth: false, lineStyle: { width: 1.8, color: acc }, areaStyle: { color: acc, opacity: 0.08 },
        markLine: {
          silent: true, symbol: "none", animation: false,
          data: [
            { yAxis: 0, lineStyle: { color: muted, type: "solid", width: 1 }, label: { show: false } },
            ...(d?.avg != null ? [{ yAxis: d.avg, lineStyle: { color: muted, type: "dashed", width: 1 }, label: { formatter: "TB " + r2(d.avg), color: muted, fontSize: 10, position: "insideEndTop" } }] : []),
          ],
        },
      }],
    };
  };
  const diff = d?.latest != null && d?.avg != null ? d.latest - d.avg : null;
  return (
    <div className="rounded-md border border-line bg-panel2 p-3 grid gap-2" aria-live="polite">
      <div className="flex flex-wrap items-center gap-2">
        <h3 className="m-0 text-[13px] font-semibold">Tương quan lăn: {label}</h3>
        <span className="text-[11px] text-faint">cửa sổ lăn (phiên)</span>
        <Seg value={win} onChange={setWin} options={ROLL} label="Cửa sổ lăn" />
        <button type="button" className="btn ml-auto" onClick={onClose} aria-label="Đóng tương quan lăn"><X size={13} aria-hidden="true" /> Đóng</button>
      </div>
      <QState q={q} empty="Không đủ dữ liệu chung để tính tương quan lăn." rows={4} isEmpty={(x) => !x || !x.series?.length} />
      {q.data && d?.series?.length > 0 && (
        <>
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 text-[12px]">
            {[["Hiện tại", d.latest], ["Trung bình", d.avg], ["Thấp nhất", d.min], ["Cao nhất", d.max]].map(([l, v]) => (
              <div key={l}><div className="text-muted text-[11px]">{l}</div><div className="num text-[15px]">{r2(v)}</div></div>
            ))}
          </div>
          <div className="flex flex-col" style={{ minHeight: 200 }}>
            <EChart build={build} deps={[series, d?.avg]} height={200} label={`Tương quan lăn ${win} phiên của ${label}`} />
          </div>
          {diff != null && (
            <p className="m-0 text-[12px] text-muted">
              Hiện tại <b className="num text-fg">{r2(d.latest)}</b> {diff >= 0 ? "cao hơn" : "thấp hơn"} trung bình dài hạn <b className="num text-fg">{r2(d.avg)}</b> khoảng <span className="num">{Math.abs(diff).toFixed(2)}</span>
              {Math.abs(diff) >= 0.3 ? " — mối quan hệ đang lệch đáng kể so với thường lệ." : " — gần mức thường lệ."} Số liệu lịch sử, tham khảo.
            </p>
          )}
        </>
      )}
    </div>
  );
}

function PairList({ title, items, labels, onPick, tone }) {
  return (
    <div>
      <div className="text-[11.5px] font-semibold text-muted px-1 pb-1">{title}</div>
      {items.length === 0 ? <div className="text-[12px] text-faint px-1">Không có cặp phù hợp.</div> : (
        <div role="list">
          {items.map((p) => (
            <button key={p.a + "|" + p.b} type="button" role="listitem" className="in-row w-full text-left bg-transparent border-0 text-fg cursor-pointer font-[inherit]" onClick={() => onPick(p.a, p.b)}
              aria-label={`${labels[p.a] || p.a} với ${labels[p.b] || p.b}: r ${r2(p.r)}, ${p.n} quan sát. Bấm để xem tương quan lăn`}>
              <span className="truncate flex-1 text-[12.5px]">{labels[p.a] || shortSym(p.a)} <span className="text-faint">/</span> {labels[p.b] || shortSym(p.b)}</span>
              <span className="in-bar w-[56px] shrink-0" aria-hidden="true"><i style={{ left: 0, width: `${Math.abs(p.r) * 100}%`, background: tone }} /></span>
              <span className="num w-[44px] text-right text-[12.5px]">{r2(p.r)}</span>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

export function CorrelationView({ symbols: symProp, window: winProp, method: methodProp, compact = false, height }) {
  const all = useSymbols();
  const [savedSyms, setSavedSyms] = useLocal("intel.corr.syms", []);
  const [savedWin, setSavedWin] = useLocal("intel.corr.win", 60);
  const [savedMethod, setSavedMethod] = useLocal("intel.corr.method", "pearson");
  const [open, setOpen] = useState(false);
  const [pair, setPair] = useState(null);
  const fixed = Array.isArray(symProp) && symProp.length > 0;
  const syms = fixed ? symProp : savedSyms;
  const win = winProp ?? savedWin;
  const method = methodProp ?? savedMethod;
  const q = useCorrelationMatrix(syms, win, method);
  const d = q.data;
  const labels = d?.labels || {};
  const names = d?.symbols;
  const known = useMemo(() => new Set((all.data || []).map((s) => s.symbol)), [all.data]);

  const applyPreset = (p) => {
    const list = known.size ? p.symbols.filter((s) => known.has(s)) : p.symbols;
    setSavedSyms(list.length >= 2 || p.symbols.length === 0 ? list : p.symbols);
    setPair(null);
  };
  const activePreset = PRESETS.find((p) => p.symbols.length === savedSyms.length && p.symbols.every((s) => savedSyms.includes(s)))?.id;

  const { cells, pos, neg, weak } = useMemo(() => {
    const out = { cells: [], pos: [], neg: [], weak: 0 };
    if (!d?.matrix || !names) return out;
    const on = css("--on-heat") || "#04110b", fg = css("--fg");
    for (let y = 0; y < names.length; y++) {
      for (let x = 0; x < names.length; x++) {
        const v = d.matrix[y]?.[x];
        if (v == null) continue;
        const n = d.n_obs?.[y]?.[x];
        out.cells.push({ value: [x, y, v], label: { color: Math.abs(v) > 0.55 ? on : fg } });
        if (x > y) {
          if (n != null && n < 20) out.weak++;
          const it = { a: names[y], b: names[x], r: v, n };
          (v >= 0 ? out.pos : out.neg).push(it);
        }
      }
    }
    out.pos.sort((p, q2) => q2.r - p.r);
    out.neg.sort((p, q2) => p.r - q2.r);
    out.pos = out.pos.slice(0, 8);
    out.neg = out.neg.filter((p) => p.r < 0).slice(0, 8);
    return out;
  }, [d, names]);

  const n = names?.length || 0;
  const showLabel = n > 0 && n <= (compact ? 10 : 16);
  const h = height ?? (compact ? 260 : Math.min(640, Math.max(340, n * 34 + 110)));
  const build = () => {
    const fg = css("--fg"), muted = css("--muted"), line = css("--line2"), panel = css("--panel");
    const neg0 = css("--info") || "#5aa9ff", mid = css("--panel2") || "#1b2430", pos0 = css("--accent") || "#f0b84f";
    const cat = (names || []).map((s) => labels[s] || shortSym(s));
    return {
      animation: false,
      grid: { left: 6, right: 10, top: 8, bottom: 6, containLabel: true },
      tooltip: {
        confine: true, backgroundColor: panel, borderColor: line, textStyle: { color: fg, fontSize: 12 },
        formatter: (p) => {
          const [x, y, v] = p.data.value;
          const no = d?.n_obs?.[y]?.[x];
          return `<b>${cat[y]} / ${cat[x]}</b><br/>r = <b>${r2(v)}</b> (tương quan ${corrTone(v)}${v < 0 ? ", ngược chiều" : ""})<br/>${no ?? "?"} quan sát${no != null && no < 20 ? " — ít, kém tin cậy" : ""}<br/><i>Bấm để xem tương quan lăn</i>`;
        },
      },
      visualMap: { show: false, type: "continuous", min: -1, max: 1, dimension: 2, inRange: { color: [neg0, mid, pos0] } },
      xAxis: { type: "category", data: cat, splitArea: { show: false }, axisTick: { show: false }, axisLine: { lineStyle: { color: line } }, axisLabel: { color: muted, fontSize: 11, interval: 0, rotate: n > 8 ? 40 : 0 } },
      yAxis: { type: "category", data: cat, inverse: true, axisTick: { show: false }, axisLine: { lineStyle: { color: line } }, axisLabel: { color: muted, fontSize: 11, interval: 0 } },
      series: [{
        type: "heatmap", data: cells, progressive: 0,
        label: { show: showLabel, fontSize: n > 12 ? 9.5 : 11, formatter: (p) => { const v = p.data.value[2]; if (v >= 0.995) return "1"; return (v < 0 ? "−" : "") + Math.abs(v).toFixed(2).replace(/^0/, ""); } },
        itemStyle: { borderColor: panel, borderWidth: 1 },
        emphasis: { itemStyle: { borderColor: fg, borderWidth: 1.5 } },
      }],
    };
  };

  const wrap = useRef(null);
  const ready = !!d?.matrix;
  useEffect(() => {
    const node = wrap.current?.querySelector('[role="img"]');
    const inst = node && echarts.getInstanceByDom(node);
    if (!inst || !names) return;
    const hnd = (e) => {
      const v = e?.data?.value;
      if (!Array.isArray(v)) return;
      const a = names[v[1]], b = names[v[0]];
      if (a && b && a !== b) setPair({ a, b });
    };
    inst.on("click", hnd);
    return () => { if (!inst.isDisposed()) inst.off("click", hnd); };
  }, [names, ready]);

  const pickPair = (a, b) => setPair({ a, b });
  const pairLabel = pair ? `${labels[pair.a] || shortSym(pair.a)} / ${labels[pair.b] || shortSym(pair.b)}` : "";

  return (
    <div className={cn("grid gap-3", compact && "tm-pad")}>
      {!compact && (
        <div className="flex flex-wrap items-center gap-2">
          <Seg value={win} onChange={(v) => !winProp && setSavedWin(v)} options={WINDOWS} label="Cửa sổ tính (số phiên)" />
          <Seg value={method} onChange={(v) => !methodProp && setSavedMethod(v)} options={METHODS} label="Phương pháp" />
          {!fixed && (
            <>
              <div className="seg" role="group" aria-label="Rổ mã định sẵn">
                {PRESETS.map((p) => <button key={p.id} type="button" aria-pressed={activePreset === p.id || (p.id === "multi" && savedSyms.length === 0)} onClick={() => applyPreset(p)}>{p.label}</button>)}
              </div>
              <button type="button" className="btn" aria-expanded={open} onClick={() => setOpen((o) => !o)}>
                Chọn mã ({savedSyms.length || "mặc định"}) {open ? <ChevronUp size={13} aria-hidden="true" /> : <ChevronDown size={13} aria-hidden="true" />}
              </button>
            </>
          )}
        </div>
      )}
      {!compact && open && !fixed && (
        <div className="rounded-md border border-line bg-panel2 p-3">
          <MultiSymbolPicker all={all.data || []} value={savedSyms} onChange={(v) => { setSavedSyms(v); setPair(null); }} max={30} />
          <p className="m-0 mt-2 text-[11.5px] text-faint">Để trống = rổ đa tài sản mặc định của máy chủ. Chọn 2–30 mã.</p>
        </div>
      )}
      <QState q={q} empty="Chưa đủ dữ liệu để tính tương quan." hint="Chọn thêm mã hoặc đợi dữ liệu nến ngày." rows={6} compact={compact} isEmpty={(x) => !x || !x.symbols?.length || x.symbols.length < 2} />
      {ready && n >= 2 && (
        <div className={cn("grid gap-3", !compact && "lg:grid-cols-[minmax(0,1fr)_20rem]")}>
          <div className="min-w-0 grid gap-2">
            <div ref={wrap} className="flex flex-col" style={{ minHeight: h }}>
              <EChart build={build} deps={[cells, names, showLabel, win, method]} height={h} label={`Ma trận tương quan ${method === "spearman" ? "hạng Spearman" : "Pearson"} ${win} phiên, ${n} mã`} />
            </div>
            <Legend />
            {!compact && (
              <div className="flex flex-wrap gap-1.5 items-center">
                <Chip title="Cửa sổ và phương pháp đang dùng">{win} phiên · {method === "spearman" ? "Spearman" : "Pearson"}</Chip>
                {weak > 0 && <Chip tone="accent" title="Cặp có dưới 20 quan sát chung">ⓘ {weak} cặp có dưới 20 quan sát</Chip>}
                {d.missing?.length > 0 && (
                  <span className="inline-flex items-center gap-1 text-[12px] text-accent" role="note"><AlertTriangle size={13} aria-hidden="true" /> Thiếu dữ liệu: {d.missing.map((s) => shortSym(s)).join(", ")}</span>
                )}
              </div>
            )}
          </div>
          {!compact && (
            <div className="grid gap-3 content-start min-w-0">
              <PairList title="Cặp cùng chiều mạnh nhất" items={pos} labels={labels} onPick={pickPair} tone="var(--accent)" />
              <PairList title="Cặp ngược chiều (đối nghịch) mạnh nhất" items={neg} labels={labels} onPick={pickPair} tone="var(--info, #5aa9ff)" />
            </div>
          )}
        </div>
      )}
      {!compact && pair && <RollingPanel a={pair.a} b={pair.b} label={pairLabel} onClose={() => setPair(null)} />}
      {!compact && (
        <p className="m-0 text-[11.5px] text-faint max-w-[90ch]">
          Tương quan tính trên lợi suất log của nến ngày; các cặp dùng chung ngày giao dịch (thị trường 7 ngày/tuần như tiền ảo được ghép với thị trường 5 ngày/tuần), nên số quan sát thực tế có thể ít hơn số phiên chọn.
          Tương quan thay đổi theo thời gian và không hàm ý nhân quả. Thống kê tham khảo, không phải khuyến nghị đầu tư.
          {pair && <> Mở biểu đồ: <SymLink symbol={pair.a} label={shortSym(pair.a)} /> · <SymLink symbol={pair.b} label={shortSym(pair.b)} />.</>}
        </p>
      )}
    </div>
  );
}

export default CorrelationView;
