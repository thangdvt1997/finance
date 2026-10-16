import { MessagesSquare } from "lucide-react";
import { useWidget } from "../terminal/ui";
import ExpertFeed from "../components/experts/ExpertFeed";
import { FIXED_NOTE } from "../lib/trackrecord";
import "../components/experts/experts.css";

export const meta = {
  id: "expert-feed", title: "Quan điểm chuyên gia", icon: MessagesSquare, group: "Thông tin", linkable: true,
  desc: "Dòng thời gian quan điểm tăng/giảm mới nhất của chuyên gia; lọc theo mã và hướng. Chỉ tham khảo.",
  defaultSize: { w: 7, h: 14 }, minSize: { w: 4, h: 6 },
  configSchema: [
    { key: "direction", label: "Hướng", type: "select", default: "", options: [{ value: "", label: "Tất cả" }, { value: "bullish", label: "Chỉ tăng" }, { value: "bearish", label: "Chỉ giảm" }] },
    { key: "symbol", label: "Mã cố định (trống = tất cả)", type: "text", default: "" },
    { key: "limit", label: "Số quan điểm", type: "number", default: 30, min: 10, max: 100 },
    { key: "bySymbol", label: "Lọc theo mã đang theo dõi (khi gắn kênh)", type: "bool", default: true },
  ],
};

export default function ExpertFeedWidget() {
  const { config, symbol, channel } = useWidget();
  const follow = !!channel && config.bySymbol !== false && symbol;
  const sym = follow ? symbol : (config.symbol || "").trim().toUpperCase();
  return (
    <div className="tm-fill tm-scroll tm-pad">
      {follow && <div className="tm-sub mb-1">Lọc theo {String(symbol).replace(/^[A-Za-z]+:/, "")}</div>}
      <ExpertFeed hideControls compact symbol={sym} direction={config.direction || ""} limit={config.limit || 30} />
      <div className="xp-note mt-2">{FIXED_NOTE}</div>
    </div>
  );
}
