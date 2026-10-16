import * as echarts from "echarts/core";
import { TreemapChart } from "echarts/charts";
import { EChart, css } from "../charts";
import { bil, pc, vnd } from "../../lib/vn";

echarts.use([TreemapChart]);

const hex = (h) => { const s = h.replace("#", ""); const v = s.length === 3 ? s.replace(/./g, "$&$&") : s; return [0, 2, 4].map((i) => parseInt(v.slice(i, i + 2), 16)); };
const mixv = (a, b, t) => a.map((x, i) => Math.round(x + (b[i] - x) * t));
const lum = ([r, g, b]) => (0.2126 * r + 0.7152 * g + 0.0722 * b) / 255;

/** Màu ô theo %: xám trung tính -> xanh (tăng) / đỏ (giảm); bão hoà đủ ở +-5%. Số % luôn in trong ô nên không chỉ dựa vào màu. */
export function cellColor(p, neutral, up, down) {
  const t = Math.min(Math.abs(p) / 5, 1);
  return mixv(neutral, p >= 0 ? up : down, 0.18 + 0.82 * t);
}

/** Treemap ECharts: ngành -> mã; diện tích = vốn hoá (hoặc GTGD). Viền tím = trần, xanh lơ = sàn. */
export default function Heatmap({ data, height = 520 }) {
  const build = () => {
    const neutral = hex(css("--panel2") || "#131b26"), up = hex(css("--up") || "#2bd08f"), down = hex(css("--down") || "#ff5c7a");
    const bg = css("--bg"), fg = css("--fg"), line = css("--line2");
    const ceil = css("--vn-ceil"), flr = css("--vn-floor");
    const sizeLabel = data.size_by === "value" ? "GTGD" : "Vốn hoá";
    const nodes = (data.sectors || []).map((s) => ({
      name: s.name, value: s.value, pct: s.pct, isSector: true,
      children: s.children.map((c) => { const rgb = cellColor(c.pct, neutral, up, down); return {
        name: c.name, value: c.value, pct: c.pct, close: c.close, marketcap: c.marketcap, tvalue: c.tvalue, limit: c.limit,
        label: { color: lum(rgb) > 0.5 ? "#0b1018" : "#fff" },
        itemStyle: { color: `rgb(${rgb.join(",")})`, borderColor: c.limit === "ceiling" ? ceil : c.limit === "floor" ? flr : bg, borderWidth: c.limit ? 2.5 : 1 },
      }; }),
    }));
    return {
      animation: false,
      tooltip: {
        confine: true, backgroundColor: css("--panel"), borderColor: line, textStyle: { color: fg, fontSize: 12 },
        formatter: (p) => {
          const d = p.data;
          if (d.isSector) return `<b>${d.name}</b><br/>${sizeLabel}: ${bil(d.value)}<br/>Biến động bình quân gia quyền: ${pc(d.pct)}`;
          return `<b>${d.name}</b> ${d.limit === "ceiling" ? "· TRẦN" : d.limit === "floor" ? "· SÀN" : ""}<br/>Giá đóng: ${vnd(d.close)}đ · ${pc(d.pct)}<br/>Vốn hoá: ${bil(d.marketcap)}<br/>GTGD: ${bil(d.tvalue)}`;
        },
      },
      series: [{
        type: "treemap", data: nodes, roam: false, nodeClick: false, breadcrumb: { show: false }, left: 0, right: 0, top: 0, bottom: 0, squareRatio: 1.1,
        label: { show: true, color: "#fff", fontWeight: 600, fontSize: 12, overflow: "truncate", formatter: (p) => (p.data.isSector ? "" : `${p.name}\n${pc(p.data.pct, 1)}`), lineHeight: 15 },
        upperLabel: { show: true, height: 20, color: fg, fontSize: 11.5, fontWeight: 650, formatter: "{b}" },
        itemStyle: { borderColor: bg, borderWidth: 1, gapWidth: 1 },
        levels: [
          { itemStyle: { borderColor: bg, borderWidth: 3, gapWidth: 3, color: "transparent" }, upperLabel: { show: true, height: 20, color: fg, fontSize: 11.5, fontWeight: 650, position: "insideLeft", padding: [0, 0, 0, 4], formatter: "{b}" } },,
          { itemStyle: { borderColor: bg, borderWidth: 1, gapWidth: 1 }, upperLabel: { show: false } },
        ],
      }],
    };
  };
  return <EChart build={build} deps={[data]} height={height} label="Bản đồ nhiệt ngành chứng khoán Việt Nam" />;
}
