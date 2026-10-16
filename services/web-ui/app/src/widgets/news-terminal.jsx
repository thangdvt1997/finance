import { Radio } from "lucide-react";
import { VirtualList, QState } from "../components/intel/bits";
import { NewsRow } from "../components/intel/NewsParts";
import { markRead, useNewsFeed, useNewsMarks } from "../lib/intelNews";
import { useWidget } from "../terminal/ui";

export const meta = {
  id: "news-terminal", title: "Dòng tin squawk", icon: Radio, group: "Tin & lịch", linkable: true,
  desc: "Dòng tin thời gian thực kiểu squawk: lọc theo chủ đề, mức quan trọng, cảm xúc; mỗi tin một dòng hoặc thẻ.",
  defaultSize: { w: 9, h: 16 }, minSize: { w: 5, h: 6 },
  configSchema: [
    { key: "dens", label: "Mật độ", type: "select", default: "squawk", options: [{ value: "squawk", label: "Squawk (1 dòng)" }, { value: "normal", label: "Thẻ" }] },
    { key: "imp", label: "Mức quan trọng tối thiểu", type: "select", default: "0", options: [{ value: "0", label: "Tất cả" }, { value: "2", label: "Chú ý trở lên" }, { value: "3", label: "Chỉ quan trọng" }] },
    { key: "sent", label: "Cảm xúc", type: "select", default: "", options: [{ value: "", label: "Tất cả" }, { value: "pos", label: "Tích cực" }, { value: "neg", label: "Tiêu cực" }, { value: "neu", label: "Trung tính" }] },
    { key: "topic", label: "Chủ đề", type: "select", default: "", options: [{ value: "", label: "Mọi chủ đề" }, { value: "monetary_policy", label: "Chính sách tiền tệ" }, { value: "inflation", label: "Lạm phát" }, { value: "jobs", label: "Việc làm" }, { value: "growth", label: "Tăng trưởng" }, { value: "geopolitics", label: "Địa chính trị" }, { value: "energy", label: "Năng lượng" }, { value: "precious_metals", label: "Kim loại quý" }, { value: "fx_markets", label: "Ngoại hối" }, { value: "equities", label: "Cổ phiếu & chỉ số" }, { value: "crypto", label: "Tiền ảo" }, { value: "banking_credit", label: "Ngân hàng & tín dụng" }, { value: "real_estate", label: "Bất động sản" }, { value: "tech_ai", label: "Công nghệ & AI" }] },
    { key: "bySymbol", label: "Lọc theo mã đang theo dõi (khi gắn kênh màu)", type: "bool", default: true },
  ],
};

export default function NewsTerminalWidget() {
  const { config, symbol, channel } = useWidget();
  const follow = !!channel && config.bySymbol !== false && symbol;
  const dens = config.dens === "normal" ? "normal" : "squawk";
  const filters = { symbol: follow ? symbol : undefined, topic: config.topic || undefined, min_importance: Number(config.imp) || undefined, sentiment: config.sent || undefined, hours: 72 };
  const feed = useNewsFeed(filters, { pageSize: 50 });
  const marks = useNewsMarks();
  const list = feed.items;
  const rowH = dens === "normal" ? 76 : 36;
  if (!list.length) return <div className="tm-fill"><QState q={feed} compact rows={6} empty="Chưa có tin khớp bộ lọc." isEmpty={() => true} /></div>;
  return (
    <div className="tm-fill">
      {follow && <div className="tm-sub px-2 py-1 border-b border-line">Lọc theo {symbol.replace(/^[A-Za-z]+:/, "")}</div>}
      <VirtualList count={list.length} rowHeight={rowH} ariaLabel="Dòng tin" onNearEnd={feed.hasNextPage && !feed.isFetchingNextPage ? () => feed.fetchNextPage() : undefined}
        render={(i) => { const it = list[i]; return <NewsRow it={it} selected={false} read={marks.isRead(it.url)} saved={marks.isSaved(it.url)} density={dens} words={[]} fresh={it.live && Date.now() - (it.liveAt || 0) < 4000}
          onSelect={(x) => { markRead(x.url); window.open(x.url, "_blank", "noopener,noreferrer"); }} />; }} />
      <div className="px-2 py-1 text-[11px] text-faint border-t border-line flex justify-between"><span>{list.length} tin</span><a href="#/tin-tuc" className="no-underline text-muted hover:text-accent">Mở terminal tin tức →</a></div>
    </div>
  );
}
