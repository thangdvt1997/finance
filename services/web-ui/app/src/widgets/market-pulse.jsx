import { HeartPulse } from "lucide-react";
import { useWidget } from "../terminal/ui";
import { PulseView } from "../components/intel/PulseView";

export const meta = {
  id: "market-pulse", title: "Nhịp thị trường", icon: HeartPulse, group: "Thị trường",
  desc: "Khẩu vị rủi ro, chỉ số biến động, độ rộng thị trường theo lớp tài sản, tâm lý tin tức 24h.",
  defaultSize: { w: 9, h: 16 }, minSize: { w: 5, h: 8 },
  configSchema: [
    { key: "view", label: "Hiển thị", type: "select", default: "all", options: [{ value: "all", label: "Tổng hợp" }, { value: "appetite", label: "Chỉ khẩu vị rủi ro" }, { value: "breadth", label: "Chỉ độ rộng" }] },
  ],
};

export default function MarketPulseWidget() {
  const { config } = useWidget();
  return (
    <div className="tm-fill">
      <div className="tm-scroll tm-pad">
        <PulseView compact part={config.view || "all"} />
      </div>
    </div>
  );
}
