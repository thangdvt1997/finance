import { useEffect, useState } from "react";
import { LayoutGrid } from "lucide-react";
import { Disclaimer, PageHead, Panel } from "../components/ui";
import { HeatmapView } from "../components/intel/HeatmapView";

export const meta = { path: "ban-do-nhiet", label: "Bản đồ nhiệt", group: "Thị trường", icon: LayoutGrid, order: 66, keywords: "heatmap treemap crypto etf sector ngành hàng hoá bản đồ nhiệt" };

const calc = () => Math.max(360, (typeof window === "undefined" ? 800 : window.innerHeight) - 300);

export default function Heatmaps() {
  const [h, setH] = useState(calc);
  useEffect(() => {
    const f = () => setH(calc());
    window.addEventListener("resize", f);
    return () => window.removeEventListener("resize", f);
  }, []);
  return (
    <div className="grid gap-3">
      <PageHead title="Bản đồ nhiệt" sub="Toàn cảnh thị trường theo nhóm tài sản: màu thể hiện % thay đổi, diện tích thể hiện giá trị giao dịch." />
      <Panel title="Bản đồ nhiệt thị trường" icon={LayoutGrid}>
        <HeatmapView height={h} />
      </Panel>
      <Disclaimer>Số liệu thống kê từ dữ liệu giá đã lưu, chỉ mang tính tham khảo, không phải khuyến nghị đầu tư. Kích thước ô là giá trị giao dịch trung bình 20 phiên, không phải vốn hoá.</Disclaimer>
    </div>
  );
}
