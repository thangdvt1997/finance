import { ArrowLeftRight } from "lucide-react";
import { CrossRatesView } from "../components/intel/CrossRates";

export const meta = {
  id: "cross-rates", title: "Tỷ giá chéo", icon: ArrowLeftRight, group: "Thị trường", desc: "Ma trận 8x8 tỷ giá chéo và máy tính quy đổi (tham khảo).",
  defaultSize: { w: 12, h: 13 }, minSize: { w: 7, h: 8 },
};

export default function CrossRatesWidget() {
  return <div className="tm-fill tm-scroll"><CrossRatesView compact /></div>;
}
