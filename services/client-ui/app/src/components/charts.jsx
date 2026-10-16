import { useEffect, useRef } from "react";
import { cn } from "./ui";
import * as echarts from "echarts/core";
import { LineChart, BarChart, PieChart, GaugeChart, HeatmapChart } from "echarts/charts";
import { GridComponent, TooltipComponent, DataZoomComponent, MarkLineComponent, VisualMapComponent, CalendarComponent } from "echarts/components";
import { CanvasRenderer } from "echarts/renderers";

echarts.use([LineChart, BarChart, PieChart, GaugeChart, HeatmapChart, GridComponent, TooltipComponent, DataZoomComponent, MarkLineComponent, VisualMapComponent, CalendarComponent, CanvasRenderer]);

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
