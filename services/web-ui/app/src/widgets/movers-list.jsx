import { TrendingUp } from "lucide-react";
import { useWidget } from "../terminal/ui";
import { MoversView } from "../components/intel/MoversView";

export const meta = {
  id: "movers-list", title: "Movers", icon: TrendingUp, group: "Thị trường",
  desc: "Danh sách mã tăng/giảm mạnh, biến động bất thường, khối lượng, gần đỉnh/đáy 52 tuần, gap.",
  defaultSize: { w: 8, h: 14 }, minSize: { w: 5, h: 7 },
  configSchema: [
    { key: "group", label: "Nhóm tài sản", type: "select", default: "all", options: [{ value: "all", label: "Tất cả nhóm" }, { value: "crypto", label: "Tiền ảo" }, { value: "etf", label: "Chỉ số & ETF toàn cầu" }, { value: "sector", label: "Ngành Mỹ (ETF)" }, { value: "commodity", label: "Kim loại & hàng hoá" }, { value: "forex", label: "Forex" }, { value: "us_stock", label: "Cổ phiếu Mỹ" }, { value: "bond", label: "Trái phiếu" }, { value: "vn", label: "Cổ phiếu VN" }] },
    { key: "period", label: "Kỳ", type: "select", default: "1d", options: [{ value: "1h", label: "1 giờ" }, { value: "4h", label: "4 giờ" }, { value: "1d", label: "1 ngày" }, { value: "1w", label: "1 tuần" }, { value: "1m", label: "1 tháng" }] },
    { key: "kind", label: "Loại", type: "select", default: "gainers", options: [{ value: "gainers", label: "Tăng mạnh" }, { value: "losers", label: "Giảm mạnh" }, { value: "volatile", label: "Biến động bất thường" }, { value: "range", label: "Biên độ trong ngày" }, { value: "volume", label: "Khối lượng đột biến" }, { value: "near_high", label: "Gần đỉnh 52 tuần" }, { value: "near_low", label: "Gần đáy 52 tuần" }, { value: "gaps", label: "Gap mở cửa" }] },
    { key: "rows", label: "Số dòng", type: "number", default: 10, min: 3, max: 30, step: 1 },
  ],
};

export default function MoversListWidget() {
  const { config } = useWidget();
  return (
    <div className="tm-fill">
      <div className="tm-scroll tm-pad">
        <MoversView compact group={config.group || "all"} period={config.period || "1d"} kind={config.kind || "gainers"} rows={config.rows || 10} />
      </div>
    </div>
  );
}
