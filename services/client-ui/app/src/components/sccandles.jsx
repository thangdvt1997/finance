// Biểu đồ nến gọn cho trang "Kịch bản": nến + đường giá Entry/SL/TP + điểm đánh dấu sự kiện. Lightweight Charts v5 (Apache-2.0, đã có trong dự án).
// Màu đọc từ token CSS -> đổi sáng/tối tự vẽ lại. Giờ trục theo múi giờ trong cài đặt.
import { useEffect, useRef } from "react";
import { createChart, CandlestickSeries, LineStyle, createSeriesMarkers } from "lightweight-charts";
import { date, dateTime, decimals, symbolLabel, time } from "../lib/format";
import { t } from "../lib/i18n";

const css = (n) => getComputedStyle(document.documentElement).getPropertyValue(n).trim();
const sec = (v) => Math.floor((typeof v === "number" ? (v > 1e12 ? v : v * 1000) : Date.parse(v)) / 1000);

/** bars: [{ts_open|t, o,h,l,c}] (thứ tự bất kỳ); levels: {entry, sl, tp_1r..}; marks: [{t, label, tone?}] */
export default function ScCandles({ bars, symbol, levels, marks, height = 320 }) {
  const el = useRef(null);
  useEffect(() => {
    if (!el.current || !bars?.length) return undefined;
    const dp = decimals(symbolLabel(symbol));
    const seen = new Set();
    const data = bars.map((b) => ({ time: sec(b.ts_open ?? b.t), open: +b.o, high: +b.h, low: +b.l, close: +b.c }))
      .filter((b) => Number.isFinite(b.time) && Number.isFinite(b.close) && !seen.has(b.time) && seen.add(b.time))
      .sort((a, b) => a.time - b.time);
    if (!data.length) return undefined;
    let chart, series, mk;
    const draw = () => {
      chart?.remove();
      chart = createChart(el.current, {
        autoSize: true,
        layout: { background: { color: "transparent" }, textColor: css("--muted"), fontSize: 11, attributionLogo: false },
        grid: { vertLines: { color: css("--line") }, horzLines: { color: css("--line") } },
        rightPriceScale: { borderColor: css("--line2") },
        timeScale: { borderColor: css("--line2"), rightOffset: 6, timeVisible: true, secondsVisible: false, tickMarkFormatter: (tm, kind) => (kind <= 2 ? date(tm * 1000) : time(tm * 1000)) },
        localization: { timeFormatter: (tm) => dateTime(tm * 1000), priceFormatter: (p) => p.toFixed(dp) },
        handleScroll: { vertTouchDrag: false }, crosshair: { mode: 0 },
      });
      const up = css("--up"), down = css("--down");
      const L = levels || {};
      const lv = [L.entry, L.sl, L.tp_1r, L.tp_2r, L.tp_3r].map(Number).filter(Number.isFinite);
      // mức gợi ý luôn nằm trong khung nhìn (price line mặc định không tham gia autoscale)
      const autoscaleInfoProvider = (orig) => { const r = orig(); if (!r || !lv.length) return r; return { ...r, priceRange: { minValue: Math.min(r.priceRange.minValue, ...lv), maxValue: Math.max(r.priceRange.maxValue, ...lv) } }; };
      series = chart.addSeries(CandlestickSeries, { autoscaleInfoProvider, upColor: up, downColor: down, borderUpColor: up, borderDownColor: down, wickUpColor: up, wickDownColor: down, priceFormat: { type: "price", precision: dp, minMove: 1 / 10 ** dp } });
      series.setData(data);
      const pl = (price, color, title, style = LineStyle.Dashed) => Number.isFinite(+price) && series.createPriceLine({ price: +price, color, lineWidth: 1, lineStyle: style, axisLabelVisible: true, title });
      pl(L.entry, css("--accent"), t("Entry"), LineStyle.Solid);
      pl(L.sl, down, "SL");
      pl(L.tp_1r, up, "TP1"); pl(L.tp_2r, up, "TP2"); pl(L.tp_3r, up, "TP3");
      const first = data[0].time, last = data[data.length - 1].time;
      // pivot có giá -> chấm tại giá kèm nhãn "(1)".."(n)"; trigger/sự kiện -> mũi tên trên nến
      const ms = (marks || []).map((m) => (m.kind === "pivot" && Number.isFinite(+m.p)
        ? { time: sec(m.t), position: "atPriceMiddle", price: +m.p, shape: "circle", size: 0.6, color: css("--muted"), text: m.label }
        : { time: sec(m.t), position: "aboveBar", shape: "arrowDown", color: m.tone === "down" ? down : css("--info"), text: m.label }))
        .filter((m) => Number.isFinite(m.time) && m.time >= first && m.time <= last)
        .map((m) => ({ ...m, time: data.reduce((a, b) => (b.time <= m.time ? b.time : a), first) }))
        .sort((a, b) => a.time - b.time);
      mk = createSeriesMarkers(series, ms);
      chart.timeScale().fitContent();
    };
    draw();
    const mo = new MutationObserver(draw);
    mo.observe(document.documentElement, { attributes: true, attributeFilter: ["data-theme"] });
    return () => { mo.disconnect(); mk = null; chart?.remove(); };
  }, [bars, symbol, levels, marks]);
  return (
    <div className="sc-chart" style={{ height }}>
      <div ref={el} className="absolute inset-0" role="img" aria-label={t("Biểu đồ nến {sym} kèm mức Entry, SL, TP gợi ý", { sym: symbolLabel(symbol) })} />
    </div>
  );
}
