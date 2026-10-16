import { Network } from "lucide-react";
import { useWidget } from "../terminal/ui";
import { CorrelationView } from "../components/intel/CorrelationView";

export const meta = {
  id: "correlation-matrix", title: "Ma trận tương quan", icon: Network, group: "Thị trường",
  desc: "Tương quan lợi suất ngày giữa các mã (thang −1…+1). Thống kê tham khảo.",
  defaultSize: { w: 10, h: 14 }, minSize: { w: 6, h: 8 },
  configSchema: [
    { key: "window", label: "Cửa sổ (phiên)", type: "select", default: "60", options: ["20", "60", "120", "250"] },
    { key: "method", label: "Phương pháp", type: "select", default: "pearson", options: [{ value: "pearson", label: "Pearson" }, { value: "spearman", label: "Spearman" }] },
    { key: "symbols", label: "Mã (trống = rổ đa tài sản)", type: "symbols", default: [] },
  ],
};

export default function CorrelationWidget() {
  const { config, size } = useWidget();
  const h = Math.max(200, (size?.h || 360) - 70);
  return (
    <div className="tm-fill"><div className="tm-scroll">
      <CorrelationView compact symbols={config.symbols} window={Number(config.window) || 60} method={config.method || "pearson"} height={h} />
    </div></div>
  );
}
