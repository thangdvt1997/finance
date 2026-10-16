// Biểu đồ chuyên nghiệp trên TradingView Lightweight Charts v5 (Apache-2.0): nến/HA/thanh/đường/vùng, nhiều pane chỉ báo,
// công cụ vẽ (DrawingEngine), tín hiệu (markers), so sánh 2 mã (%), log scale, legend theo con trỏ.
// Khung: <div absolute inset-0> trong hộp có kích thước do CSS quyết định -> chart KHÔNG BAO GIỜ tự kéo cao cha (autoSize chỉ đọc kích thước).
import { useEffect, useMemo, useRef, useState } from "react";
import { Eye, EyeOff, Settings2, X } from "lucide-react";
import {
  createChart, CandlestickSeries, BarSeries, LineSeries, AreaSeries, HistogramSeries, CrosshairMode, LineStyle,
  PriceScaleMode, createSeriesMarkers,
} from "lightweight-charts";
import { cn } from "../ui";
import { lget, lset } from "../../lib/lstore";
import { IND, compute, makeCols, heikinAshi } from "./indicators";
import { computeSignals } from "./signals";
import { DrawingEngine, DRAW_COLORS } from "./drawings";
import { dateLocale, t } from "../../lib/i18n";
import { TZ, numLocale } from "../../lib/format";

const css = (n) => getComputedStyle(document.documentElement).getPropertyValue(n).trim();
const hexA = (hex, a) => {
  const m = /^#([0-9a-f]{6})$/i.exec(hex || "");
  if (!m) return hex;
  const n = parseInt(m[1], 16);
  return `rgba(${(n >> 16) & 255},${(n >> 8) & 255},${n & 255},${a})`;
};
// định dạng giờ/ngày trên trục theo ngôn ngữ + múi giờ trong cài đặt; dựng lúc tạo biểu đồ (không phải lúc nạp module)
let fDT, fT, fD, fM, fY;
const initFmt = () => {
  const L = dateLocale(), tz = TZ;
  fDT = new Intl.DateTimeFormat(L, { timeZone: tz, day: "2-digit", month: "2-digit", year: "2-digit", hour: "2-digit", minute: "2-digit", hour12: false });
  fT = new Intl.DateTimeFormat(L, { timeZone: tz, hour: "2-digit", minute: "2-digit", hour12: false });
  fD = new Intl.DateTimeFormat(L, { timeZone: tz, day: "2-digit", month: "2-digit" });
  fM = new Intl.DateTimeFormat(L, { timeZone: tz, month: "short" });
  fY = new Intl.DateTimeFormat(L, { timeZone: tz, year: "numeric" });
};

const lowerBound = (T, t) => {
  let lo = 0, hi = T.length - 1;
  if (hi < 0) return -1;
  if (t <= T[0]) return 0;
  if (t >= T[hi]) return hi;
  while (hi - lo > 1) { const m = (lo + hi) >> 1; if (T[m] <= t) lo = m; else hi = m; }
  return lo;
};

function lineData(values, T, n, step) {
  const out = [];
  let started = false;
  for (let i = 0; i < values.length; i++) {
    const time = i < n ? T[i] : T[n - 1] + (i - n + 1) * step;
    const v = values[i];
    if (v == null) { if (started) out.push({ time }); } else { started = true; out.push({ time, value: v }); }
  }
  return out;
}
const PANE_FMT = { rsi: 2, stoch: 2, adx: 2, cci: 2, wr: 2, atr: "dec", macd: "dec", obv: "vol", volume: "vol" };
const fmtNum = (v, dec) => (v == null ? "—" : Math.abs(v) >= 1e6 ? `${(v / 1e6).toFixed(2)}M` : Math.abs(v) >= 1e4 ? `${(v / 1e3).toFixed(1)}K` : v.toFixed(dec));

export default function ProChart({
  apiRef, symbol, tf, tfSec, bars, decimals = 5, cfg, indicators, serverTf, compare,
  tool, magnet, drawVisible, onToolDone, onIndicatorAction, className,
}) {
  const el = useRef(null);
  const S = useRef({ T: [], live: null });
  const bus = useRef(null);
  const [epoch, setEpoch] = useState(0);
  const [themeVer, setThemeVer] = useState(0);
  const [liveVer, setLiveVer] = useState(0);
  const [indState, setIndState] = useState([]);
  const [paneTops, setPaneTops] = useState([]);
  const [sel, setSel] = useState(null);
  const keyRef = useRef("");
  keyRef.current = `ts-draw:${symbol}:${tf}`;

  // nến làm việc = nến từ API + nến cuối cập nhật từ tick (đẩy lại chỉ báo tối đa ~mỗi 4s)
  const liveBars = useMemo(() => {
    const arr = bars || [];
    const lv = S.current.live;
    if (!lv || !arr.length) return arr;
    const last = arr[arr.length - 1];
    if (lv.t === last.t) return [...arr.slice(0, -1), lv];
    if (lv.t > last.t) return [...arr, lv];
    return arr;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [bars, liveVer]);
  const cols = useMemo(() => makeCols(liveBars), [liveBars]);
  S.current.bars = liveBars; S.current.cols = cols; S.current.tfSec = tfSec; S.current.T = cols.t; S.current.type = cfg.type;

  const theme = () => ({ up: css("--up"), down: css("--down"), accent: css("--accent"), muted: css("--muted"), line: css("--line"), line2: css("--line2"), fg: css("--fg"), panel: css("--panel") });

  // ---------- 1) tạo chart một lần ----------
  useEffect(() => {
    initFmt();
    const c = theme();
    const chart = createChart(el.current, {
      autoSize: true,
      layout: { background: { color: "transparent" }, textColor: c.muted, fontFamily: "Inter Variable, system-ui, sans-serif", fontSize: 11,
        panes: { separatorColor: c.line2, separatorHoverColor: hexA(c.accent, 0.4), enableResize: true } },
      grid: { vertLines: { color: c.line }, horzLines: { color: c.line } },
      crosshair: { mode: CrosshairMode.Normal },
      rightPriceScale: { borderColor: c.line2, scaleMargins: { top: 0.08, bottom: 0.08 } },
      timeScale: {
        borderColor: c.line2, timeVisible: true, secondsVisible: false, rightOffset: 6, minBarSpacing: 0.5,
        tickMarkFormatter: (t, type) => { const d = new Date(t * 1000); return type === 0 ? fY.format(d) : type === 1 ? fM.format(d) : type === 2 ? fD.format(d) : fT.format(d); },
      },
      localization: { locale: dateLocale(), timeFormatter: (t) => fDT.format(new Date(t * 1000)) },
    });
    const vol = chart.addSeries(HistogramSeries, { priceFormat: { type: "volume" }, priceScaleId: "vol", lastValueVisible: false, priceLineVisible: false });
    chart.priceScale("vol").applyOptions({ scaleMargins: { top: 0.86, bottom: 0 } });
    const engine = new DrawingEngine({
      container: el.current,
      onChange: (list) => lset(keyRef.current, list),
      onSelect: (d) => setSel(d),
      onToolDone: () => onToolDoneRef.current?.(),
    });
    S.current.chart = chart; S.current.vol = vol; S.current.engine = engine;
    let raf = 0;
    const onMove = (p) => {
      cancelAnimationFrame(raf);
      raf = requestAnimationFrame(() => {
        const idx = p.time == null || p.point == null ? null : lowerBound(S.current.T, p.time);
        bus.current?.(idx);
        updateTops();
      });
    };
    const updateTops = () => {
      try {
        let y = 0;
        const tops = chart.panes().map((pn) => { const t = y; y += pn.getHeight() + 1; return t; });
        setPaneTops((o) => (o.length === tops.length && o.every((v, i) => v === tops[i]) ? o : tops));
      } catch { /* bỏ qua */ }
    };
    S.current.updateTops = updateTops;
    chart.subscribeCrosshairMove(onMove);
    const ro = new ResizeObserver(() => updateTops());
    ro.observe(el.current);
    const applyTheme = () => {
      const t = theme();
      chart.applyOptions({
        layout: { textColor: t.muted, panes: { separatorColor: t.line2 } },
        grid: { vertLines: { color: t.line }, horzLines: { color: t.line } },
        rightPriceScale: { borderColor: t.line2 }, timeScale: { borderColor: t.line2 },
      });
      engine.setColors({ fg: t.fg, panel: t.panel, muted: t.muted });
      setThemeVer((v) => v + 1); // dựng lại series để lấy màu mới
    };
    engine.setColors({ fg: c.fg, panel: c.panel, muted: c.muted });
    const mo = new MutationObserver(applyTheme);
    mo.observe(document.documentElement, { attributes: true, attributeFilter: ["data-theme"] });
    return () => {
      cancelAnimationFrame(raf); mo.disconnect(); ro.disconnect();
      engine.destroy(); chart.remove();
      S.current.chart = null; S.current.main = null; S.current.engine = null;
    };
  }, []);
  const onToolDoneRef = useRef(onToolDone);
  onToolDoneRef.current = onToolDone;

  // ---------- 2) series chính theo loại biểu đồ ----------
  useEffect(() => {
    const { chart, engine } = S.current;
    if (!chart) return;
    const c = theme();
    if (S.current.main) {
      try { S.current.markers?.detach?.(); } catch { /* đã gỡ */ }
      engine.detach();
      try { chart.removeSeries(S.current.main); } catch { /* đã gỡ */ }
    }
    const t = cfg.type;
    let main;
    if (t === "candles" || t === "ha") main = chart.addSeries(CandlestickSeries, { upColor: c.up, downColor: c.down, wickUpColor: c.up, wickDownColor: c.down, borderVisible: false });
    else if (t === "bars") main = chart.addSeries(BarSeries, { upColor: c.up, downColor: c.down });
    else if (t === "area") main = chart.addSeries(AreaSeries, { lineColor: c.accent, topColor: hexA(c.accent, 0.32), bottomColor: hexA(c.accent, 0.02), lineWidth: 2 });
    else main = chart.addSeries(LineSeries, { color: c.accent, lineWidth: 2 });
    S.current.main = main;
    engine.attach(chart, main);
    S.current.markers = createSeriesMarkers(main, []);
    if (S.current.mainType !== t) S.current.lastKey = null; // đổi loại biểu đồ: áp lại khung nhìn mặc định
    S.current.mainType = t;
    setEpoch((e) => e + 1);
  }, [cfg.type, themeVer]);

  // ---------- 3) dữ liệu nến + volume ----------
  useEffect(() => {
    const { chart, main, vol, engine } = S.current;
    if (!main || !bars) return;
    S.current.live = null;
    const t = cfg.type;
    main.applyOptions({ priceFormat: { type: "price", precision: decimals, minMove: 1 / 10 ** decimals } });
    if (t === "line" || t === "area") main.setData(bars.map((b) => ({ time: b.t, value: b.c })));
    else main.setData((t === "ha" ? heikinAshi(bars) : bars).map((b) => ({ time: b.t, open: b.o, high: b.h, low: b.l, close: b.c })));
    const c = theme();
    vol.setData(bars.map((b) => ({ time: b.t, value: b.v || 0, color: b.c >= b.o ? hexA(c.up, 0.3) : hexA(c.down, 0.3) })));
    engine.setBars(bars, tfSec);
    engine.setFormatter((p) => Number(p).toLocaleString(numLocale(), { minimumFractionDigits: decimals, maximumFractionDigits: decimals }));
    const key = `${symbol}|${tf}`;
    if (bars.length && S.current.lastKey !== key) {
      S.current.lastKey = key;
      chart.timeScale().fitContent();
      if (bars.length > 120) chart.timeScale().setVisibleLogicalRange({ from: bars.length - 110, to: bars.length + 6 });
    }
    S.current.updateTops?.();
  }, [bars, epoch, cfg.type, decimals, symbol, tf, tfSec]);

  // ---------- 4) chỉ báo ----------
  useEffect(() => {
    const { chart, main } = S.current;
    if (!chart || !main) return;
    for (const s of S.current.ind || []) { try { chart.removeSeries(s); } catch { /* đã gỡ */ } }
    S.current.ind = [];
    try { const ps = chart.panes(); for (let i = ps.length - 1; i >= 1; i--) chart.removePane(i); } catch { /* chưa có pane phụ */ }
    const c = theme(), n = cols.n, T = cols.t;
    const state = [];
    let pane = 0;
    if (n > 5) {
      for (const inst of indicators) {
        if (!inst.visible) { state.push({ inst, hidden: true, pane: 0, values: {} }); continue; }
        const def = IND[inst.type];
        if (!def) continue;
        let values;
        try { values = compute(inst.type, inst.params, cols, tfSec); } catch (e) { console.warn("indicator", inst.type, e); continue; }
        const isPane = def.group === "pane";
        if (isPane) pane += 1;
        const idx = isPane ? pane : 0;
        const fmt = PANE_FMT[inst.type];
        const priceFormat = !isPane || fmt === "dec" ? { type: "price", precision: decimals + (isPane ? 1 : 0), minMove: 1 / 10 ** (decimals + (isPane ? 1 : 0)) }
          : fmt === "vol" ? { type: "volume" } : { type: "price", precision: 2, minMove: 0.01 };
        let first = null;
        for (const o of def.outputs) {
          const arr = values[o.key];
          if (!arr) continue;
          const color = inst.colors?.[o.key] || "#f0b84f";
          let s;
          if (o.kind === "histsign" || o.kind === "histvol") {
            s = chart.addSeries(HistogramSeries, { priceFormat, lastValueVisible: false, priceLineVisible: false }, idx);
            s.setData(arr.map((v, i) => (v == null ? { time: T[i] }
              : { time: T[i], value: v, color: o.kind === "histvol" ? (cols.c[i] >= cols.o[i] ? hexA(c.up, 0.5) : hexA(c.down, 0.5)) : v >= 0 ? hexA(c.up, 0.6) : hexA(c.down, 0.6) })));
          } else {
            s = chart.addSeries(LineSeries, {
              color, lineWidth: inst.width || 1.5, lineStyle: o.dashed ? LineStyle.Dashed : LineStyle.Solid, priceFormat,
              priceLineVisible: false, lastValueVisible: isPane, crosshairMarkerVisible: false, title: "",
              lineVisible: o.kind !== "dots", pointMarkersVisible: o.kind === "dots", pointMarkersRadius: 1.6,
            }, idx);
            s.setData(lineData(arr, T, n, tfSec));
          }
          S.current.ind.push(s);
          if (!first) first = s;
        }
        if (first && isPane && def.levels) {
          for (const lv of def.levels) first.createPriceLine({ price: lv, color: c.line2, lineWidth: 1, lineStyle: LineStyle.Dotted, axisLabelVisible: false, title: "" });
        }
        state.push({ inst, pane: idx, values });
      }
    }
    try {
      const ps = chart.panes();
      if (ps.length > 1) ps.forEach((p, i) => p.setStretchFactor(i === 0 ? 2 + ps.length : 1));
    } catch { /* API cũ */ }
    setIndState(state);
    setTimeout(() => S.current.updateTops?.(), 0);
  }, [indicators, cols, tfSec, epoch, decimals]);

  // ---------- 5) tín hiệu ----------
  useEffect(() => {
    const m = S.current.markers;
    if (!m) return;
    if (!cfg.signals?.on) { m.setMarkers([]); return; }
    const c = theme();
    const list = computeSignals(cols, new Set(cfg.signals.kinds || [])).slice(-250);
    m.setMarkers(list.map((s) => ({
      time: s.time, position: s.side === "buy" ? "belowBar" : "aboveBar", shape: s.side === "buy" ? "arrowUp" : "arrowDown",
      color: s.side === "buy" ? c.up : c.down, text: s.text,
    })));
  }, [cols, cfg.signals, epoch]);

  // ---------- 6) so sánh 2 mã (phần trăm) + thang giá ----------
  useEffect(() => {
    const { chart } = S.current;
    if (!chart) return;
    for (const s of S.current.cmp || []) { try { chart.removeSeries(s); } catch { /* đã gỡ */ } }
    S.current.cmp = [];
    const T = S.current.T;
    if (compare?.bars?.length && T.length) {
      const cb = compare.bars; let j = 0, last = null;
      const data = [];
      for (let i = 0; i < T.length; i++) {
        while (j < cb.length && cb[j].t <= T[i]) { last = cb[j].c; j++; }
        if (last != null && cb[0].t <= T[i]) data.push({ time: T[i], value: last });
      }
      const s = chart.addSeries(LineSeries, { color: css("--info") || "#5aa9ff", lineWidth: 2, priceLineVisible: false, title: compare.symbol, lastValueVisible: true, crosshairMarkerVisible: false });
      s.setData(data);
      S.current.cmp.push(s);
    }
    chart.priceScale("right").applyOptions({ mode: compare?.bars?.length ? PriceScaleMode.Percentage : cfg.log ? PriceScaleMode.Logarithmic : PriceScaleMode.Normal, autoScale: cfg.auto !== false });
    chart.priceScale("vol").applyOptions({ visible: false });
    S.current.vol?.applyOptions({ visible: cfg.volume !== false });
  }, [compare, cfg.log, cfg.auto, cfg.volume, epoch, bars]);

  // ---------- 7) pivot từ máy chủ (analytics) ----------
  useEffect(() => {
    const { main } = S.current;
    if (!main) return;
    for (const pl of S.current.pivLines || []) { try { main.removePriceLine(pl); } catch { /* đã gỡ */ } }
    S.current.pivLines = [];
    const pv = serverTf?.pivot;
    if (!cfg.serverPivot || !pv) return;
    const c = theme();
    for (const [k, v] of Object.entries(pv)) {
      if (v == null) continue;
      const col = k === "p" ? c.accent : k.startsWith("r") ? c.down : c.up;
      S.current.pivLines.push(main.createPriceLine({ price: v, color: col, lineWidth: 1, lineStyle: LineStyle.Dashed, axisLabelVisible: true, title: k.toUpperCase() }));
    }
  }, [serverTf, cfg.serverPivot, epoch]);

  // ---------- 8) bản vẽ theo (symbol, khung) + công cụ ----------
  useEffect(() => {
    const e = S.current.engine;
    if (!e) return;
    e.load(lget(keyRef.current, []));
  }, [symbol, tf]);
  useEffect(() => { S.current.engine?.setTool(tool); }, [tool]);
  useEffect(() => { S.current.engine?.setMagnet(magnet); }, [magnet]);
  useEffect(() => { S.current.engine?.setVisible(drawVisible); }, [drawVisible]);

  // ---------- API ra ngoài ----------
  useEffect(() => {
    if (!apiRef) return;
    apiRef.current = {
      /** tick/nến realtime: k = {t,o,h,l,c,v} */
      updateLast(k) {
        const { main, vol, T } = S.current;
        if (!main || !T.length) return;
        const type = S.current.type;
        S.current.live = k;
        let o = k;
        if (type === "ha") {
          const base = S.current.bars, lastB = base[base.length - 1];
          const arr = heikinAshi(lastB && lastB.t === k.t ? [...base.slice(0, -1), k] : [...base, k]);
          o = arr[arr.length - 1] || k;
        }
        try {
          if (type === "line" || type === "area") main.update({ time: k.t, value: k.c });
          else main.update({ time: k.t, open: o.o, high: o.h, low: o.l, close: o.c });
          const c = theme();
          if (k.v != null) vol.update({ time: k.t, value: k.v, color: k.c >= k.o ? hexA(c.up, 0.3) : hexA(c.down, 0.3) });
        } catch { /* nến cũ hơn dữ liệu đã nạp */ }
        if (!S.current.liveTimer) S.current.liveTimer = setTimeout(() => { S.current.liveTimer = null; setLiveVer((v) => v + 1); }, 4000);
      },
      fit: () => S.current.chart?.timeScale().fitContent(),
      toEnd: () => { const ts = S.current.chart?.timeScale(); ts?.scrollToRealTime(); },
      zoomRecent: () => { const n = S.current.T.length; if (n > 120) S.current.chart?.timeScale().setVisibleLogicalRange({ from: n - 110, to: n + 6 }); },
      undo: () => S.current.engine?.undo(),
      clearAll: () => S.current.engine?.clearAll(),
      removeSelected: () => S.current.engine?.removeSelected(),
      cancel: () => S.current.engine?.cancel() || false,
      screenshot: () => {
        const cv = S.current.chart?.takeScreenshot();
        if (!cv) return;
        cv.toBlob((b) => {
          if (!b) return;
          const a = document.createElement("a");
          a.href = URL.createObjectURL(b); a.download = `${symbol}-${tf}.png`; a.click();
          setTimeout(() => URL.revokeObjectURL(a.href), 4000);
        });
      },
    };
  });
  useEffect(() => () => { clearTimeout(S.current.liveTimer); }, []);

  return (
    <div className={cn("relative w-full h-full min-h-0 overflow-hidden", className)}>
      <div ref={el} className="pc-surface absolute inset-0" role="group" aria-label={t("Biểu đồ {symbol} khung {tf}", { symbol, tf })} />
      <Legend bus={bus} bars={liveBars} symbol={symbol} tf={tf} decimals={decimals} inds={indState} paneTops={paneTops} onAction={onIndicatorAction} compare={compare} />
      {sel && (
        <div className="absolute z-20 top-2 left-1/2 -translate-x-1/2 flex items-center gap-1 rounded-md border border-line2 bg-panel/95 px-1.5 py-1 shadow-lg backdrop-blur" role="toolbar" aria-label={t("Kiểu hình vẽ")} data-pc-ui>
          {DRAW_COLORS.map((col) => (
            <button key={col} type="button" aria-label={t("Màu {col}", { col })} aria-pressed={sel.style?.color === col}
              className={cn("h-[18px] w-[18px] rounded-full border-2 cursor-pointer p-0", sel.style?.color === col ? "border-fg" : "border-transparent")}
              style={{ background: col }} onClick={() => S.current.engine?.patchSelected({ color: col })} />
          ))}
          <span className="mx-1 h-4 w-px bg-line2" />
          {[1, 2, 3].map((w) => (
            <button key={w} type="button" aria-label={t("Độ dày {w}", { w })} aria-pressed={Math.round(sel.style?.width || 1.5) === w}
              className={cn("grid h-6 w-6 place-items-center rounded border-0 bg-transparent cursor-pointer text-fg", Math.round(sel.style?.width || 1.5) === w && "bg-panel2")}
              onClick={() => S.current.engine?.patchSelected({ width: w })}><span className="block w-4 bg-current" style={{ height: w }} /></button>
          ))}
          <button type="button" className={cn("h-6 rounded border-0 bg-transparent px-1.5 text-[11px] cursor-pointer text-fg", sel.style?.dash && "bg-panel2")}
            aria-pressed={!!sel.style?.dash} onClick={() => S.current.engine?.patchSelected({ dash: !sel.style?.dash })}>- - -</button>
          <span className="mx-1 h-4 w-px bg-line2" />
          <button type="button" aria-label={t("Xoá hình vẽ")} title={t("Xoá (Del)")} className="grid h-6 w-6 place-items-center rounded border-0 bg-transparent cursor-pointer text-down" onClick={() => S.current.engine?.removeSelected()}><X size={14} /></button>
        </div>
      )}
    </div>
  );
}

/** Legend: OHLC + giá trị chỉ báo tại nến dưới con trỏ (hoặc nến cuối). Tự giữ state để mousemove không render lại cả chart. */
function Legend({ bus, bars, symbol, tf, decimals, inds, paneTops, onAction, compare }) {
  const [hover, setHover] = useState(null);
  useEffect(() => { bus.current = setHover; return () => { bus.current = null; }; }, [bus]);
  const n = bars.length;
  const i = hover == null ? n - 1 : Math.max(0, Math.min(n - 1, hover));
  const b = bars[i], pb = bars[i - 1] || null;
  const chg = b && pb ? ((b.c - pb.c) / pb.c) * 100 : null;
  const tone = b && b.c >= b.o ? "up" : "down";
  const f = (v) => (v == null ? "—" : Number(v).toLocaleString(numLocale(), { minimumFractionDigits: decimals, maximumFractionDigits: decimals }));
  const overlays = inds.filter((x) => IND[x.inst.type]?.group === "overlay");
  const panes = inds.filter((x) => IND[x.inst.type]?.group === "pane" && !x.hidden);
  return (
    <>
      <div className="pointer-events-none absolute left-2 top-1.5 z-10 flex max-w-[calc(100%-5rem)] flex-col gap-[2px] text-[11.5px] leading-tight">
        <div className="flex flex-wrap items-center gap-x-2.5 gap-y-0.5 rounded bg-panel/70 px-1.5 py-[2px] backdrop-blur-[2px]">
          <b className="text-[12.5px]">{symbol.replace(/^(VN|US):/, "")}</b>
          <span className="text-faint">{tf}</span>
          {b && <>
            <span className="num"><span className="text-faint">O</span> <span className={tone}>{f(b.o)}</span></span>
            <span className="num"><span className="text-faint">H</span> <span className={tone}>{f(b.h)}</span></span>
            <span className="num"><span className="text-faint">L</span> <span className={tone}>{f(b.l)}</span></span>
            <span className="num"><span className="text-faint">C</span> <span className={tone}>{f(b.c)}</span></span>
            {chg != null && <span className={cn("num", chg >= 0 ? "up" : "down")}>{chg >= 0 ? "+" : ""}{chg.toFixed(2)}%</span>}
          </>}
          {compare?.symbol && <span className="text-info">vs {compare.symbol.replace(/^(VN|US):/, "")} (%)</span>}
        </div>
        {overlays.map((x) => <LegendRow key={x.inst.id} x={x} i={i} dec={decimals} onAction={onAction} />)}
      </div>
      {panes.map((x) => (
        <div key={x.inst.id} className="pointer-events-none absolute left-2 z-10 text-[11.5px]" style={{ top: (paneTops[x.pane] ?? 0) + 4 }}>
          <LegendRow x={x} i={i} dec={decimals + 1} onAction={onAction} />
        </div>
      ))}
    </>
  );
}

function LegendRow({ x, i, dec, onAction }) {
  const def = IND[x.inst.type];
  const params = def.params.map((p) => x.inst.params?.[p.k] ?? p.def).join(", ");
  return (
    <div className={cn("pointer-events-auto group flex w-fit max-w-full items-center gap-2 rounded bg-panel/70 px-1.5 py-[1px] backdrop-blur-[2px]", x.hidden && "opacity-50")}>
      <span className="font-medium">{def.name}{params && <span className="text-faint"> {params}</span>}</span>
      {!x.hidden && def.outputs.filter((o) => x.values[o.key]).map((o) => {
        const v = x.values[o.key][i];
        return <span key={o.key} className="num" style={{ color: x.inst.colors?.[o.key] }}>{o.kind === "histvol" || x.inst.type === "obv" ? fmtNum(v, 0) : fmtNum(v, x.inst.type === "rsi" || x.inst.type === "stoch" || x.inst.type === "adx" || x.inst.type === "cci" || x.inst.type === "wr" ? 2 : dec)}</span>;
      })}
      <span className="hidden items-center gap-0.5 group-hover:flex">
        <button type="button" className="legend-btn" aria-label={t("Ẩn/hiện")} onClick={() => onAction?.("toggle", x.inst.id)}>{x.hidden ? <EyeOff size={12} /> : <Eye size={12} />}</button>
        <button type="button" className="legend-btn" aria-label={t("Cài đặt chỉ báo")} onClick={() => onAction?.("edit", x.inst.id)}><Settings2 size={12} /></button>
        <button type="button" className="legend-btn" aria-label={t("Gỡ chỉ báo")} onClick={() => onAction?.("remove", x.inst.id)}><X size={12} /></button>
      </span>
    </div>
  );
}
