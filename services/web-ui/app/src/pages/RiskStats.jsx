import { useState } from "react";
import { Network, Activity, Gauge } from "lucide-react";
import { Disclaimer, PageHead, Panel } from "../components/ui";
import { CorrelationView } from "../components/intel/CorrelationView";
import { VolatilityRankView } from "../components/intel/VolatilityRank";
import { ReturnDistributionView } from "../components/intel/ReturnDistribution";

export const meta = { path: "tuong-quan-rui-ro", label: "Tương quan & rủi ro", group: "Thị trường", icon: Network, order: 70, keywords: "correlation beta atr volatility distribution var tương quan rủi ro phân phối" };

export default function RiskStats() {
  const [sym, setSym] = useState("US:SPY");
  return (
    <>
      <PageHead title="Tương quan & rủi ro" sub="Ma trận tương quan, xếp hạng biến động (ATR, beta) và phân phối lợi suất, tính trên nến ngày." />
      <div><Disclaimer><b>Thống kê lịch sử, tham khảo, không phải khuyến nghị đầu tư.</b> Tương quan và biến động thay đổi theo thời gian; dữ liệu quá khứ không đảm bảo kết quả tương lai.</Disclaimer></div>
      <Panel title="Ma trận tương quan" icon={Network}><CorrelationView /></Panel>
      <div className="grid gap-3 xl:grid-cols-2 items-start">
        <Panel title="Xếp hạng biến động & beta" icon={Activity}><VolatilityRankView onSelect={setSym} selected={sym} /></Panel>
        <Panel title="Phân phối lợi suất" icon={Gauge}><ReturnDistributionView symbol={sym} onSymbol={setSym} /></Panel>
      </div>
    </>
  );
}
