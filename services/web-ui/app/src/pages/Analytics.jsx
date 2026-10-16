import { useEffect, useMemo, useState } from "react";
import { Grid3x3, LineChart as LineIcon, Network, SlidersHorizontal, Sunrise, TrendingDown, TrendingUp, Minus } from "lucide-react";
import { Async, Chip, Disclaimer, Freshness, PageHead, Panel, Seg, Stat, cn } from "../components/ui";
import { FRESH } from "../lib/freshness";
import { CandleChart, EChart, css } from "../components/charts";
import { DataTable } from "../components/table";
import { useAnOverview, useAnSymbol, useBars, useCorrelation, useScreener, useSessions, useNow } from "../lib/queries";
import { decimals, price, rel, symbolLabel } from "../lib/format";

const NOTE = "Chỉ báo kỹ thuật, không phải khuyến nghị đầu tư.";
const TREND = { up: ["Tăng", "up"], down: ["Giảm", "down"], side: ["Đi ngang", ""] };
const MOM = { overbought: ["Quá mua", "accent"], oversold: ["Quá bán", "accent"], bullish: ["Nghiêng tăng", "up"], bearish: ["Nghiêng giảm", "down"], neutral: ["Trung tính", ""] };
const VOL = { squeeze: ["Squeeze", "accent"], high: ["Cao", "accent"], normal: ["Vừa", ""], low: ["Thấp", ""] };
const TONE = { up: "up", down: "down", accent: "accent", warn: "accent", neutral: "" };
const SESSION_LABEL = { tokyo: "Tokyo", london: "London", newyork: "New York" };
const num = (v, dp = 1) => (v == null ? "—" : Number(v).toFixed(dp));
const signed = (v, dp = 0) => (v == null ? "—" : `${v > 0 ? "+" : ""}${Number(v).toFixed(dp)}`);

function Tag({ map, v }) {
  const [label, tone] = map[v] || [v, ""];
  return <Chip tone={tone}>{label}</Chip>;
}

/** Màu ô heatmap: hue theo độ nghiêng chỉ báo (xanh = nghiêng tăng, đỏ = nghiêng giảm, xám = trung tính), đậm theo heat. */
function cellStyle(c) {
  if (!c) return {};
  const strength = Math.min(1, Math.abs(c.bias) / 100);
  if (strength < 0.2) return { background: "var(--panel2)" };
  const hue = c.bias > 0 ? "var(--up)" : "var(--down)";
  const mix = Math.round(10 + (c.heat / 100) * 38);
  return { background: `color-mix(in srgb, ${hue} ${mix}%, var(--panel2))` };
}

function Heatmap({ data, sel, onPick }) {
  const rows = useMemo(() => {
    const by = new Map();
    for (const i of data.items) {
      if (!by.has(i.symbol)) by.set(i.symbol, { symbol: i.symbol, max: 0, cells: {} });
      const r = by.get(i.symbol);
      r.cells[i.tf] = i;
      r.max = Math.max(r.max, i.heat);
    }
    return [...by.values()].sort((a, b) => b.max - a.max || a.symbol.localeCompare(b.symbol));
  }, [data]);
  return (
    <div className="scroll-x">
      <table className="tbl" style={{ minWidth: 300 }} aria-label="Bản đồ nhiệt trạng thái chỉ báo theo symbol và khung thời gian">
        <thead>
          <tr>
            <th>Symbol</th>
            {data.tfs.map((tf) => <th key={tf} className="r">{tf}</th>)}
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.symbol} className={cn(sel === r.symbol && "!bg-panel2")}>
              <td>
                <button type="button" className="cursor-pointer font-semibold text-fg bg-transparent border-0 p-0 font-[inherit]" onClick={() => onPick(r.symbol)} aria-pressed={sel === r.symbol}>
                  {symbolLabel(r.symbol)}
                </button>
              </td>
              {data.tfs.map((tf) => {
                const c = r.cells[tf];
                const Icon = !c ? null : c.trend === "up" ? TrendingUp : c.trend === "down" ? TrendingDown : Minus;
                return (
                  <td key={tf} className="r !p-[3px]">
                    {c ? (
                      <button type="button" onClick={() => { onPick(r.symbol); }} style={cellStyle(c)}
                        title={`${r.symbol} ${tf}: heat ${c.heat}, độ nghiêng ${signed(c.bias)}, xu hướng ${TREND[c.trend]?.[0]}, ${MOM[c.momentum]?.[0]}, biến động ${VOL[c.volatility]?.[0]}`}
                        aria-label={`${r.symbol} ${tf}: heat ${c.heat}, độ nghiêng ${signed(c.bias)}`}
                        className="w-full min-w-[64px] h-9 rounded-[5px] border-0 text-fg cursor-pointer inline-flex items-center justify-end gap-[6px] px-2 font-[inherit]">
                        <Icon size={13} aria-hidden="true" className={c.trend === "up" ? "text-up" : c.trend === "down" ? "text-down" : "text-faint"} />
                        <span className="num text-[13px]">{c.heat}</span>
                      </button>
                    ) : <span className="text-faint px-2">—</span>}
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
      <div className="flex flex-wrap items-center gap-x-4 gap-y-1 px-3 pb-3 pt-2 text-[11.5px] text-muted" aria-hidden="true">
        <span className="inline-flex items-center gap-1"><i className="inline-block w-3 h-3 rounded-sm" style={{ background: "color-mix(in srgb, var(--up) 40%, var(--panel2))" }} /> nghiêng tăng</span>
        <span className="inline-flex items-center gap-1"><i className="inline-block w-3 h-3 rounded-sm" style={{ background: "color-mix(in srgb, var(--down) 40%, var(--panel2))" }} /> nghiêng giảm</span>
        <span className="inline-flex items-center gap-1"><i className="inline-block w-3 h-3 rounded-sm bg-panel2 border border-line2" /> trung tính</span>
        <span>Số trong ô = heat (0–100): mức đáng chú ý, màu đậm = heat cao.</span>
      </div>
    </div>
  );
}

const lineData = (t, v) => t.map((x, i) => ({ time: x, value: v[i] })).filter((p) => p.value != null);

function SubChart({ d, kind }) {
  const s = d.series;
  const build = () => {
    const x = s.t.map((t) => t * 1000);
    const axis = { axisLine: { lineStyle: { color: css("--line2") } }, axisLabel: { color: css("--muted"), fontSize: 11 }, splitLine: { lineStyle: { color: css("--line") } } };
    const tip = { trigger: "axis", backgroundColor: css("--panel2"), borderColor: css("--line2"), textStyle: { color: css("--fg"), fontSize: 12 } };
    const base = { animation: false, backgroundColor: "transparent", grid: { left: 44, right: 12, top: 10, bottom: 22 }, tooltip: tip,
      xAxis: { type: "time", ...axis, splitLine: { show: false } } };
    if (kind === "rsi") {
      const ml = (y) => ({ yAxisIndex: 0, silent: true, symbol: "none", lineStyle: { color: css("--faint"), type: "dashed" }, label: { show: false }, data: [{ yAxis: y }] });
      return { ...base, yAxis: { type: "value", min: 0, max: 100, interval: 10, ...axis, axisLabel: { ...axis.axisLabel, formatter: (v) => (v % 30 === 0 || v === 50 ? v : "") } },
        series: [
          { name: "RSI(14)", type: "line", data: s.rsi.map((v, i) => [x[i], v]), showSymbol: false, lineStyle: { width: 1.8, color: css("--accent") }, itemStyle: { color: css("--accent") },
            markLine: { silent: true, symbol: "none", label: { show: false }, lineStyle: { color: css("--faint"), type: "dashed" }, data: [{ yAxis: 30 }, { yAxis: 70 }] } },
          { name: "Stoch %K", type: "line", data: s.stoch_k.map((v, i) => [x[i], v]), showSymbol: false, lineStyle: { width: 1, color: css("--info"), opacity: 0.8 }, itemStyle: { color: css("--info") } },
        ] };
    }
    return { ...base, yAxis: { type: "value", scale: true, ...axis, axisLabel: { ...axis.axisLabel, formatter: (v) => Number(v.toPrecision(2)) } },
      series: [
        { name: "Histogram", type: "bar", data: s.macd_hist.map((v, i) => ({ value: [x[i], v], itemStyle: { color: v >= 0 ? css("--up") : css("--down"), opacity: 0.55 } })), barMaxWidth: 4 },
        { name: "MACD", type: "line", data: s.macd.map((v, i) => [x[i], v]), showSymbol: false, lineStyle: { width: 1.5, color: css("--fg") }, itemStyle: { color: css("--fg") } },
        { name: "Signal", type: "line", data: s.macd_signal.map((v, i) => [x[i], v]), showSymbol: false, lineStyle: { width: 1.2, color: css("--accent") }, itemStyle: { color: css("--accent") } },
      ] };
  };
  return <EChart build={build} deps={[d]} height={kind === "rsi" ? 130 : 120} className="flex-none" label={kind === "rsi" ? "Biểu đồ RSI và Stochastic" : "Biểu đồ MACD"} />;
}

function Detail({ symbol }) {
  const [tf, setTf] = useState("H1");
  const q = useAnSymbol(symbol);
  const tfs = q.data ? Object.keys(q.data.tfs) : [];
  const cur = tfs.includes(tf) ? tf : tfs[0];
  const d = q.data?.tfs?.[cur];
  const bars = useBars(symbol, cur, 400, { enabled: !!cur, refetchInterval: 60_000 });
  const ordered = useMemo(() => [...(bars.data?.items || [])].reverse(), [bars.data]);
  const overlays = useMemo(() => {
    if (!d) return [];
    const s = d.series;
    return [
      { id: "ema20", color: css("--accent"), width: 1.5, data: lineData(s.t, s.ema20) },
      { id: "ema50", color: css("--info"), width: 1.5, data: lineData(s.t, s.ema50) },
      { id: "ema200", color: css("--fg"), width: 2, data: lineData(s.t, s.ema200) },
      { id: "bbu", color: css("--faint"), dashed: true, data: lineData(s.t, s.bb_upper) },
      { id: "bbl", color: css("--faint"), dashed: true, data: lineData(s.t, s.bb_lower) },
    ];
  }, [d]);
  const dec = decimals(symbol);
  return (
    <Panel title={`${symbolLabel(symbol)} · chi tiết chỉ báo`} icon={LineIcon} className="an-detail" scroll bodyClass="flex flex-col"
      right={tfs.length > 0 && <Seg value={cur} onChange={setTf} options={tfs} label="Khung thời gian" />}>
      <Async q={q} rows={8} empty="Chưa có phân tích cho symbol này." isEmpty={() => !d}>
        {() => d && (
          <div className="flex flex-col gap-3 min-h-full">
            <div className="flex flex-wrap gap-1.5" aria-label="Trạng thái theo quy tắc">
              {d.states.map((s) => <Chip key={s.code} tone={TONE[s.tone]} title={`Quy tắc: ${s.rule}`}>{s.label}</Chip>)}
            </div>
            <div className="grid grid-cols-[repeat(auto-fit,minmax(8.5rem,1fr))] gap-3">
              <Stat label="Heat (0–100)" big value={d.heat} sub="mức đáng chú ý, không có hướng" />
              <Stat label="Độ nghiêng chỉ báo" big value={signed(d.bias)} tone={d.bias > 0 ? "up" : d.bias < 0 ? "down" : ""} sub="−100 … +100, 5 điều kiện" />
              <Stat label="RSI(14)" value={num(d.rsi)} sub={`Stoch %K ${num(d.stoch_k)}`} />
              <Stat label="ADX(14)" value={num(d.adx)} sub={`+DI ${num(d.indicators.plus_di)} / −DI ${num(d.indicators.minus_di)}`} />
              <Stat label="ATR(14)" value={price(symbol, d.indicators.atr)} sub={`${num(d.atr_pct, 3)}% · phân vị ${num(d.atr_percentile, 0)}`} />
              <Stat label="Cách EMA200" value={d.ema200_dist_pct == null ? "—" : `${signed(d.ema200_dist_pct, 2)}%`} tone={d.ema200_dist_pct > 0 ? "up" : d.ema200_dist_pct < 0 ? "down" : ""} />
              <Stat label="Bollinger %B" value={num(d.bb_pctb, 2)} sub={`rộng ${num(d.indicators.bb_width * 100, 2)}%`} />
              <Stat label="MACD hist" value={num(d.macd_hist, 5)} />
            </div>
            <div className="flex flex-col flex-1">
              <div className="flex flex-wrap gap-x-4 gap-y-1 text-[11.5px] text-muted mb-1" aria-hidden="true">
                <span><i className="inline-block w-3 h-[2px] align-middle mr-1" style={{ background: "var(--accent)" }} />EMA20</span>
                <span><i className="inline-block w-3 h-[2px] align-middle mr-1" style={{ background: "var(--info)" }} />EMA50</span>
                <span><i className="inline-block w-3 h-[2px] align-middle mr-1" style={{ background: "var(--fg)" }} />EMA200</span>
                <span><i className="inline-block w-3 border-t border-dashed border-faint align-middle mr-1" />Bollinger(20,2)</span>
              </div>
              <Async q={bars} rows={8} empty={`Chưa có nến ${cur}.`}>
                {() => <CandleChart bars={ordered} symbol={symbol} tf={cur} decimals={dec} overlays={overlays} height={320} />}
              </Async>
              <SubChart d={d} kind="rsi" />
              <SubChart d={d} kind="macd" />
            </div>
            <div className="grid sm:grid-cols-2 gap-3">
              <div>
                <h3 className="m-0 mb-1 text-[12px] font-semibold text-muted">Pivot cổ điển</h3>
                <table className="tbl"><tbody>
                  {["r2", "r1", "p", "s1", "s2"].map((k) => (
                    <tr key={k}><td className="text-muted">{k.toUpperCase()}</td><td className="r num">{price(symbol, d.pivot[k])}</td></tr>
                  ))}
                </tbody></table>
                <p className="m-0 mt-1 text-[11.5px] text-faint">{d.pivot_note}</p>
              </div>
              <details className="text-[12.5px]">
                <summary className="cursor-pointer text-muted">Quy tắc của từng trạng thái</summary>
                <ul className="m-0 mt-2 p-0 list-none grid gap-1">
                  {d.states.map((s) => <li key={s.code}><b>{s.label}</b><span className="text-muted"> — {s.rule}</span></li>)}
                </ul>
              </details>
            </div>
            <p className="m-0 text-[11.5px] text-faint">{NOTE} Nến cuối: {d.bar_ts?.slice(0, 16).replace("T", " ")} UTC.</p>
          </div>
        )}
      </Async>
    </Panel>
  );
}

const SELECT = "field";
function Screener({ onPick, sel, tfs }) {
  const [f, setF] = useState({ tf: "H1", trend: "", momentum: "", volatility: "", q: "", rsi_min: "", rsi_max: "", heat_min: "", adx_min: "" });
  const set = (k) => (e) => setF((o) => ({ ...o, [k]: e.target.value }));
  const params = { ...f, sort: "heat", order: "desc", limit: 200 };
  const q = useScreener(params);
  const columns = useMemo(() => [
    { accessorKey: "symbol", header: "Symbol", cell: (c) => (
      <button type="button" onClick={() => onPick(c.getValue())} className="border-0 bg-transparent p-0 font-[inherit] font-semibold text-fg cursor-pointer underline decoration-dotted underline-offset-2">{symbolLabel(c.getValue())}</button>) },
    { accessorKey: "heat", header: "Heat", meta: { align: "r" }, cell: (c) => <span className="num">{c.getValue()}</span> },
    { accessorKey: "bias", header: "Nghiêng", meta: { align: "r" }, cell: (c) => <span className={cn("num", c.getValue() > 0 ? "up" : c.getValue() < 0 ? "down" : "flat")}>{signed(c.getValue())}</span> },
    { accessorKey: "trend", header: "Xu hướng", cell: (c) => <Tag map={TREND} v={c.getValue()} /> },
    { accessorKey: "momentum", header: "Động lượng", cell: (c) => <Tag map={MOM} v={c.getValue()} /> },
    { accessorKey: "volatility", header: "Biến động", cell: (c) => <Tag map={VOL} v={c.getValue()} /> },
    { accessorKey: "rsi", header: "RSI", meta: { align: "r" }, cell: (c) => <span className="num">{num(c.getValue())}</span> },
    { accessorKey: "adx", header: "ADX", meta: { align: "r" }, cell: (c) => <span className="num">{num(c.getValue())}</span> },
    { accessorKey: "atr_percentile", header: "ATR %ile", meta: { align: "r" }, cell: (c) => <span className="num">{num(c.getValue(), 0)}</span> },
    { accessorKey: "ema200_dist_pct", header: "Cách EMA200", meta: { align: "r" }, cell: (c) => <span className={cn("num", c.getValue() > 0 ? "up" : c.getValue() < 0 ? "down" : "flat")}>{c.getValue() == null ? "—" : `${signed(c.getValue(), 2)}%`}</span> },
  ], [onPick]);
  return (
    <Panel title="Bộ lọc điều kiện (screener)" icon={SlidersHorizontal} pad={false} className="an-screen" bodyClass="flex flex-col"
      right={<Chip>{q.data ? `${q.data.total} kết quả` : "…"}</Chip>}>
      <form className="flex flex-wrap items-end gap-2 p-3 border-b border-line shrink-0" onSubmit={(e) => e.preventDefault()} aria-label="Điều kiện lọc">
        <label className="grid gap-[2px] text-[11.5px] text-muted">Khung
          <Seg value={f.tf} onChange={(v) => setF((o) => ({ ...o, tf: v }))} options={tfs} label="Khung thời gian" />
        </label>
        <label className="grid gap-[2px] text-[11.5px] text-muted">Xu hướng
          <select className={SELECT} value={f.trend} onChange={set("trend")}><option value="">Tất cả</option><option value="up">Tăng</option><option value="down">Giảm</option><option value="side">Đi ngang</option></select>
        </label>
        <label className="grid gap-[2px] text-[11.5px] text-muted">Động lượng
          <select className={SELECT} value={f.momentum} onChange={set("momentum")}><option value="">Tất cả</option><option value="overbought">Quá mua</option><option value="oversold">Quá bán</option><option value="bullish">Nghiêng tăng</option><option value="bearish">Nghiêng giảm</option></select>
        </label>
        <label className="grid gap-[2px] text-[11.5px] text-muted">Biến động
          <select className={SELECT} value={f.volatility} onChange={set("volatility")}><option value="">Tất cả</option><option value="squeeze">Squeeze</option><option value="high">Cao</option><option value="normal">Vừa</option><option value="low">Thấp</option></select>
        </label>
        <label className="grid gap-[2px] text-[11.5px] text-muted">RSI từ
          <input className={cn(SELECT, "w-[68px]")} inputMode="decimal" value={f.rsi_min} onChange={set("rsi_min")} placeholder="0" />
        </label>
        <label className="grid gap-[2px] text-[11.5px] text-muted">RSI đến
          <input className={cn(SELECT, "w-[68px]")} inputMode="decimal" value={f.rsi_max} onChange={set("rsi_max")} placeholder="100" />
        </label>
        <label className="grid gap-[2px] text-[11.5px] text-muted">ADX ≥
          <input className={cn(SELECT, "w-[68px]")} inputMode="decimal" value={f.adx_min} onChange={set("adx_min")} placeholder="25" />
        </label>
        <label className="grid gap-[2px] text-[11.5px] text-muted">Heat ≥
          <input className={cn(SELECT, "w-[68px]")} inputMode="decimal" value={f.heat_min} onChange={set("heat_min")} placeholder="50" />
        </label>
        <label className="grid gap-[2px] text-[11.5px] text-muted">Tìm mã
          <input className={cn(SELECT, "w-[110px]")} value={f.q} onChange={set("q")} placeholder="EUR, VN:" />
        </label>
        <button type="button" className="btn" onClick={() => setF({ tf: f.tf, trend: "", momentum: "", volatility: "", q: "", rsi_min: "", rsi_max: "", heat_min: "", adx_min: "" })}>Xoá lọc</button>
      </form>
      <div className="p-3 pt-1 scroll-y lg:max-h-[34rem] min-[2100px]:max-h-none">
        <Async q={q} rows={6} empty="Không có symbol nào khớp điều kiện." hint="Nới lỏng bộ lọc hoặc đổi khung thời gian." isEmpty={(d) => !d.items.length}>
          {(d) => <DataTable data={d.items} columns={columns} minWidth={820} getRowId={(r) => `${r.symbol}:${r.tf}`} initialSort={[{ id: "heat", desc: true }]} />}
        </Async>
      </div>
    </Panel>
  );
}

function CorrMatrix({ c }) {
  const n = c.symbols.length;
  const build = () => {
    const data = [];
    c.matrix.forEach((row, i) => row.forEach((v, j) => data.push([j, i, v == null || i === j ? null : Number(v.toFixed(2))])));
    const axis = { type: "category", data: c.symbols.map(symbolLabel), splitArea: { show: false }, axisLine: { lineStyle: { color: css("--line2") } }, axisTick: { show: false }, axisLabel: { color: css("--muted"), fontSize: 10.5, interval: 0 } };
    return {
      animation: false, backgroundColor: "transparent", grid: { left: 64, right: 12, top: 8, bottom: n > 10 ? 104 : 92 },
      tooltip: { position: "top", backgroundColor: css("--panel2"), borderColor: css("--line2"), textStyle: { color: css("--fg"), fontSize: 12 },
        formatter: (p) => `${symbolLabel(c.symbols[p.value[1]])} / ${symbolLabel(c.symbols[p.value[0]])}: <b>${p.value[2] == null ? "—" : p.value[2].toFixed(2)}</b>` },
      xAxis: { ...axis, axisLabel: { ...axis.axisLabel, rotate: 45 } }, yAxis: { ...axis, inverse: true },
      visualMap: { min: -1, max: 1, calculable: false, orient: "horizontal", left: "center", bottom: 0, itemWidth: 10, itemHeight: 120, text: ["+1", "−1"], textStyle: { color: css("--muted"), fontSize: 11 },
        inRange: { color: [css("--info"), css("--panel2"), css("--accent")] } },
      series: [{ type: "heatmap", data, label: { show: n <= 9, color: css("--fg"), fontSize: 10.5, formatter: (p) => (p.value[2] == null ? "" : p.value[2].toFixed(1)) },
        itemStyle: { borderColor: css("--panel"), borderWidth: 2, borderRadius: 3 }, emphasis: { itemStyle: { borderColor: css("--fg") } } }],
    };
  };
  return <EChart build={build} deps={[c]} height={Math.max(300, Math.min(520, 60 + n * 38))} label={`Ma trận tương quan ${n} symbol, cửa sổ ${c.window} ngày`} />;
}

function Correlation() {
  const q = useCorrelation("D1");
  return (
    <Panel title="Tương quan lăn 30 ngày (D1)" icon={Network} right={<Chip title="Pearson trên log-return">Pearson</Chip>}>
      <Async q={q} rows={8} empty="Chưa đủ dữ liệu D1 để tính tương quan." hint="Cần tối thiểu 2 symbol có đủ ~35 nến D1." isEmpty={(d) => !d.symbols.length}>
        {(c) => (
          <div className="grid gap-3">
            <CorrMatrix c={c} />
            <div className="grid sm:grid-cols-2 gap-3 text-[12.5px]">
              <div>
                <h3 className="m-0 mb-1 text-[12px] font-semibold text-muted">Cặp tương quan mạnh nhất</h3>
                <ul className="m-0 p-0 list-none grid gap-[2px]">
                  {c.top_pairs.slice(0, 6).map((p) => (
                    <li key={p.a + p.b} className="flex justify-between gap-2"><span>{symbolLabel(p.a)} / {symbolLabel(p.b)}</span><span className="num">{signed(p.corr, 2)}</span></li>
                  ))}
                </ul>
              </div>
              <div>
                <h3 className="m-0 mb-1 text-[12px] font-semibold text-muted">Đổi chiều so với 30 ngày trước</h3>
                {c.flips.length ? (
                  <ul className="m-0 p-0 list-none grid gap-[2px]">
                    {c.flips.slice(0, 6).map((p) => (
                      <li key={p.a + p.b} className="flex justify-between gap-2"><span>{symbolLabel(p.a)} / {symbolLabel(p.b)}</span><span className="num">{signed(p.prev, 2)} → {signed(p.now, 2)}</span></li>
                    ))}
                  </ul>
                ) : <p className="m-0 text-muted">Không có cặp nào đổi dấu bất thường.</p>}
              </div>
            </div>
            <p className="m-0 text-[11.5px] text-faint">Dữ liệu tới {c.as_of?.slice(0, 10)}. Tương quan quá khứ không bảo đảm tương lai.</p>
          </div>
        )}
      </Async>
    </Panel>
  );
}

function Sessions({ symbol }) {
  const q = useSessions();
  const item = q.data?.items?.find((i) => i.symbol === symbol);
  const build = () => {
    const axis = { axisLine: { lineStyle: { color: css("--line2") } }, axisLabel: { color: css("--muted"), fontSize: 11 }, splitLine: { lineStyle: { color: css("--line") } } };
    return {
      animation: false, backgroundColor: "transparent", grid: { left: 44, right: 10, top: 10, bottom: 26 },
      tooltip: { trigger: "axis", backgroundColor: css("--panel2"), borderColor: css("--line2"), textStyle: { color: css("--fg"), fontSize: 12 },
        formatter: (a) => `${a[0].axisValue}:00 UTC<br/>Biên độ TB: <b>${a[0].value == null ? "—" : a[0].value.toFixed(3)}%</b>` },
      xAxis: { type: "category", data: item.hourly.map((h) => h.hour), ...axis, splitLine: { show: false }, axisLabel: { ...axis.axisLabel, interval: 2 } },
      yAxis: { type: "value", ...axis, axisLabel: { ...axis.axisLabel, formatter: (v) => `${v}%` } },
      series: [{ type: "bar", data: item.hourly.map((h) => h.avg_range_pct), itemStyle: { color: css("--accent"), borderRadius: [3, 3, 0, 0] }, barMaxWidth: 14 }],
    };
  };
  return (
    <Panel title={`Phiên giao dịch · ${symbolLabel(symbol)}`} icon={Sunrise}>
      <Async q={q} rows={6} empty={`Chưa có thống kê phiên cho ${symbolLabel(symbol)}.`} isEmpty={() => !item}>
        {() => (
          <div className="grid gap-3">
            <div className="grid grid-cols-3 gap-3">
              {Object.entries(item.sessions).map(([k, s]) => (
                <Stat key={k} label={SESSION_LABEL[k] || k} value={s.avg_range_pct == null ? "—" : `${s.avg_range_pct.toFixed(2)}%`}
                  sub={`${String(s.start_utc).padStart(2, "0")}–${String(s.end_utc).padStart(2, "0")}h UTC · ${s.days} ngày`} />
              ))}
            </div>
            <div>
              <h3 className="m-0 text-[12px] font-semibold text-muted">Biên độ trung bình mỗi nến H1 theo giờ (UTC)</h3>
              <EChart build={build} deps={[item]} height={170} label={`Biên độ trung bình theo giờ của ${symbol}`} />
            </div>
            <p className="m-0 text-[11.5px] text-faint">Biên độ ngày trong phiên = (cao nhất − thấp nhất) / giá mở, trung bình {item.days_window} ngày. {item.note}</p>
          </div>
        )}
      </Async>
    </Panel>
  );
}

function Summary({ data }) {
  return (
    <div className="grid gap-3 grid-cols-[repeat(auto-fit,minmax(210px,1fr))]">
      {data.tfs.map((tf) => {
        const s = data.summary.by_tf[tf];
        return (
          <div key={tf} className="panel panel-b">
            <div className="flex items-center justify-between mb-1"><b>{tf}</b><span className="text-[11.5px] text-faint">{s.n} symbol</span></div>
            <div className="flex gap-3 text-[12.5px]">
              <span className="up num">{s.up} tăng</span><span className="down num">{s.down} giảm</span><span className="flat num">{s.side} ngang</span>
            </div>
            <div className="text-[11.5px] text-muted mt-1">Quá mua {s.overbought} · quá bán {s.oversold} · squeeze {s.squeeze} · biến động cao {s.high_vol}</div>
          </div>
        );
      })}
    </div>
  );
}

export default function Analytics({ arg }) {
  const ov = useAnOverview();
  const [sel, setSel] = useState(() => (arg && decodeURIComponent(arg)) || "");
  const now = useNow(10_000);
  const symbol = sel || ov.data?.summary?.top_heat?.[0]?.symbol || ov.data?.symbols?.[0] || "";
  useEffect(() => { if (arg) setSel(decodeURIComponent(arg)); }, [arg]);
  const age = ov.data?.age_seconds;
  const stale = age != null && age > 1800;
  return (
    <>
      <PageHead title="Phân tích" sub="Chỉ báo kỹ thuật tính từ nến đã thu thập (RSI, MACD, ATR, Bollinger, EMA, ADX, Stochastic, Pivot) theo quy tắc minh bạch."
        right={<Freshness now={now} ts={ov.data?.updated_at} source="analytics" label="Lần tính chỉ báo gần nhất" {...FRESH.analytics} />} />
      <div><Disclaimer><b>{NOTE}</b> Hệ thống chỉ mô tả trạng thái và cảnh báo điều kiện, không đưa ra tín hiệu mua/bán và không đặt lệnh.</Disclaimer></div>
      <Async q={ov} rows={8} empty="Chưa có dữ liệu phân tích." hint="Bật service analytics và chạy infra/db/create_analytics_role.sh; cần nến H1 đã thu thập (tối thiểu ~60 nến)." isEmpty={(d) => !d.items.length}>
        {(d) => (
          <div className="grid gap-3">
            <Summary data={d} />
            <div className="an-grid">
              <Panel title="Bản đồ nhiệt trạng thái" icon={Grid3x3} pad={false} className="an-heat" scroll bodyClass="max-lg:max-h-[24rem] max-lg:overflow-y-auto">
                <Heatmap data={d} sel={symbol} onPick={setSel} />
              </Panel>
              {symbol && <Detail symbol={symbol} />}
              <Screener onPick={setSel} sel={symbol} tfs={d.tfs} />
            </div>
            <div className="grid gap-3 xl:grid-cols-2 items-start">
              <Correlation />
              {symbol && <Sessions symbol={symbol} />}
            </div>
          </div>
        )}
      </Async>
    </>
  );
}
