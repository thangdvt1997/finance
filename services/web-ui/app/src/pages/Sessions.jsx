import { Clock, Activity } from "lucide-react";
import { Disclaimer, PageHead, Panel } from "../components/ui";
import { MarketHoursView } from "../components/intel/MarketHours";
import { SessionRangesView } from "../components/intel/SessionRanges";

export const meta = {
  path: "phien-giao-dich", label: "Phiên giao dịch", group: "Thị trường", icon: Clock, order: 64,
  keywords: "session tokyo london new york giờ mở cửa ngày lễ holiday phiên", roles: ["master", "client"],
};

export default function SessionsPage() {
  return (
    <>
      <PageHead title="Phiên giao dịch & giờ mở cửa" sub="Trạng thái mở/đóng của các sàn, đếm ngược, ngày lễ sắp tới và biên độ giá trung bình theo phiên." />
      <div className="grid gap-3 xl:grid-cols-2 items-start">
        <Panel title="Giờ mở cửa các sàn" icon={Clock}><MarketHoursView /></Panel>
        <Panel title="Biên độ theo giờ và theo phiên" icon={Activity}><SessionRangesView /></Panel>
      </div>
      <Disclaimer>Giờ giao dịch và ngày lễ chỉ để tham khảo, hãy kiểm tra lịch chính thức của sàn. Thống kê biên độ là dữ liệu quá khứ, không phải khuyến nghị đầu tư.</Disclaimer>
    </>
  );
}
