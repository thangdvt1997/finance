import { useEffect, useRef } from "react";
import { cn } from "./ui";
import * as echarts from "echarts/core";
import { LineChart, HeatmapChart, BarChart, ScatterChart } from "echarts/charts";
import { GridComponent, TooltipComponent, VisualMapComponent, DataZoomComponent, MarkLineComponent } from "echarts/components";
import { CanvasRenderer } from "echarts/renderers";
import { createChart, CandlestickSeries, HistogramSeries, LineSeries, CrosshairMode, LineStyle } from "lightweight-charts";

echarts.use([LineChart, HeatmapChart, BarChart, ScatterChart, GridComponent, TooltipComponent, VisualMapComponent, DataZoomComponent, MarkLineComponent, CanvasRenderer]);

export const css = (name) => getComputedStyle(document.documentElement).getPropertyValue(name).trim();

function onTheme(fn) {
  const mo = new MutationObserver(fn);
  mo.observe(document.documentElement, { attributes: true, attributeFilter: ["data-theme"] });
  return () => mo.disconnect();
}

/** ECharts: truyền `build()` trả về option (đọc màu từ CSS vars); vẽ lại khi đổi theme/kích thước. */
export function EChart({ build, deps, height = 220, label, className }) {
  const el = useRef(null);
  const inst = useRef(null);
  const buildRef = useRef(build);
  buildRef.current = build;
  useEffect(() => {
    const c = echarts.init(el.current, null, { renderer: "canvas" });
    inst.current = c;
    const ro = new ResizeObserver(() => c.resize());
    ro.observe(el.current);
    const off = onTheme(() => c.setOption(buildRef.current(), true));
    return () => { ro.disconnect(); off(); c.dispose(); };
  }, []);
  useEffect(() => {
    inst.current?.setOption(buildRef.current(), true);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);
  // Khung co giãn: lấp đầy chiều cao còn lại nếu cha là flex-col, tối thiểu `height` px.
  return (
    <div className={cn("relative w-full flex-1", className)} style={{ minHeight: height }}>
      <div ref={el} className="absolute inset-0" role="img" aria-label={label} />
    </div>
  );
}

/** Biểu đồ nến TradingView Lightweight Charts (Apache-2.0). */
/** overlays: [{ id, color, width?, dashed?, data: [{time(giây), value}] }] — đường chỉ báo vẽ chồng lên nến. */
export function CandleChart({ bars, symbol, tf, onReady, height = 420, decimals = 5, overlays, className }) {
  const el = useRef(null);
  const api = useRef({});
  const lines = useRef([]);
  useEffect(() => {
    const chart = createChart(el.current, {
      autoSize: true,
      layout: { background: { color: "transparent" }, textColor: css("--muted"), fontFamily: "Inter Variable, system-ui, sans-serif", fontSize: 11 },
      grid: { vertLines: { color: css("--line") }, horzLines: { color: css("--line") } },
      crosshair: { mode: CrosshairMode.Normal },
      rightPriceScale: { borderColor: css("--line2") },
      timeScale: { borderColor: css("--line2"), timeVisible: true, secondsVisible: false },
      localization: { locale: "vi-VN" },
    });
    const candles = chart.addSeries(CandlestickSeries, {
      upColor: css("--up"), downColor: css("--down"), wickUpColor: css("--up"), wickDownColor: css("--down"), borderVisible: false,
    });
    const vol = chart.addSeries(HistogramSeries, { priceFormat: { type: "volume" }, priceScaleId: "vol", color: css("--line2") });
    chart.priceScale("vol").applyOptions({ scaleMargins: { top: 0.82, bottom: 0 } });
    api.current = { chart, candles, vol };
    const apply = () => {
      chart.applyOptions({
        layout: { textColor: css("--muted") },
        grid: { vertLines: { color: css("--line") }, horzLines: { color: css("--line") } },
        rightPriceScale: { borderColor: css("--line2") }, timeScale: { borderColor: css("--line2") },
      });
      candles.applyOptions({ upColor: css("--up"), downColor: css("--down"), wickUpColor: css("--up"), wickDownColor: css("--down") });
    };
    const off = onTheme(apply);
    onReady?.(api.current);
    return () => { off(); chart.remove(); };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
  useEffect(() => {
    const { candles, vol, chart } = api.current;
    if (!candles) return;
    candles.applyOptions({ priceFormat: { type: "price", precision: decimals, minMove: 1 / 10 ** decimals } });
    const data = (bars || []).map((b) => ({ time: Math.floor(new Date(b.ts_open).getTime() / 1000), open: b.o, high: b.h, low: b.l, close: b.c }));
    candles.setData(data);
    vol.setData((bars || []).map((b) => ({
      time: Math.floor(new Date(b.ts_open).getTime() / 1000), value: b.v || 0,
      color: b.c >= b.o ? "rgba(43,208,143,.28)" : "rgba(255,92,122,.28)",
    })));
    chart.timeScale().fitContent();
    if (data.length > 120) chart.timeScale().setVisibleLogicalRange({ from: data.length - 110, to: data.length + 6 });
  }, [bars, symbol, tf, decimals]);
  useEffect(() => {
    const { chart } = api.current;
    if (!chart) return;
    for (const l of lines.current) chart.removeSeries(l);
    lines.current = (overlays || []).map((o) => {
      const s = chart.addSeries(LineSeries, {
        color: o.color, lineWidth: o.width || 1, lineStyle: o.dashed ? LineStyle.Dashed : LineStyle.Solid,
        priceLineVisible: false, lastValueVisible: false, crosshairMarkerVisible: false, title: "",
      });
      s.setData(o.data);
      return s;
    });
  }, [overlays, symbol, tf]);
  return (
    <div className={cn("relative w-full flex-1", className)} style={{ minHeight: height }}>
      <div ref={el} className="absolute inset-0" role="group" aria-label={`Biểu đồ nến ${symbol} khung ${tf}`} />
    </div>
  );
}
