import { useMemo } from "react";
import { Rows3 } from "lucide-react";
import { useWatchSymbols } from "../lib/prefs";
import { useSymbols, useQuotesLatest } from "../lib/queries";
import { useQuote, useStream } from "../lib/stream";
import { classOf } from "../lib/assetClass";
import { price, symbolLabel, pct } from "../lib/format";
import { cn } from "../components/ui";
import { useWidget } from "../terminal/ui";

export const meta = {
  id: "ticker-tape", title: "Băng chạy giá", icon: Rows3, group: "Thị trường", bare: true, desc: "Băng giá chạy ngang, chọn danh sách và tốc độ.",
  defaultSize: { w: 24, h: 2 }, minSize: { w: 4, h: 2 },
  configSchema: [
    { key: "cls", label: "Nguồn danh sách", type: "select", default: "watch", options: [{ value: "watch", label: "Nhóm theo dõi đang chọn" }, { value: "all", label: "Mọi mã" }, { value: "forex", label: "Forex" }, { value: "crypto", label: "Tiền ảo" }, { value: "vn", label: "Cổ phiếu VN" }, { value: "us", label: "Cổ phiếu Mỹ" }, { value: "commodity", label: "Kim loại & hàng hoá" }, { value: "index", label: "Chỉ số & ETF" }, { value: "custom", label: "Danh sách riêng" }] },
    { key: "symbols", label: "Danh sách riêng (khi chọn “Danh sách riêng”)", type: "symbols", default: [] },
    { key: "speed", label: "Tốc độ (giây cho một vòng)", type: "number", default: 60, min: 15, max: 300, step: 5 },
    { key: "pause", label: "Dừng khi rê chuột", type: "bool", default: true },
  ],
};

function Item({ symbol }) {
  const q = useQuote(symbol);
  if (!q) return null;
  const px = q.bid ?? q.ask;
  return (
    <span className="inline-flex items-center gap-2 px-3 whitespace-nowrap h-full">
      <b className="text-[12px]">{symbolLabel(symbol)}</b>
      <span className={cn("num text-[12.5px]", q.dir > 0 ? "up" : q.dir < 0 ? "down" : "")}>{price(symbol, px)} <span aria-hidden="true">{q.dir > 0 ? "▲" : q.dir < 0 ? "▼" : ""}</span></span>
    </span>
  );
}

export default function TickerTapeWidget() {
  const { config } = useWidget();
  const watch = useWatchSymbols();
  const all = useSymbols();
  const syms = useMemo(() => {
    const c = config.cls;
    if (c === "watch") return watch;
    if (c === "custom") return config.symbols || [];
    const list = (all.data || []);
    return list.filter((s) => c === "all" || classOf(s) === c).map((s) => s.symbol);
  }, [config.cls, config.symbols, watch, all.data]).slice(0, 60);
  useQuotesLatest(syms);
  useStream();
  if (all.isError && config.cls !== "watch" && config.cls !== "custom") return <div className="tm-pad text-down text-[12.5px]">Không tải được danh sách mã.</div>;
  if (!syms.length) return <div className="tm-pad text-muted text-[12.5px]">Chưa có mã trong danh sách này.</div>;
  return (
    <div className={cn("tape h-full", config.pause === false && "tm-nopause")} role="marquee" aria-label="Băng giá trực tiếp" style={{ "--tape-dur": `${config.speed || 60}s` }}>
      <div className="tape-track h-full" style={{ animationDuration: `${config.speed || 60}s` }}>
        {[0, 1].map((k) => <div key={k} className="flex h-full items-center" aria-hidden={k === 1 ? "true" : undefined}>{syms.map((s) => <Item key={s} symbol={s} />)}</div>)}
      </div>
    </div>
  );
}
