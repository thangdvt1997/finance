import { Gauge } from "lucide-react";
import { useWidget } from "../terminal/ui";
import { ReturnDistributionView } from "../components/intel/ReturnDistribution";

export const meta = {
  id: "return-distribution", title: "Phân phối lợi suất", icon: Gauge, group: "Thị trường", linkable: true,
  desc: "Histogram lợi suất ngày, VaR/ES lịch sử của mã đang chọn. Không dự báo.",
  defaultSize: { w: 9, h: 13 }, minSize: { w: 5, h: 8 },
  configSchema: [
    { key: "window", label: "Cửa sổ (phiên)", type: "select", default: "250", options: ["60", "120", "250", "500", "1000"] },
  ],
};

export default function DistributionWidget() {
  const { config, symbol, size } = useWidget();
  const h = Math.max(150, (size?.h || 340) - 150);
  return (
    <div className="tm-fill"><div className="tm-scroll">
      <ReturnDistributionView compact symbol={symbol || "US:SPY"} window={Number(config.window) || 250} height={h} />
    </div></div>
  );
}
