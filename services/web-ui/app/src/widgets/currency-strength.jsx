import { Scale } from "lucide-react";
import { useWidget } from "../terminal/ui";
import { StrengthView } from "../components/intel/StrengthMeter";

export const meta = {
  id: "currency-strength", title: "Sức mạnh tiền tệ", icon: Scale, group: "Thị trường", desc: "Xếp hạng 8 tiền tệ chính và lịch sử điểm (thống kê tham khảo).",
  defaultSize: { w: 9, h: 14 }, minSize: { w: 5, h: 8 },
  configSchema: [{ key: "tf", label: "Khung thời gian", type: "select", default: "D1", options: ["H1", "H4", "D1"] }],
};

export default function CurrencyStrengthWidget() {
  const { config } = useWidget();
  const tf = config.tf || "D1";
  return <div className="tm-fill tm-scroll"><StrengthView key={tf} tf={tf} compact /></div>;
}
