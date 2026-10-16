import { UsersRound } from "lucide-react";
import { useWidget } from "../terminal/ui";
import { PositioningView } from "../components/intel/CotView";

export const meta = {
  id: "cot-positions", title: "Vị thế đầu cơ lớn", icon: UsersRound, group: "Thông tin",
  desc: "Vị thế ròng nhóm đầu cơ lớn theo báo cáo hàng tuần: net, thay đổi tuần, phân vị. Tham khảo.",
  defaultSize: { w: 9, h: 14 }, minSize: { w: 5, h: 8 },
  configSchema: [
    { key: "view", label: "Kiểu hiển thị", type: "select", default: "cards", options: [{ value: "cards", label: "Thẻ" }, { value: "table", label: "Bảng" }] },
    { key: "symbols", label: "Lọc theo mã (trống = tất cả)", type: "symbols", default: [] },
  ],
};

export default function CotWidget() {
  const { config } = useWidget();
  return (
    <div className="tm-fill"><div className="tm-scroll">
      <PositioningView compact view={config.view || "cards"} symbols={config.symbols} />
    </div></div>
  );
}
