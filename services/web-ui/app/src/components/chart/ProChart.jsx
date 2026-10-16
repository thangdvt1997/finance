// Biểu đồ chuyên nghiệp trên TradingView Lightweight Charts v5 (Apache-2.0): nến/rỗng/HA/thanh/đường/vùng/baseline/cột + Renko/Range/
// Line Break/Kagi/Point&Figure (tính phía trình duyệt), nhiều pane chỉ báo (tính trong Web Worker), công cụ vẽ (DrawingEngine, lưu server theo
// mã+khung), lớp phủ phiên/lịch/tin/cảnh báo giá (OverlayEngine), tín hiệu, so sánh %, tương quan, đồng bộ crosshair/vùng thời gian giữa nhiều biểu đồ.
// Khung: <div absolute inset-0> trong hộp có kích thước do CSS quyết định -> chart KHÔNG BAO GIỜ tự kéo cao cha (autoSize chỉ đọc kích thước).
import { useEffect, useMemo, useRef, useState } from "react";
import { Copy, Eye, EyeOff, Lock, LockOpen, Settings2, X } from "lucide-react";
import {
  createChart, CandlestickSeries, BarSeries, LineSeries, AreaSeries, BaselineSeries, HistogramSeries, CrosshairMode, LineStyle, LineType,
  PriceScaleMode, createSeriesMarkers,
} from "lightweight-charts";
import { cn } from "../ui";
import { IND, makeCols, heikinAshi } from "./indicators";
import { computeSignals } from "./signals";
import { DrawingEngine, DRAW_COLORS } from "./drawings";
import { OverlayEngine } from "./overlays";
import { deriveBars, isDerived, rollingCorr } from "./charttypes";
import { useIndicatorValues } from "./useIndicators";
import { readLocalDrawings, saveDrawingsServer, serverDrawings, unpackDrawings, useChartPrefs, writeLocalDrawings } from "./chartPrefs";

const css = (n) => getComputedStyle(document.documentElement).getPropertyValue(n).trim();
const hexA = (hex, a) => {
  const m = /^#([0-9a-f]{6})$/i.exec(hex || "");
  if (!m) return hex;
  const n = parseInt(m[1], 16);
  return `rgba(${(n >> 16) & 255},${(n >> 8) & 255},${n & 255},${a})`;
};
const TZ = "Asia/Ho_Chi_Minh";
const fDT = new Intl.DateTimeFormat("vi-VN", { timeZone: TZ, day: "2-digit", month: "2-digit", year: "2-digit", hour: "2-digit", minute: "2-digit", hour12: false });
const fT = new Intl.DateTimeFormat("vi-VN", { timeZone: TZ, hour: "2-digit", minute: "2-digit", hour12: false });
const fD = new Intl.DateTimeFormat("vi-VN", { timeZone: TZ, day: "2-digit", month: "2-digit" });
const fM = new Intl.DateTimeFormat("vi-VN", { timeZone: TZ, month: "short" });
const fY = new Intl.DateTimeFormat("vi-VN", { timeZone: TZ, year: "numeric" });
const dayKey = (t) => Math.floor(t / 86400);

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
const CLEAR = "rgba(0,0,0,0)";

export default function ProChart({
  apiRef, symbol, tf, tfSec, bars, decimals = 5, cfg, indicators, serverTf, compare, drawSymbol,
  tool, magnet, drawVisible, onToolDone, onIndicatorAction, className, label,
  ov, onAlertCreate, onAlertMove, onCrosshairTime, onVisibleRange, onNeedMore, pickMode, onPickBar, onFocusCell, onDrawingsChange, onHistory, replayOn,
}) {
  const el = useRef(null);
  const S = useRef({ T: [], live: null });
  const bus = useRef(null);
  const cb = useRef({});
  cb.current = { onCrosshairTime, onVisibleRange, onNeedMore, onPickBar, onAlertCreate, onAlertMove, onDrawingsChange, onHistory, onToolDone, pickMode };
  const [epoch, setEpoch] = useState(0);
  const [themeVer, setThemeVer] = useState(0);
  const [liveVer, setLiveVer] = useState(0);
  const [indState, setIndState] = useState([]);
  const [paneTops, setPaneTops] = useState([]);
  const [sel, setSel] = useState(null);
  const [edit, setEdit] = useState(null);
  const [tip, setTip] = useState(null);
  const cfgRef = useRef(cfg);
  cfgRef.current = cfg;
  const type = cfg.type;
  const derivedMode = isDerived(type);
  const drawSym = drawSymbol || symbol;
  const drawTf = derivedMode ? `${tf}~${type}` : tf;
  const keyRef = useRef({ s: drawSym, tf: drawTf });
  keyRef.current = { s: drawSym, tf: drawTf };
  const style = cfg.style || {};
  const ps = style.scaleSide === "left" ? "left" : "right";
  const styleSig = `${style.up || ""}|${style.down || ""}|${style.grid || ""}|${ps}`;
  const prefs = useChartPrefs();

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
  const derived = useMemo(() => (derivedMode ? deriveBars(type, liveBars, tfSec, cfg.boxSize || 0) : null), [derivedMode, type, liveBars, tfSec, cfg.boxSize]);
  const dispBars = derived ? derived.bars : liveBars;
  const cols = useMemo(() => makeCols(dispBars), [dispBars]);
  const ind = useIndicatorValues(indicators, cols, tfSec);
  S.current.bars = dispBars; S.current.raw = liveBars; S.current.cols = cols; S.current.tfSec = tfSec; S.current.T = cols.t; S.current.type = type; S.current.derived = derived;

  const theme = () => {
    const st = cfgRef.current.style || {};
    return { up: st.up || css("--up"), down: st.down || css("--down"), accent: css("--accent"), muted: css("--muted"), line: css("--line"), line2: css("--line2"), fg: css("--fg"), panel: css("--panel"), info: css("--info") };
  };
  const gridColors = (c) => { const g = cfgRef.current.style?.grid || "both"; return { v: g === "both" || g === "v" ? c.line : CLEAR, h: g === "both" || g === "h" ? c.line : CLEAR }; };

  // ---------- 1) tạo chart một lần ----------
  useEffect(() => {
    const c = theme(), gc = gridColors(c);
    const chart = createChart(el.current, {
      autoSize: true,
      layout: { background: { color: "transparent" }, textColor: c.muted, fontFamily: "Inter Variable, system-ui, sans-serif", fontSize: 11,
        panes: { separatorColor: c.line2, separatorHoverColor: hexA(c.accent, 0.4), enableResize: true } },
      grid: { vertLines: { color: gc.v }, horzLines: { color: gc.h } },
      crosshair: { mode: CrosshairMode.Normal },
      rightPriceScale: { borderColor: c.line2, scaleMargins: { top: 0.08, bottom: 0.08 } },
      leftPriceScale: { borderColor: c.line2, scaleMargins: { top: 0.08, bottom: 0.08 }, visible: false },
      timeScale: {
        borderColor: c.line2, timeVisible: true, secondsVisible: false, rightOffset: 6, minBarSpacing: 0.02,
        tickMarkFormatter: (t, type2) => { const d = new Date(t * 1000); return type2 === 0 ? fY.format(d) : type2 === 1 ? fM.format(d) : type2 === 2 ? fD.format(d) : fT.format(d); },
      },
      localization: { locale: "vi-VN", timeFormatter: (t) => fDT.format(new Date(t * 1000)) },
    });
    const vol = chart.addSeries(HistogramSeries, { priceFormat: { type: "volume" }, priceScaleId: "vol", lastValueVisible: false, priceLineVisible: false });
    chart.priceScale("vol").applyOptions({ scaleMargins: { top: 0.86, bottom: 0 } });
    // Overlay TẠO TRƯỚC engine vẽ để bắt chuột (kéo/tạo cảnh báo) trước DrawingEngine.
    const overlay = new OverlayEngine({
      container: el.current,
      onAlertCreate: (p) => cb.current.onAlertCreate?.(p),
      onAlertMove: (id, p) => cb.current.onAlertMove?.(id, p),
      onHover: (h) => setTip(h),
    });
    const engine = new DrawingEngine({
      container: el.current,
      onChange: (list) => {
        const k = keyRef.current, ts = Date.now();
        writeLocalDrawings(k.s, k.tf, list, ts);
        S.current.drawTs = ts;
        saveDrawingsServer(k.s, k.tf, list, ts);
        cb.current.onDrawingsChange?.(list);
        cb.current.onHistory?.({ undo: engine.canUndo(), redo: engine.canRedo() });
      },
      onSelect: (d) => setSel(d),
      onToolDone: () => cb.current.onToolDone?.(),
      onEditText: (d) => setEdit({ id: d.id, text: d.name || "" }),
    });
    S.current.chart = chart; S.current.vol = vol; S.current.engine = engine; S.current.overlay = overlay;
    let raf = 0;
    const onMove = (p) => {
      // phát crosshair cho các biểu đồ khác (đồng bộ) — bỏ qua tiếng vọng do chính ta đặt vị trí
      const now = performance.now();
      if (!S.current.inExt && now - (S.current.extAt || 0) > 80) cb.current.onCrosshairTime?.(p.time == null || p.point == null ? null : p.time);
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
    const onClick = (p) => { if (cb.current.pickMode && p.time != null) cb.current.onPickBar?.(p.time); };
    chart.subscribeClick(onClick);
    // vùng thời gian: phát cho biểu đồ khác + tải thêm lịch sử khi kéo sát mép trái
    const onRange = (r) => {
      if (!r) return;
      const now = performance.now();
      if (r.from < 40 && now - (S.current.moreAt || 0) > 600 && S.current.T.length) { S.current.moreAt = now; cb.current.onNeedMore?.(S.current.T[0]); }
    };
    chart.timeScale().subscribeVisibleLogicalRangeChange(onRange);
    const onTimeRange = (r) => {
      if (!r) return;
      const now = performance.now();
      if (now - (S.current.rangeAt || 0) < 120) return; // đang áp từ biểu đồ khác
      cb.current.onVisibleRange?.(r);
    };
    chart.timeScale().subscribeVisibleTimeRangeChange(onTimeRange);
    const ro = new ResizeObserver(() => updateTops());
    ro.observe(el.current);
    const applyTheme = () => {
      const t = theme(), g2 = gridColors(t);
      chart.applyOptions({
        layout: { textColor: t.muted, panes: { separatorColor: t.line2 } },
        grid: { vertLines: { color: g2.v }, horzLines: { color: g2.h } },
        rightPriceScale: { borderColor: t.line2 }, leftPriceScale: { borderColor: t.line2 }, timeScale: { borderColor: t.line2 },
      });
      engine.setColors({ fg: t.fg, panel: t.panel, muted: t.muted });
      overlay.set({ colors: { up: t.up, down: t.down, fg: t.fg, panel: t.panel, muted: t.muted, accent: t.accent, line: t.line } });
      setThemeVer((v) => v + 1); // dựng lại series để lấy màu mới
    };
    engine.setColors({ fg: c.fg, panel: c.panel, muted: c.muted });
    overlay.set({ colors: { up: c.up, down: c.down, fg: c.fg, panel: c.panel, muted: c.muted, accent: c.accent, line: c.line } });
    const mo = new MutationObserver(applyTheme);
    mo.observe(document.documentElement, { attributes: true, attributeFilter: ["data-theme"] });
    S.current.applyTheme = applyTheme;
    return () => {
      cancelAnimationFrame(raf); mo.disconnect(); ro.disconnect();
      engine.destroy(); overlay.destroy(); chart.remove();
      S.current.chart = null; S.current.main = null; S.current.engine = null; S.current.overlay = null;
    };
  }, []);

  // kiểu hiển thị (màu nến, lưới, phía thang giá)
  useEffect(() => {
    const { chart } = S.current;
    if (!chart) return;
    S.current.applyTheme?.();
    chart.applyOptions({ rightPriceScale: { visible: ps === "right" }, leftPriceScale: { visible: ps === "left" } });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [styleSig]);

  // ---------- 2) series chính theo loại biểu đồ ----------
  useEffect(() => {
    const { chart, engine, overlay } = S.current;
    if (!chart) return;
    const c = theme();
    if (S.current.main) {
      try { S.current.markers?.detach?.(); } catch { /* đã gỡ */ }
      engine.detach(); overlay.detach();
      try { chart.removeSeries(S.current.main); } catch { /* đã gỡ */ }
    }
    const t = cfg.type;
    const base = { priceScaleId: ps };
    let main;
    if (t === "candles" || t === "ha" || t === "renko" || t === "range" || t === "linebreak") main = chart.addSeries(CandlestickSeries, { ...base, upColor: c.up, downColor: c.down, wickUpColor: c.up, wickDownColor: c.down, borderVisible: false });
    else if (t === "hollow") main = chart.addSeries(CandlestickSeries, { ...base, upColor: CLEAR, downColor: c.down, borderUpColor: c.up, borderDownColor: c.down, wickUpColor: c.up, wickDownColor: c.down, borderVisible: true });
    else if (t === "pnf") main = chart.addSeries(CandlestickSeries, { ...base, upColor: CLEAR, downColor: CLEAR, wickUpColor: CLEAR, wickDownColor: CLEAR, borderVisible: false, lastValueVisible: false, priceLineVisible: false });
    else if (t === "bars") main = chart.addSeries(BarSeries, { ...base, upColor: c.up, downColor: c.down });
    else if (t === "area") main = chart.addSeries(AreaSeries, { ...base, lineColor: c.accent, topColor: hexA(c.accent, 0.32), bottomColor: hexA(c.accent, 0.02), lineWidth: 2 });
    else if (t === "baseline") main = chart.addSeries(BaselineSeries, { ...base, topLineColor: c.up, bottomLineColor: c.down, topFillColor1: hexA(c.up, 0.28), topFillColor2: hexA(c.up, 0.04), bottomFillColor1: hexA(c.down, 0.04), bottomFillColor2: hexA(c.down, 0.28), lineWidth: 2 });
    else if (t === "columns") main = chart.addSeries(HistogramSeries, { ...base, color: c.accent });
    else if (t === "kagi") main = chart.addSeries(LineSeries, { ...base, color: c.up, lineWidth: 2, lineType: LineType.WithSteps });
    else main = chart.addSeries(LineSeries, { ...base, color: c.accent, lineWidth: 2 });
    S.current.main = main;
    engine.attach(chart, main);
    overlay.attach(chart, main);
    S.current.markers = createSeriesMarkers(main, []);
    if (S.current.mainType !== t) S.current.lastKey = null; // đổi loại biểu đồ: áp lại khung nhìn mặc định
    S.current.mainType = t;
    setEpoch((e) => e + 1);
  }, [cfg.type, themeVer, ps]);

  // ---------- 3) dữ liệu nến + volume ----------
  useEffect(() => {
    const { chart, main, vol, engine, overlay } = S.current;
    if (!main || !bars) return;
    S.current.live = null;
    const t = cfg.type;
    const src = S.current.raw || bars;
    main.applyOptions({ priceFormat: { type: "price", precision: decimals, minMove: 1 / 10 ** decimals } });
    const c = theme();
    const key = `${symbol}|${tf}`;
    const keep = S.current.lastKey === key && S.current.firstT != null && dispBars.length && dispBars[0].t < S.current.firstT && !derivedMode ? chart.timeScale().getVisibleRange() : null;
    if (t === "line" || t === "area") main.setData(dispBars.map((b) => ({ time: b.t, value: b.c })));
    else if (t === "baseline") {
      const cl = dispBars.map((b) => b.c).slice(-300);
      const lo = Math.min(...cl), hi = Math.max(...cl);
      main.applyOptions({ baseValue: { type: "price", price: cl.length ? (lo + hi) / 2 : 0 } });
      main.setData(dispBars.map((b) => ({ time: b.t, value: b.c })));
    } else if (t === "columns") main.setData(dispBars.map((b, i) => ({ time: b.t, value: b.c, color: b.c >= (dispBars[i - 1]?.c ?? b.o) ? hexA(c.up, 0.85) : hexA(c.down, 0.85) })));
    else if (t === "kagi") main.setData((derived?.extra || []).map((p) => ({ time: p.t, value: p.price, color: p.yang ? c.up : c.down })));
    else if (t === "ha") main.setData(heikinAshi(src).map((b) => ({ time: b.t, open: b.o, high: b.h, low: b.l, close: b.c })));
    else main.setData(dispBars.map((b) => ({ time: b.t, open: b.o, high: b.h, low: b.l, close: b.c })));
    if (derivedMode) vol.setData([]);
    else vol.setData(bars.map((b) => ({ time: b.t, value: b.v || 0, color: b.c >= b.o ? hexA(c.up, 0.3) : hexA(c.down, 0.3) })));
    engine.setBars(dispBars, tfSec);
    engine.setFormatter((p) => Number(p).toLocaleString("en-US", { minimumFractionDigits: decimals, maximumFractionDigits: decimals }));
    overlay.set({ T: cols.t, step: tfSec, tfSec, nonTime: derivedMode, pnf: t === "pnf" && derived?.extra ? { cols: derived.extra, box: derived.size } : null,
      fmt: (p) => Number(p).toLocaleString("en-US", { minimumFractionDigits: decimals, maximumFractionDigits: decimals }) });
    if (keep) { try { chart.timeScale().setVisibleRange(keep); } catch { /* ngoài dữ liệu */ } }
    S.current.firstT = dispBars.length ? dispBars[0].t : null;
    if (dispBars.length && S.current.lastKey !== key) {
      S.current.lastKey = key;
      chart.timeScale().fitContent();
      if (dispBars.length > 120) chart.timeScale().setVisibleLogicalRange({ from: dispBars.length - 110, to: dispBars.length + 6 });
    }
    S.current.updateTops?.();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [bars, dispBars, epoch, cfg.type, decimals, symbol, tf, tfSec]);

  // ---------- 4) chỉ báo (giá trị tính trong Web Worker) ----------
  useEffect(() => {
    const { chart, main } = S.current;
    if (!chart || !main) return;
    if (ind.key !== cols) return; // giá trị còn của dữ liệu cũ: giữ nguyên đường cũ đến khi worker trả bản mới
    for (const s of S.current.ind || []) { try { chart.removeSeries(s); } catch { /* đã gỡ */ } }
    S.current.ind = [];
    try { const ps2 = chart.panes(); for (let i = ps2.length - 1; i >= 1; i--) chart.removePane(i); } catch { /* chưa có pane phụ */ }
    const c = theme(), n = cols.n, T = cols.t;
    const state = [];
    let pane = 0;
    if (n > 5) {
      for (const inst of indicators) {
        if (!inst.visible) { state.push({ inst, hidden: true, pane: 0, values: {} }); continue; }
        const def = IND[inst.type];
        const values = ind.values.get(inst.id);
        if (!def || !values) continue;
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
            s = chart.addSeries(HistogramSeries, { priceFormat, lastValueVisible: false, priceLineVisible: false, priceScaleId: ps }, idx);
            s.setData(arr.map((v, i) => (v == null ? { time: T[i] }
              : { time: T[i], value: v, color: o.kind === "histvol" ? (cols.c[i] >= cols.o[i] ? hexA(c.up, 0.5) : hexA(c.down, 0.5)) : v >= 0 ? hexA(c.up, 0.6) : hexA(c.down, 0.6) })));
          } else {
            s = chart.addSeries(LineSeries, {
              color, lineWidth: inst.width || 1.5, lineStyle: o.dashed ? LineStyle.Dashed : LineStyle.Solid, priceFormat, priceScaleId: ps,
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
    // pane tương quan (khi đang so sánh 2 mã và bật hiển thị)
    if (cfg.corr && compare?.bars?.length && n > 60) {
      pane += 1;
      const cr = rollingCorr(dispBars, compare.bars, cfg.corrWin || 50);
      const s = chart.addSeries(LineSeries, { color: c.info || "#5aa9ff", lineWidth: 1.5, priceScaleId: ps, priceFormat: { type: "price", precision: 2, minMove: 0.01 }, priceLineVisible: false, lastValueVisible: true, crosshairMarkerVisible: false, title: "" }, pane);
      s.setData(lineData(cr, T, n, tfSec));
      for (const lv of [-0.5, 0, 0.5]) s.createPriceLine({ price: lv, color: c.line2, lineWidth: 1, lineStyle: LineStyle.Dotted, axisLabelVisible: false, title: "" });
      S.current.ind.push(s);
      state.push({ inst: { id: "corr", type: "corr", params: {}, colors: { v: c.info } }, pane, values: { v: cr }, corr: true });
    }
    try {
      const ps2 = chart.panes();
      if (ps2.length > 1) ps2.forEach((p, i) => p.setStretchFactor(i === 0 ? 2 + ps2.length : 1));
    } catch { /* API cũ */ }
    setIndState(state);
    setTimeout(() => S.current.updateTops?.(), 0);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [indicators, ind, epoch, decimals, cfg.corr, cfg.corrWin, compare, ps]);

  // ---------- 5) tín hiệu ----------
  useEffect(() => {
    const m = S.current.markers;
    if (!m) return;
    if (!cfg.signals?.on || derivedMode) { m.setMarkers([]); return; }
    const c = theme();
    const list = computeSignals(cols, new Set(cfg.signals.kinds || [])).slice(-250);
    m.setMarkers(list.map((s) => ({
      time: s.time, position: s.side === "buy" ? "belowBar" : "aboveBar", shape: s.side === "buy" ? "arrowUp" : "arrowDown",
      color: s.side === "buy" ? c.up : c.down, text: s.text,
    })));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [cols, cfg.signals, epoch, derivedMode]);

  // ---------- 6) so sánh 2 mã (phần trăm) + thang giá ----------
  useEffect(() => {
    const { chart } = S.current;
    if (!chart) return;
    for (const s of S.current.cmp || []) { try { chart.removeSeries(s); } catch { /* đã gỡ */ } }
    S.current.cmp = [];
    const T = S.current.T;
    const ovCmp = compare?.bars?.length && (compare.mode || "pct") === "pct" && !derivedMode;
    if (ovCmp && T.length) {
      const cb2 = compare.bars; let j = 0, last = null;
      const data = [];
      for (let i = 0; i < T.length; i++) {
        while (j < cb2.length && cb2[j].t <= T[i]) { last = cb2[j].c; j++; }
        if (last != null && cb2[0].t <= T[i]) data.push({ time: T[i], value: last });
      }
      const s = chart.addSeries(LineSeries, { color: css("--info") || "#5aa9ff", lineWidth: 2, priceScaleId: ps, priceLineVisible: false, title: compare.symbol, lastValueVisible: true, crosshairMarkerVisible: false });
      s.setData(data);
      S.current.cmp.push(s);
    }
    const pct = ovCmp || cfg.pct;
    chart.priceScale(ps).applyOptions({ mode: pct ? PriceScaleMode.Percentage : cfg.log ? PriceScaleMode.Logarithmic : PriceScaleMode.Normal, autoScale: cfg.auto !== false });
    chart.priceScale("vol").applyOptions({ visible: false });
    S.current.vol?.applyOptions({ visible: cfg.volume !== false && !derivedMode && type !== "columns" });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [compare, cfg.log, cfg.auto, cfg.volume, cfg.pct, epoch, bars, ps, derivedMode]);

  // ---------- 7) pivot máy chủ + đường tham chiếu (đóng cửa trước / mở cửa ngày) ----------
  useEffect(() => {
    const { main } = S.current;
    if (!main) return;
    for (const pl of S.current.pivLines || []) { try { main.removePriceLine(pl); } catch { /* đã gỡ */ } }
    S.current.pivLines = [];
    const c = theme();
    const pv = serverTf?.pivot;
    if (cfg.serverPivot && pv) {
      for (const [k, v] of Object.entries(pv)) {
        if (v == null) continue;
        const col = k === "p" ? c.accent : k.startsWith("r") ? c.down : c.up;
        S.current.pivLines.push(main.createPriceLine({ price: v, color: col, lineWidth: 1, lineStyle: LineStyle.Dashed, axisLabelVisible: true, title: k.toUpperCase() }));
      }
    }
    const raw = S.current.raw || [];
    if ((cfg.prevClose || cfg.dayOpen) && raw.length > 1 && !derivedMode) {
      const last = raw[raw.length - 1], dk = tfSec >= 86400 ? null : dayKey(last.t);
      let i = raw.length - 1;
      if (dk == null) {
        if (cfg.prevClose) S.current.pivLines.push(main.createPriceLine({ price: raw[raw.length - 2].c, color: c.muted, lineWidth: 1, lineStyle: LineStyle.Dashed, axisLabelVisible: true, title: "Đóng cửa trước" }));
      } else {
        while (i > 0 && dayKey(raw[i - 1].t) === dk) i--;
        if (cfg.dayOpen) S.current.pivLines.push(main.createPriceLine({ price: raw[i].o, color: c.accent, lineWidth: 1, lineStyle: LineStyle.Dotted, axisLabelVisible: true, title: "Mở cửa ngày" }));
        if (cfg.prevClose && i > 0) S.current.pivLines.push(main.createPriceLine({ price: raw[i - 1].c, color: c.muted, lineWidth: 1, lineStyle: LineStyle.Dashed, axisLabelVisible: true, title: "Đóng cửa trước" }));
      }
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [serverTf, cfg.serverPivot, cfg.prevClose, cfg.dayOpen, epoch, bars, derivedMode]);

  // ---------- 8) bản vẽ theo (mã, khung): localStorage + máy chủ (user_prefs) ----------
  useEffect(() => {
    const e = S.current.engine;
    if (!e) return;
    const loc = readLocalDrawings(drawSym, drawTf);
    const srv = prefs.loaded && prefs.available ? serverDrawings(prefs.prefs, drawSym, drawTf) : null;
    if (srv && (srv.u || 0) > (loc.ts || 0)) {
      const list = unpackDrawings(srv.d);
      writeLocalDrawings(drawSym, drawTf, list, srv.u);
      S.current.drawTs = srv.u;
      e.load(list);
    } else {
      S.current.drawTs = loc.ts || 0;
      e.load(loc.list);
      // bản cục bộ mới hơn máy chủ (hoặc máy chủ chưa có) -> đẩy lên
      if (prefs.loaded && prefs.available && loc.list.length && (!srv || (loc.ts || 0) > (srv.u || 0))) saveDrawingsServer(drawSym, drawTf, loc.list, loc.ts || Date.now());
    }
    cb.current.onDrawingsChange?.(e.get());
    cb.current.onHistory?.({ undo: false, redo: false });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [drawSym, drawTf, prefs.loaded, prefs.available]);
  // bản vẽ đổi ở nơi khác (tab/thiết bị khác) -> nạp lại nếu máy chủ mới hơn bản đang có
  useEffect(() => {
    const e = S.current.engine;
    if (!e || !(prefs.loaded && prefs.available)) return;
    const srv = serverDrawings(prefs.prefs, drawSym, drawTf);
    if (srv && (srv.u || 0) > (S.current.drawTs || 0)) {
      const list = unpackDrawings(srv.d);
      writeLocalDrawings(drawSym, drawTf, list, srv.u);
      S.current.drawTs = srv.u;
      e.replace(list);
      cb.current.onDrawingsChange?.(e.get());
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [prefs.prefs]);
  useEffect(() => { S.current.engine?.setTool(tool); }, [tool]);
  useEffect(() => { S.current.engine?.setMagnet(magnet); }, [magnet]);
  useEffect(() => { S.current.engine?.setVisible(drawVisible); }, [drawVisible]);
  useEffect(() => { S.current.engine?.setPassive(!!pickMode); }, [pickMode]);

  // ---------- 9) lớp phủ: phiên, sự kiện/tin, cảnh báo ----------
  useEffect(() => {
    const o = S.current.overlay;
    if (!o) return;
    o.set({
      sessions: { on: !!cfg.sessions?.on, ids: cfg.sessions?.ids || ["tokyo", "london", "newyork"], lines: cfg.sessions?.lines !== false },
      marks: ov?.marks || [], alerts: ov?.alerts || [], alertMode: !!ov?.alertMode, noDrag: !!replayOn,
    });
  }, [cfg.sessions, ov?.marks, ov?.alerts, ov?.alertMode, replayOn, epoch]);
  useEffect(() => { el.current?.classList.toggle("pc-draw", !!ov?.alertMode || !!pickMode); }, [ov?.alertMode, pickMode]);

  // ---------- API ra ngoài ----------
  useEffect(() => {
    if (!apiRef) return;
    apiRef.current = {
      /** tick/nến realtime: k = {t,o,h,l,c,v} */
      updateLast(k) {
        const { main, vol, T } = S.current;
        if (!main || !T.length) return;
        const ty = S.current.type;
        S.current.live = k;
        if (el.current) el.current.dataset.liveN = String((Number(el.current.dataset.liveN) || 0) + 1);
        if (isDerived(ty)) {
          if (!S.current.liveTimer) S.current.liveTimer = setTimeout(() => { S.current.liveTimer = null; setLiveVer((v) => v + 1); }, 1500);
          return;
        }
        let o = k;
        if (ty === "ha") {
          const base = S.current.raw, lastB = base[base.length - 1];
          const arr = heikinAshi(lastB && lastB.t === k.t ? [...base.slice(0, -1), k] : [...base, k]);
          o = arr[arr.length - 1] || k;
        }
        try {
          const c = theme();
          if (ty === "line" || ty === "area" || ty === "baseline") main.update({ time: k.t, value: k.c });
          else if (ty === "columns") main.update({ time: k.t, value: k.c, color: k.c >= k.o ? hexA(c.up, 0.85) : hexA(c.down, 0.85) });
          else main.update({ time: k.t, open: o.o, high: o.h, low: o.l, close: o.c });
          if (k.v != null) vol.update({ time: k.t, value: k.v, color: k.c >= k.o ? hexA(c.up, 0.3) : hexA(c.down, 0.3) });
        } catch { /* nến cũ hơn dữ liệu đã nạp */ }
        // chỉ báo/tín hiệu tính lại thưa hơn khi dữ liệu lớn (20.000 nến ~ 12s) để thao tác kéo/zoom luôn mượt
        if (!S.current.liveTimer) S.current.liveTimer = setTimeout(() => { S.current.liveTimer = null; setLiveVer((v) => v + 1); }, Math.min(15000, 4000 + (T.length / 1000) * 400));
      },
      fit: () => S.current.chart?.timeScale().fitContent(),
      toEnd: () => { const ts = S.current.chart?.timeScale(); ts?.scrollToRealTime(); },
      zoomRecent: () => { const n = S.current.T.length; if (n > 120) S.current.chart?.timeScale().setVisibleLogicalRange({ from: n - 110, to: n + 6 }); },
      /** căn khung nhìn quanh nến thứ i (replay) */
      focusIndex: (i, span = 110) => { const ts = S.current.chart?.timeScale(); if (ts) { try { ts.setVisibleLogicalRange({ from: i - span + 8, to: i + 8 }); } catch { /* bỏ qua */ } } },
      undo: () => S.current.engine?.undo(),
      redo: () => S.current.engine?.redo(),
      clearAll: () => S.current.engine?.clearAll(),
      removeSelected: () => S.current.engine?.removeSelected(),
      duplicateSelected: () => S.current.engine?.duplicateSelected(),
      cancel: () => S.current.engine?.cancel() || false,
      drawings: {
        list: () => S.current.engine?.get() || [],
        selectedId: () => S.current.engine?.selectedId || null,
        patch: (id, p, styleOnly) => S.current.engine?.patch(id, p, styleOnly),
        remove: (id) => S.current.engine?.remove(id),
        select: (id) => S.current.engine?.select(id),
      },
      // ---- đồng bộ ----
      setCrosshair(t) {
        const { chart, main, T, cols: cl } = S.current;
        if (!chart || !main || !T.length) return;
        const i = lowerBound(T, t);
        if (i < 0 || t > T[T.length - 1] + tfSec * 2 || t < T[0]) { this.clearCrosshair(); return; }
        S.current.inExt = true; S.current.extAt = performance.now();
        try { chart.setCrosshairPosition(cl.c[i], T[i], main); if (el.current) el.current.dataset.ext = String(T[i]); } catch { /* chưa có dữ liệu */ }
        S.current.inExt = false;
      },
      clearCrosshair() {
        const { chart } = S.current;
        if (!chart) return;
        S.current.inExt = true; S.current.extAt = performance.now();
        try { chart.clearCrosshairPosition(); if (el.current) el.current.dataset.ext = ""; } catch { /* bỏ qua */ }
        S.current.inExt = false;
      },
      setRange(r) {
        const { chart } = S.current;
        if (!chart || !r) return;
        S.current.rangeAt = performance.now();
        try { chart.timeScale().setVisibleRange({ from: r.from, to: r.to }); } catch { /* ngoài dữ liệu */ }
      },
      getRange: () => { try { return S.current.chart?.timeScale().getVisibleRange(); } catch { return null; } },
      // ---- ảnh chụp ----
      screenshotCanvas: () => snapshot(S.current.chart, label || `${symbol} · ${tf}`),
      screenshot() {
        const cv = snapshot(S.current.chart, label || `${symbol} · ${tf}`);
        if (!cv) return;
        cv.toBlob((b) => {
          if (!b) return;
          const a = document.createElement("a");
          a.href = URL.createObjectURL(b); a.download = `${String(symbol).replace(/[^\w.-]/g, "_")}-${tf}.png`; a.click();
          setTimeout(() => URL.revokeObjectURL(a.href), 4000);
        });
      },
      async copyImage() {
        const cv = snapshot(S.current.chart, label || `${symbol} · ${tf}`);
        if (!cv) return false;
        try {
          const blob = await new Promise((res) => cv.toBlob(res, "image/png"));
          await navigator.clipboard.write([new ClipboardItem({ "image/png": blob })]);
          return true;
        } catch { return false; }
      },
    };
  });
  useEffect(() => () => { clearTimeout(S.current.liveTimer); }, []);

  const commitEdit = (ok) => {
    const e = edit;
    setEdit(null);
    if (!e) return;
    if (ok && e.text.trim()) S.current.engine?.patch(e.id, { name: e.text.trim().slice(0, 120) });
  };

  return (
    <div className={cn("relative w-full h-full min-h-0 overflow-hidden", className)} onPointerDownCapture={() => onFocusCell?.()}>
      <div ref={el} className="pc-surface absolute inset-0" role="group" aria-label={`Biểu đồ ${symbol} khung ${tf}`} />
      <Legend bus={bus} bars={dispBars} symbol={label || symbol} tf={tf} decimals={decimals} inds={indState} paneTops={paneTops} onAction={onIndicatorAction} compare={compare} typeLabel={derivedMode ? derived?.size : null} />
      {tip && (
        <div className="pointer-events-none absolute z-30 max-w-[280px] rounded-md border border-line2 bg-panel/95 px-2 py-1.5 text-[11.5px] shadow-lg backdrop-blur" style={{ left: Math.min(tip.x + 10, (el.current?.clientWidth || 300) - 290), top: Math.min(tip.y + 12, (el.current?.clientHeight || 200) - 80) }} data-pc-ui>
          <b className="block">{tip.mk.title}</b>
          {tip.mk.sub && <span className="block text-muted">{tip.mk.sub}</span>}
          <span className="block text-faint">{tip.mk.when}</span>
        </div>
      )}
      {edit && (
        <form className="absolute left-1/2 top-12 z-30 flex -translate-x-1/2 items-center gap-1.5 rounded-md border border-line2 bg-panel/95 p-1.5 shadow-lg backdrop-blur" data-pc-ui
          onSubmit={(ev) => { ev.preventDefault(); commitEdit(true); }}>
          <input autoFocus className="field !h-8 w-56" aria-label="Nội dung" value={edit.text} maxLength={120} onChange={(ev) => setEdit({ ...edit, text: ev.target.value })} onKeyDown={(ev) => { if (ev.key === "Escape") { ev.stopPropagation(); commitEdit(false); } }} />
          <button type="submit" className="btn !h-8">Lưu</button>
          <button type="button" className="btn !h-8" onClick={() => commitEdit(false)}>Huỷ</button>
        </form>
      )}
      {sel && !edit && (
        <div className="absolute z-20 top-2 left-1/2 -translate-x-1/2 flex items-center gap-1 rounded-md border border-line2 bg-panel/95 px-1.5 py-1 shadow-lg backdrop-blur" role="toolbar" aria-label="Kiểu hình vẽ" data-pc-ui>
          {DRAW_COLORS.map((col) => (
            <button key={col} type="button" aria-label={`Màu ${col}`} aria-pressed={sel.style?.color === col} disabled={sel.locked}
              className={cn("h-[18px] w-[18px] rounded-full border-2 cursor-pointer p-0", sel.style?.color === col ? "border-fg" : "border-transparent")}
              style={{ background: col }} onClick={() => S.current.engine?.patchSelected({ color: col })} />
          ))}
          <span className="mx-1 h-4 w-px bg-line2" />
          {[1, 2, 3].map((w) => (
            <button key={w} type="button" aria-label={`Độ dày ${w}`} aria-pressed={Math.round(sel.style?.width || 1.5) === w} disabled={sel.locked}
              className={cn("grid h-6 w-6 place-items-center rounded border-0 bg-transparent cursor-pointer text-fg", Math.round(sel.style?.width || 1.5) === w && "bg-panel2")}
              onClick={() => S.current.engine?.patchSelected({ width: w })}><span className="block w-4 bg-current" style={{ height: w }} /></button>
          ))}
          <button type="button" className={cn("h-6 rounded border-0 bg-transparent px-1.5 text-[11px] cursor-pointer text-fg", sel.style?.dash && "bg-panel2")} disabled={sel.locked}
            aria-pressed={!!sel.style?.dash} onClick={() => S.current.engine?.patchSelected({ dash: !sel.style?.dash })}>- - -</button>
          <span className="mx-1 h-4 w-px bg-line2" />
          <button type="button" aria-label={sel.locked ? "Mở khoá hình vẽ" : "Khoá hình vẽ"} title={sel.locked ? "Mở khoá" : "Khoá"} aria-pressed={!!sel.locked}
            className={cn("grid h-6 w-6 place-items-center rounded border-0 bg-transparent cursor-pointer text-fg", sel.locked && "bg-panel2 text-accent")} onClick={() => S.current.engine?.patch(sel.id, { locked: !sel.locked })}>{sel.locked ? <Lock size={13} /> : <LockOpen size={13} />}</button>
          <button type="button" aria-label="Nhân bản hình vẽ" title="Nhân bản (Ctrl+D)" className="grid h-6 w-6 place-items-center rounded border-0 bg-transparent cursor-pointer text-fg" onClick={() => S.current.engine?.duplicateSelected()}><Copy size={13} /></button>
          <button type="button" aria-label="Xoá hình vẽ" title="Xoá (Del)" className="grid h-6 w-6 place-items-center rounded border-0 bg-transparent cursor-pointer text-down" disabled={sel.locked} onClick={() => S.current.engine?.removeSelected()}><X size={14} /></button>
        </div>
      )}
    </div>
  );
}

/** Ảnh chụp: biểu đồ + dải tiêu đề (mã, khung, thời điểm chụp) để dán/ chia sẻ. */
function snapshot(chart, title) {
  const cv = chart?.takeScreenshot();
  if (!cv) return null;
  const H = 26, out = document.createElement("canvas");
  out.width = cv.width; out.height = cv.height + H;
  const g = out.getContext("2d");
  g.fillStyle = css("--panel") || "#0e141c"; g.fillRect(0, 0, out.width, out.height);
  g.font = "600 13px 'Inter Variable', system-ui, sans-serif"; g.textBaseline = "middle"; g.fillStyle = css("--fg") || "#d6dfeb";
  g.fillText(title, 10, H / 2);
  g.font = "11px 'Inter Variable', system-ui, sans-serif"; g.fillStyle = css("--muted") || "#8191a5"; g.textAlign = "right";
  g.fillText(new Date().toLocaleString("vi-VN", { timeZone: TZ }), out.width - 10, H / 2);
  g.drawImage(cv, 0, H);
  return out;
}

/** Legend: OHLC + giá trị chỉ báo tại nến dưới con trỏ (hoặc nến cuối). Tự giữ state để mousemove không render lại cả chart. */
function Legend({ bus, bars, symbol, tf, decimals, inds, paneTops, onAction, compare, typeLabel }) {
  const [hover, setHover] = useState(null);
  useEffect(() => { bus.current = setHover; return () => { bus.current = null; }; }, [bus]);
  const n = bars.length;
  const i = hover == null ? n - 1 : Math.max(0, Math.min(n - 1, hover));
  const b = bars[i], pb = bars[i - 1] || null;
  const chg = b && pb ? ((b.c - pb.c) / pb.c) * 100 : null;
  const tone = b && b.c >= b.o ? "up" : "down";
  const f = (v) => (v == null ? "—" : Number(v).toLocaleString("en-US", { minimumFractionDigits: decimals, maximumFractionDigits: decimals }));
  const overlays = inds.filter((x) => IND[x.inst.type]?.group === "overlay");
  const panes = inds.filter((x) => (IND[x.inst.type]?.group === "pane" || x.corr) && !x.hidden);
  return (
    <>
      <div className="pointer-events-none absolute left-2 top-1.5 z-10 flex max-w-[calc(100%-5rem)] flex-col gap-[2px] text-[11.5px] leading-tight">
        <div className="flex flex-wrap items-center gap-x-2.5 gap-y-0.5 rounded bg-panel/70 px-1.5 py-[2px] backdrop-blur-[2px]">
          <b className="text-[12.5px]">{String(symbol).replace(/^(VN|US):/, "")}</b>
          <span className="text-faint">{tf}</span>
          {typeLabel ? <span className="text-faint" title="Kích thước gạch/hộp">▫ {Number(typeLabel).toPrecision(3)}</span> : null}
          {b && <>
            <span className="num"><span className="text-faint">O</span> <span className={tone}>{f(b.o)}</span></span>
            <span className="num"><span className="text-faint">H</span> <span className={tone}>{f(b.h)}</span></span>
            <span className="num"><span className="text-faint">L</span> <span className={tone}>{f(b.l)}</span></span>
            <span className="num"><span className="text-faint">C</span> <span className={tone}>{f(b.c)}</span></span>
            {chg != null && <span className={cn("num", chg >= 0 ? "up" : "down")}>{chg >= 0 ? "+" : ""}{chg.toFixed(2)}%</span>}
          </>}
          {compare?.symbol && (compare.mode || "pct") === "pct" && <span className="text-info">vs {compare.symbol.replace(/^(VN|US):/, "")} (%)</span>}
        </div>
        {overlays.map((x) => <LegendRow key={x.inst.id} x={x} i={i} dec={decimals} onAction={onAction} />)}
      </div>
      {panes.map((x) => (
        <div key={x.inst.id} className="pointer-events-none absolute left-2 z-10 text-[11.5px]" style={{ top: (paneTops[x.pane] ?? 0) + 4 }}>
          {x.corr ? <div className="rounded bg-panel/70 px-1.5 py-[1px]"><span className="font-medium">Tương quan <span className="text-faint">50</span></span> <span className="num text-info">{x.values.v[i] == null ? "—" : x.values.v[i].toFixed(2)}</span></div>
            : <LegendRow x={x} i={i} dec={decimals + 1} onAction={onAction} />}
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
        <button type="button" className="legend-btn" aria-label="Ẩn/hiện" onClick={() => onAction?.("toggle", x.inst.id)}>{x.hidden ? <EyeOff size={12} /> : <Eye size={12} />}</button>
        <button type="button" className="legend-btn" aria-label="Cài đặt chỉ báo" onClick={() => onAction?.("edit", x.inst.id)}><Settings2 size={12} /></button>
        <button type="button" className="legend-btn" aria-label="Gỡ chỉ báo" onClick={() => onAction?.("remove", x.inst.id)}><X size={12} /></button>
      </span>
    </div>
  );
}
