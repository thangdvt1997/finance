import { Grid2x2 } from "lucide-react";
import { pct, symbolLabel } from "../lib/format";
import { Skeleton } from "../components/ui";
import { useSparkChanges, useSymbolsBy } from "../terminal/hooks";
import { useWidget } from "../terminal/ui";

export const meta = {
  id: "heat-strip", title: "Bản đồ nhiệt", icon: Grid2x2, group: "Thị trường", linkable: true,
  desc: "Ô màu biến động 48 giờ; bấm ô để đổi mã cho các widget cùng kênh.",
  defaultSize: { w: 9, h: 6 }, minSize: { w: 4, h: 3 },
  configSchema: [
    { key: "cls", label: "Danh sách", type: "select", default: "watch", options: [{ value: "watch", label: "Nhóm theo dõi chung" }, { value: "all", label: "Mọi mã" }, { value: "forex", label: "Forex" }, { value: "crypto", label: "Tiền ảo" }, { value: "commodity", label: "Kim loại & hàng hoá" }, { value: "index", label: "Chỉ số & ETF" }, { value: "us", label: "Cổ phiếu Mỹ" }, { value: "vn", label: "Cổ phiếu VN" }] },
    { key: "max", label: "Số ô tối đa", type: "number", default: 24, min: 4, max: 60 },
  ],
};

export default function HeatStrip() {
  const { config, symbol, setSymbol } = useWidget();
  const { symbols, pending } = useSymbolsBy(config.cls, config.max || 24);
  const ch = useSparkChanges(symbols);
  if (pending) return <div className="tm-pad"><Skeleton rows={3} /></div>;
  if (!symbols.length) return <div className="tm-pad text-muted text-[12.5px]">Chưa có mã.</div>;
  return (
    <div className="tm-pad h-full">
      <div className="grid gap-[3px] h-full auto-rows-fr" style={{ gridTemplateColumns: "repeat(auto-fill,minmax(5.2rem,1fr))" }} role="group" aria-label="Biến động 48 giờ gần nhất">
        {symbols.map((s) => {
          const c = ch[s]?.change;
          const a = c == null ? 0 : Math.min(1, Math.abs(c) / 1.5);
          const col = c == null ? "var(--panel2)" : `color-mix(in srgb, ${c >= 0 ? "var(--up)" : "var(--down)"} ${Math.round(14 + a * 52)}%, var(--panel2))`;
          return (
            <button key={s} type="button" onClick={() => setSymbol(s)} aria-pressed={symbol === s}
              className="rounded-[5px] px-2 py-1 min-w-0 text-left border-0 cursor-pointer text-fg flex flex-col justify-center" style={{ background: col, outline: symbol === s ? "2px solid var(--accent)" : undefined, outlineOffset: -2 }}>
              <span className="text-[11.5px] font-semibold truncate">{symbolLabel(s)}</span>
              <span className="num text-[12px]">{pct(c)}</span>
            </button>
          );
        })}
      </div>
    </div>
  );
}
