import { UsersRound } from "lucide-react";
import { Disclaimer, PageHead, Panel } from "../components/ui";
import { PositioningView } from "../components/intel/CotView";

export const meta = { path: "vi-the-lon", label: "Vị thế lớn & đồng thuận", group: "Thông tin", icon: UsersRound, order: 45, keywords: "positioning net long short percentile consensus chuyên gia vị thế đầu cơ" };

export default function Positioning() {
  return (
    <>
      <PageHead title="Vị thế lớn & đồng thuận chuyên gia" sub="Vị thế ròng của nhóm đầu cơ lớn theo báo cáo hàng tuần và mức nghiêng tổng hợp từ chuyên gia công khai." />
      <div><Disclaimer><b>Tham khảo, không phải tín hiệu hay khuyến nghị đầu tư.</b> Báo cáo hàng tuần công bố trễ vài ngày; dữ liệu chuyên gia chỉ là thống kê thông tin công khai.</Disclaimer></div>
      <Panel title="Vị thế lớn & đồng thuận" icon={UsersRound}><PositioningView /></Panel>
    </>
  );
}
