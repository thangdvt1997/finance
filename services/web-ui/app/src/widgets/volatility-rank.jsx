import { Activity } from "lucide-react";
import { useWidget } from "../terminal/ui";
import { VolatilityRankView } from "../components/intel/VolatilityRank";

export const meta = {
  id: "volatility-rank", title: "Xếp hạng biến động", icon: Activity, group: "Thị trường",
  desc: "ATR%, độ biến động thực hiện, khoảng cách SMA và beta theo mã. Thống kê tham khảo.",
  defaultSize: { w: 10, h: 14 }, minSize: { w: 6, h: 8 },
  configSchema: [
    { key: "group", label: "Nhóm tài sản", type: "select", default: "all", options: [{ value: "all", label: "Tất cả" }, { value: "crypto", label: "Tiền ảo" }, { value: "etf", label: "Chỉ số & ETF toàn cầu" }, { value: "sector", label: "Ngành Mỹ (ETF)" }, { value: "commodity", label: "Kim loại & hàng hoá" }, { value: "forex", label: "Forex" }, { value: "us_stock", label: "Cổ phiếu Mỹ" }, { value: "bond", label: "Trái phiếu" }, { value: "vn", label: "Cổ phiếu VN" }] },
    { key: "benchmark", label: "Chỉ số tham chiếu (beta)", type: "select", default: "US:SPY", options: [{ value: "US:SPY", label: "SPY" }, { value: "US:QQQ", label: "QQQ" }, { value: "CRYPTO:BTCUSDT", label: "BTC" }, { value: "EURUSD", label: "EURUSD" }, { value: "XAUUSD", label: "Vàng" }] },
  ],
};

export default function VolatilityWidget() {
  const { config, size } = useWidget();
  const h = Math.max(160, (size?.h || 360) - 110);
  return (
    <div className="tm-fill"><div className="tm-scroll">
      <VolatilityRankView compact group={config.group || "all"} benchmark={config.benchmark || "US:SPY"} height={h} />
    </div></div>
  );
}
