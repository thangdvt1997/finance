import { Scale, Grid2x2, ArrowLeftRight } from "lucide-react";
import { Disclaimer, PageHead, Panel } from "../components/ui";
import { StrengthView } from "../components/intel/StrengthMeter";
import { FxHeatmapView } from "../components/intel/FxHeatmap";
import { CrossRatesView } from "../components/intel/CrossRates";

export const meta = {
  path: "suc-manh-tien-te", label: "Sức mạnh tiền tệ", group: "Thị trường", icon: Scale, order: 62,
  keywords: "forex currency strength heatmap cross rate usd eur jpy sức mạnh tiền tệ tỷ giá chéo", roles: ["master", "client"],
};

export default function CurrencyStrengthPage() {
  return (
    <>
      <PageHead title="Sức mạnh tiền tệ & Forex" sub="Xếp hạng 8 tiền tệ chính, bản đồ nhiệt 28 cặp theo nhiều khung thời gian và ma trận tỷ giá chéo." />
      <div className="grid gap-3 xl:grid-cols-2 items-start">
        <Panel title="Sức mạnh tiền tệ" icon={Scale}><StrengthView /></Panel>
        <Panel title="Bản đồ nhiệt cặp tiền" icon={Grid2x2}><FxHeatmapView /></Panel>
      </div>
      <Panel title="Tỷ giá chéo & quy đổi" icon={ArrowLeftRight}><CrossRatesView /></Panel>
      <Disclaimer>Mọi số liệu là thống kê biến động giá đã lưu, chỉ mang tính tham khảo, không phải khuyến nghị đầu tư. Một số khung thời gian có thể thiếu dữ liệu và được ghi rõ trên từng bảng.</Disclaimer>
    </>
  );
}
