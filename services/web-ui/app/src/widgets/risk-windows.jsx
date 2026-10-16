import { ShieldAlert } from "lucide-react";
import { Async } from "../components/ui";
import { RiskSummary } from "../components/risk";
import { useRiskAll } from "../lib/queries";
import { symbolLabel } from "../lib/format";
import { useWidget } from "../terminal/ui";

export const meta = {
  id: "risk-windows", title: "Cửa sổ rủi ro tin", icon: ShieldAlert, group: "Tin & lịch", desc: "Mã đang/sắp trong cửa sổ T-15…T+30 quanh sự kiện tác động cao (chỉ hiển thị cảnh báo, không đặt lệnh).",
  defaultSize: { w: 8, h: 6 }, minSize: { w: 4, h: 3 },
};

export default function RiskWindows() {
  useWidget();
  const q = useRiskAll();
  return (
    <div className="tm-fill tm-scroll tm-pad">
      <Async q={q} rows={3} empty="Không có cửa sổ rủi ro nào." isEmpty={(d) => !d?.symbols?.length}>
        {(d) => <RiskSummary data={d} labels={symbolLabel} />}
      </Async>
    </div>
  );
}
