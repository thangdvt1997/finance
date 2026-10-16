import { Clock } from "lucide-react";
import { MarketHoursView } from "../components/intel/MarketHours";

export const meta = {
  id: "market-hours", title: "Giờ mở cửa các sàn", icon: Clock, group: "Thị trường", desc: "Mở/đóng, đếm ngược và timeline 24 giờ các sàn (tham khảo).",
  defaultSize: { w: 10, h: 14 }, minSize: { w: 6, h: 8 },
};

export default function MarketHoursWidget() {
  return <div className="tm-fill tm-scroll"><MarketHoursView compact /></div>;
}
