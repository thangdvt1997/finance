import { useMemo } from "react";
import { CandlestickChart } from "lucide-react";
import { useQuery } from "@tanstack/react-query";
import { api } from "../lib/api";
import { useQuote } from "../lib/stream";
import { useRtQuoteFeed } from "../lib/rtbridge";
import { pct, price, signCls, symbolLabel, symbolMarket } from "../lib/format";
import { cn } from "../components/ui";
import { SymbolInput, useWidget } from "../terminal/ui";

export const meta = {
  id: "quote-card", title: "Thẻ giá", icon: CandlestickChart, group: "Thị trường", linkable: true, desc: "Giá lớn, % thay đổi, spread và đường giá; đổi mã tại chỗ hoặc theo kênh màu.",
  defaultSize: { w: 10, h: 10 }, minSize: { w: 5, h: 5 },
  configSchema: [
    { key: "symbol", label: "Mã", type: "symbol", default: "EURUSD" },
    { key: "tf", label: "Khung thời gian", type: "select", default: "H1", options: ["M15", "H1", "H4", "D1"] },
  ],
};

export default function QuoteCard() {
  const { symbol, setSymbol, config, size } = useWidget();
  const q = useQuote(symbol);
  useRtQuoteFeed(symbol ? [symbol] : undefined);
  const tf = config.tf || "H1";
  const bars = useQuery({ queryKey: ["qcard", symbol, tf], enabled: !!symbol, queryFn: ({ signal }) => api("/bars", { symbol, tf, limit: 120, order: "desc" }, signal), staleTime: 30_000, refetchInterval: 60_000 });
  const closes = useMemo(() => [...(bars.data?.items || [])].reverse().map((b) => b.c), [bars.data]);
  const px = q?.bid ?? q?.ask ?? closes[closes.length - 1];
  const chg = closes.length > 1 ? ((closes[closes.length - 1] - closes[0]) / closes[0]) * 100 : null;
  const spread = q?.bid != null && q?.ask != null ? q.ask - q.bid : null;
  const W = Math.max(120, size.w - 24), H = Math.max(50, size.h - 118);
  const path = useMemo(() => {
    if (closes.length < 2) return null;
    const lo = Math.min(...closes), hi = Math.max(...closes), sp = hi - lo || 1;
    const pts = closes.map((v, i) => [((i / (closes.length - 1)) * W).toFixed(1), (H - 4 - ((v - lo) / sp) * (H - 8)).toFixed(1)]);
    const line = pts.map((p) => p.join(",")).join(" ");
    return { line, area: `0,${H} ${line} ${W},${H}`, lo, hi };
  }, [closes, W, H]);
  const col = chg >= 0 ? "var(--up)" : "var(--down)";
  return (
    <div className="tm-fill tm-pad gap-2">
      <div className="flex items-center gap-2 tm-nodrag"><SymbolInput value={symbol} onChange={setSymbol} className="!h-7 w-[150px] !text-[12px]" label="Mã" /><span className="tm-sub">{symbol ? symbolMarket(symbol) : ""}</span></div>
      <div className="flex items-baseline gap-3 flex-wrap">
        <span className={cn("num leading-none", q?.dir > 0 ? "up" : q?.dir < 0 ? "down" : "")} style={{ fontSize: Math.max(24, Math.min(46, size.w / 9)) }}>{symbol ? price(symbol, px) : "—"}</span>
        <span className={cn("num text-[15px]", signCls(chg))}>{pct(chg)}</span>
        <span className="tm-sub">{symbol ? symbolLabel(symbol) : ""} · {tf} · spread {spread == null ? "—" : spread < 1 ? Number(spread.toFixed(5)) : spread.toFixed(2)}</span>
      </div>
      <div className="flex-1 min-h-0">
        {path ? (
          <svg width={W} height={H} viewBox={`0 0 ${W} ${H}`} role="img" aria-label={`Đường giá ${symbolLabel(symbol)} khung ${tf}`} className="block">
            <polygon points={path.area} fill={col} opacity=".12" />
            <polyline points={path.line} fill="none" stroke={col} strokeWidth="1.6" strokeLinejoin="round" />
            <text x="2" y="10" fontSize="9.5" fill="var(--faint)" className="num">{price(symbol, path.hi)}</text>
            <text x="2" y={H - 2} fontSize="9.5" fill="var(--faint)" className="num">{price(symbol, path.lo)}</text>
          </svg>
        ) : <div className="tm-sub">{bars.isPending ? "Đang tải…" : "Chưa có dữ liệu nến."}</div>}
      </div>
    </div>
  );
}
