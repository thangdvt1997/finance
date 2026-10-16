import { useMemo } from "react";
import { TrendingUp } from "lucide-react";
import { Skeleton, Sparkline, cn } from "../components/ui";
import { pct, price, signCls, symbolLabel, symbolMarket } from "../lib/format";
import { useQuote } from "../lib/stream";
import { useSparkChanges, useSymbolsBy } from "../terminal/hooks";
import { useWidget } from "../terminal/ui";

export const meta = {
  id: "top-movers", title: "Biến động mạnh nhất", icon: TrendingUp, group: "Thị trường", linkable: true,
  desc: "Xếp hạng mã tăng/giảm mạnh nhất 48 giờ trong danh sách chọn; bấm để đổi mã cho kênh màu.",
  defaultSize: { w: 7, h: 12 }, minSize: { w: 4, h: 5 },
  configSchema: [
    { key: "cls", label: "Danh sách", type: "select", default: "all", options: [{ value: "watch", label: "Nhóm theo dõi chung" }, { value: "all", label: "Mọi mã" }, { value: "forex", label: "Forex" }, { value: "crypto", label: "Tiền ảo" }, { value: "commodity", label: "Kim loại & hàng hoá" }, { value: "index", label: "Chỉ số & ETF" }, { value: "us", label: "Cổ phiếu Mỹ" }, { value: "vn", label: "Cổ phiếu VN" }] },
    { key: "n", label: "Số mã mỗi bên", type: "number", default: 6, min: 3, max: 15 },
  ],
};

function Item({ s, d, sel, onSel, max }) {
  const q = useQuote(s);
  const c = d?.change ?? 0;
  return (
    <li>
      <button type="button" onClick={onSel} aria-pressed={sel} className={cn("w-full grid grid-cols-[1fr_auto_auto] items-center gap-2 px-3 py-[5px] text-left bg-transparent border-0 cursor-pointer text-fg hover:bg-panel2", sel && "bg-[var(--accent-bg)]")}>
        <span className="min-w-0"><b className="text-[12.5px]">{symbolLabel(s)}</b> <span className="tm-sub">{symbolMarket(s)}</span>
          <span className="block h-[3px] rounded-sm mt-1" style={{ width: `${Math.max(4, Math.min(100, (Math.abs(c) / max) * 100))}%`, background: c >= 0 ? "var(--up)" : "var(--down)", opacity: .75 }} />
        </span>
        <Sparkline values={d?.closes} width={52} height={18} />
        <span className="text-right"><span className={cn("num text-[12.5px] block", signCls(d?.change))}>{pct(d?.change)}</span><span className="num tm-sub">{price(s, q?.bid ?? q?.ask)}</span></span>
      </button>
    </li>
  );
}

export default function TopMovers() {
  const { config, symbol, setSymbol } = useWidget();
  const { symbols, pending } = useSymbolsBy(config.cls || "all", 80);
  const ch = useSparkChanges(symbols);
  const n = config.n || 6;
  const { up, down, max } = useMemo(() => {
    const list = symbols.filter((s) => ch[s]?.change != null).sort((a, b) => ch[b].change - ch[a].change);
    return { up: list.filter((s) => ch[s].change > 0).slice(0, n), down: list.filter((s) => ch[s].change < 0).slice(-n).reverse(), max: Math.max(0.01, ...list.map((s) => Math.abs(ch[s].change))) };
  }, [symbols, ch, n]);
  if (pending) return <div className="tm-pad"><Skeleton rows={6} /></div>;
  return (
    <div className="tm-fill tm-scroll">
      {[["Tăng mạnh", up], ["Giảm mạnh", down]].map(([t, l]) => (
        <section key={t} aria-label={t}>
          <h4 className="m-0 px-3 pt-2 pb-1 text-[11px] uppercase tracking-wider text-faint font-semibold">{t}</h4>
          {l.length ? <ul className="m-0 p-0 list-none">{l.map((s) => <Item key={s} s={s} d={ch[s]} sel={symbol === s} onSel={() => setSymbol(s)} max={max} />)}</ul> : <p className="m-0 px-3 py-1 text-muted text-[12.5px]">Chưa có dữ liệu.</p>}
        </section>
      ))}
    </div>
  );
}
