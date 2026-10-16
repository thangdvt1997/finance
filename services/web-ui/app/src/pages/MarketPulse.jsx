import { HeartPulse } from "lucide-react";
import { Disclaimer, PageHead, Panel } from "../components/ui";
import { PulseView } from "../components/intel/PulseView";

export const meta = { path: "nhip-thi-truong", label: "Nhịp thị trường", group: "Thị trường", icon: HeartPulse, order: 12, keywords: "market pulse breadth vix risk appetite tâm lý độ rộng khẩu vị rủi ro biến động" };

export default function MarketPulse() {
  return (
    <div className="grid gap-3">
      <PageHead title="Nhịp thị trường" sub="Khẩu vị rủi ro, chỉ số biến động, độ rộng thị trường và tâm lý tin tức trong một màn hình." />
      <Panel title="Market Pulse" icon={HeartPulse}>
        <PulseView />
      </Panel>
      <Disclaimer>Các chỉ số được tổng hợp từ nến ngày và tin đã lưu, chỉ mang tính tham khảo, không phải khuyến nghị đầu tư.</Disclaimer>
    </div>
  );
}
