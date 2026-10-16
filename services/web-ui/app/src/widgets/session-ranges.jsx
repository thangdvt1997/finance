import { Activity } from "lucide-react";
import { useWidget } from "../terminal/ui";
import { SessionRangesView } from "../components/intel/SessionRanges";

export const meta = {
  id: "session-ranges", title: "Biên độ theo phiên", icon: Activity, group: "Thị trường", linkable: true, desc: "Biên độ trung bình theo giờ UTC và theo phiên Tokyo/London/New York (tham khảo).",
  defaultSize: { w: 10, h: 14 }, minSize: { w: 6, h: 8 },
};

export default function SessionRangesWidget() {
  const { symbol } = useWidget();
  return <div className="tm-fill tm-scroll"><SessionRangesView symbol={symbol || "EURUSD"} compact /></div>;
}
