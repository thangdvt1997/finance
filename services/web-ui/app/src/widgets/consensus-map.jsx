import { Scale } from "lucide-react";
import { useWidget } from "../terminal/ui";
import ConsensusMap from "../components/experts/ConsensusMap";
import { FIXED_NOTE } from "../lib/trackrecord";
import "../components/experts/experts.css";

export const meta = {
  id: "consensus-map", title: "Đồng thuận chuyên gia", icon: Scale, group: "Thông tin", linkable: true,
  desc: "Bao nhiêu chuyên gia nghiêng tăng/giảm theo từng mã, có trọng số uy tín; mở rộng để xem ai. Chỉ tham khảo.",
  defaultSize: { w: 9, h: 14 }, minSize: { w: 5, h: 7 },
  configSchema: [
    { key: "window_days", label: "Cửa sổ (ngày)", type: "select", default: "14", options: [{ value: "7", label: "7 ngày" }, { value: "14", label: "14 ngày" }, { value: "30", label: "30 ngày" }, { value: "90", label: "90 ngày" }] },
    { key: "scope", label: "Tài sản", type: "select", default: "all", options: [{ value: "all", label: "Mọi tài sản" }, { value: "forex", label: "Ngoại hối" }, { value: "metal", label: "Kim loại" }, { value: "index", label: "Chỉ số" }, { value: "commodity", label: "Hàng hoá" }, { value: "crypto", label: "Tiền số" }] },
    { key: "level", label: "Mức", type: "select", default: "", options: [{ value: "", label: "Mọi mức" }, { value: "consensus", label: "Chỉ đồng thuận" }, { value: "weak", label: "Chỉ nghiêng nhẹ" }] },
    { key: "min_experts", label: "Tối thiểu chuyên gia", type: "number", default: 2, min: 1, max: 10 },
    { key: "limit", label: "Số mã tối đa", type: "number", default: 12, min: 3, max: 40 },
    { key: "bySymbol", label: "Lọc theo mã đang theo dõi (khi gắn kênh)", type: "bool", default: true },
  ],
};

export default function ConsensusMapWidget() {
  const { config, symbol, channel } = useWidget();
  const follow = !!channel && config.bySymbol !== false && symbol;
  return (
    <div className="tm-fill tm-scroll tm-pad">
      <ConsensusMap hideControls compact windowDays={config.window_days || "14"} scope={config.scope || "all"} minExperts={String(config.min_experts || 1)} level={config.level || ""} symbol={follow ? symbol : undefined} limit={config.limit || 12} />
      <div className="xp-note mt-2">{FIXED_NOTE}</div>
    </div>
  );
}
