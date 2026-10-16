import { Grid2x2 } from "lucide-react";
import { FxHeatmapView } from "../components/intel/FxHeatmap";

export const meta = {
  id: "fx-heatmap", title: "Bản đồ nhiệt Forex", icon: Grid2x2, group: "Thị trường", desc: "28 cặp x 5 kỳ, sắp xếp theo cột (thống kê tham khảo).",
  defaultSize: { w: 10, h: 14 }, minSize: { w: 6, h: 8 },
};

export default function FxHeatmapWidget() {
  return <div className="tm-fill"><FxHeatmapView compact /></div>;
}
