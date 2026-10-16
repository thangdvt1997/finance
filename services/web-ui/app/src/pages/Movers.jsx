import { TrendingUp } from "lucide-react";
import { Disclaimer, PageHead, Panel } from "../components/ui";
import { MoversView } from "../components/intel/MoversView";

export const meta = { path: "movers", label: "Movers & biến động", group: "Thị trường", icon: TrendingUp, order: 68, keywords: "top gainers losers volume 52 week high low gap biến động tăng giảm mạnh" };

export default function Movers() {
  return (
    <div className="grid gap-3">
      <PageHead title="Movers & biến động" sub="Mã tăng/giảm mạnh, biến động bất thường, khối lượng đột biến, gần đỉnh/đáy 52 tuần và gap." />
      <Panel title="Bảng biến động" icon={TrendingUp}>
        <MoversView rows={20} pollMs={120_000} />
      </Panel>
      <Disclaimer>Số liệu thống kê từ nến đã lưu (52 tuần = 252 phiên gần nhất; Z-score so với độ lệch chuẩn 20 phiên). Chỉ mang tính tham khảo, không phải khuyến nghị đầu tư.</Disclaimer>
    </div>
  );
}
