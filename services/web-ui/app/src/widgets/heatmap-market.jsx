import { LayoutGrid } from "lucide-react";
import { useWidget } from "../terminal/ui";
import { HeatmapView } from "../components/intel/HeatmapView";

export const meta = {
  id: "heatmap-market", title: "Bản đồ nhiệt thị trường", icon: LayoutGrid, group: "Thị trường",
  desc: "Treemap theo nhóm tài sản: màu = % thay đổi, diện tích = giá trị giao dịch TB 20 phiên.",
  defaultSize: { w: 12, h: 14 }, minSize: { w: 6, h: 8 },
  configSchema: [
    { key: "group", label: "Nhóm tài sản", type: "select", default: "crypto", options: [{ value: "crypto", label: "Tiền ảo" }, { value: "etf", label: "Chỉ số & ETF toàn cầu" }, { value: "sector", label: "Ngành Mỹ (ETF)" }, { value: "commodity", label: "Kim loại & hàng hoá" }, { value: "forex", label: "Forex" }, { value: "us_stock", label: "Cổ phiếu Mỹ" }, { value: "bond", label: "Trái phiếu" }, { value: "vn", label: "Ngành VN" }] },
    { key: "period", label: "Kỳ", type: "select", default: "1d", options: [{ value: "1d", label: "1 ngày" }, { value: "1w", label: "1 tuần" }, { value: "1m", label: "1 tháng" }, { value: "3m", label: "3 tháng" }, { value: "ytd", label: "Từ đầu năm" }, { value: "1y", label: "1 năm" }] },
  ],
};

export default function HeatmapMarketWidget() {
  const { config, size } = useWidget();
  const h = Math.max(160, (size?.h || 420) - 110);
  return (
    <div className="tm-fill">
      <div className="tm-scroll tm-pad">
        <HeatmapView compact group={config.group || "crypto"} period={config.period || "1d"} height={h} />
      </div>
    </div>
  );
}
