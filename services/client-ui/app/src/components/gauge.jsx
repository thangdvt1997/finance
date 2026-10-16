import { EChart, css } from "./charts";
import { f0 } from "../lib/format";
import { t } from "../lib/i18n";

/**
 * Đồng hồ mức margin (0-500%+): đỏ < 150, vàng 150-300, xanh >= 300. level = null -> không có vị thế dùng margin.
 * Nhãn mốc nằm NGOÀI cung (distance âm) và kim ngắn hơn bán kính cung, nên nhãn không bao giờ bị kim đè ở mọi giá trị (kể cả 500%).
 */
export default function MarginGauge({ level, height = 190 }) {
  const v = level == null ? 500 : Math.min(level, 500);
  const build = () => ({
    animation: false, backgroundColor: "transparent",
    series: [{
      type: "gauge", min: 0, max: 500, startAngle: 200, endAngle: -20, radius: "74%", center: ["50%", "64%"],
      axisLine: { lineStyle: { width: 14, color: [[0.3, css("--down")], [0.6, css("--accent")], [1, css("--up")]] } },
      pointer: { length: "58%", width: 4, itemStyle: { color: css("--fg") } },
      axisTick: { show: false }, splitLine: { show: false },
      axisLabel: { distance: -36, color: css("--muted"), fontSize: 11, formatter: (x) => (x === 0 || x === 100 || x === 300 || x === 500 ? `${x}%` : "") },
      anchor: { show: true, size: 8, itemStyle: { color: css("--fg") } },
      title: { show: false },
      detail: { valueAnimation: false, offsetCenter: [0, "46%"], fontSize: 22, fontWeight: 700, fontFamily: "JetBrains Mono, monospace", color: css("--fg"), formatter: () => (level == null ? "—" : `${f0(level)}%`) },
      splitNumber: 5, data: [{ value: v }],
    }],
  });
  return <EChart build={build} deps={[level]} height={height} label={level == null ? t("Đồng hồ mức margin: không có vị thế dùng margin") : t("Đồng hồ mức margin: {n} phần trăm", { n: f0(level) })} />;
}
