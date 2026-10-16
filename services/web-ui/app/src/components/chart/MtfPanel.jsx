// Đa khung thời gian (MTF): xu hướng + RSI + ADX + kết luận tổng hợp ở M15 / H1 / H4 / D1 cho mã hiện tại (tính trên trình duyệt từ nến).
// CHỈ BÁO KỸ THUẬT, KHÔNG PHẢI KHUYẾN NGHỊ ĐẦU TƯ.
import { useMemo } from "react";
import { useQueries } from "@tanstack/react-query";
import { api } from "../../lib/api";
import { cn } from "../ui";
import { compute, makeCols } from "./indicators";
import { VERDICT_LABEL, technicalSummary } from "./signals";
import { toBars } from "./chartData";

const MTF_TFS = ["M15", "H1", "H4", "D1"];
const last = (a) => (a && a.length ? a[a.length - 1] : null);

export function analyzeTf(bars) {
  if (bars.length < 60) return null;
  const cols = makeCols(bars);
  const e20 = last(compute("ema", { period: 20 }, cols).v), e50 = last(compute("ema", { period: 50 }, cols).v);
  const rsi = last(compute("rsi", { period: 14 }, cols).v), ad = compute("adx", { period: 14 }, cols), adx = last(ad.adx);
  const macd = compute("macd", { fast: 12, slow: 26, signal: 9 }, cols), mh = last(macd.hist);
  const px = cols.c[cols.n - 1];
  const trend = e20 != null && e50 != null ? (px > e20 && e20 > e50 ? "up" : px < e20 && e20 < e50 ? "down" : "side") : "side";
  const ts = technicalSummary(cols);
  return { trend, rsi, adx, mh, px, verdict: ts.verdictAll, ready: ts.ready };
}

const TREND = { up: ["Tăng", "text-up", "▲"], down: ["Giảm", "text-down", "▼"], side: ["Đi ngang", "text-muted", "■"] };

export default function MtfPanel({ symbol, availableTfs, activeTf, onPickTf }) {
  const tfs = MTF_TFS.filter((t) => !availableTfs?.length || availableTfs.includes(t));
  const qs = useQueries({
    queries: tfs.map((tf) => ({
      queryKey: ["bars-pro", symbol, tf, 400], queryFn: ({ signal }) => api("/bars", { symbol, tf, limit: 400, order: "desc" }, signal),
      staleTime: 60_000, refetchInterval: 120_000, enabled: !!symbol,
    })),
  });
  const stamp = qs.map((x) => x.dataUpdatedAt).join(",");
  const rows = useMemo(() => tfs.map((tf, i) => ({ tf, q: qs[i], a: qs[i].data ? analyzeTf(toBars(qs[i].data.items || [])) : null })), [stamp, tfs.join(",")]); // eslint-disable-line react-hooks/exhaustive-deps
  const score = rows.reduce((s, r) => s + (r.a ? (r.a.trend === "up" ? 1 : r.a.trend === "down" ? -1 : 0) : 0), 0);
  const agree = rows.filter((r) => r.a).length;
  return (
    <div className="grid gap-2">
      <p className="m-0 text-[12px] text-muted">Xu hướng của <b>{symbol.replace(/^(VN|US):/, "")}</b> ở các khung lớn (EMA20/50 + giá, RSI 14, ADX 14, MACD, tổng hợp 20+ chỉ báo).</p>
      <div className="overflow-x-auto">
        <table className="w-full border-collapse text-[12px]" aria-label="Đa khung thời gian">
          <thead><tr className="text-left text-faint">{["Khung", "Xu hướng", "RSI", "ADX", "MACD", "Tổng hợp"].map((h) => <th key={h} className="px-1.5 py-1 font-medium">{h}</th>)}</tr></thead>
          <tbody>
            {rows.map(({ tf, q, a }) => (
              <tr key={tf} className={cn("cursor-pointer border-t border-line hover:bg-panel2", tf === activeTf && "bg-[var(--accent-bg)]")} onClick={() => onPickTf?.(tf)} title="Bấm để chuyển biểu đồ sang khung này">
                <td className="px-1.5 py-1.5 font-semibold">{tf}</td>
                {q.isPending ? <td colSpan={5} className="px-1.5 text-faint">Đang tải…</td> : !a ? <td colSpan={5} className="px-1.5 text-faint">Chưa đủ dữ liệu</td> : (
                  <>
                    <td className={cn("px-1.5", TREND[a.trend][1])}>{TREND[a.trend][2]} {TREND[a.trend][0]}</td>
                    <td className={cn("num px-1.5", a.rsi > 70 ? "text-down" : a.rsi < 30 ? "text-up" : "")}>{a.rsi?.toFixed(1) ?? "—"}</td>
                    <td className="num px-1.5">{a.adx?.toFixed(1) ?? "—"}{a.adx != null && <span className="text-faint">{a.adx >= 25 ? " mạnh" : " yếu"}</span>}</td>
                    <td className={cn("px-1.5", a.mh > 0 ? "text-up" : "text-down")}>{a.mh == null ? "—" : a.mh > 0 ? "▲ dương" : "▼ âm"}</td>
                    <td className={cn("px-1.5 font-medium", a.verdict.includes("buy") ? "text-up" : a.verdict.includes("sell") ? "text-down" : "text-muted")}>{VERDICT_LABEL[a.verdict]}</td>
                  </>
                )}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {agree > 0 && (
        <p className={cn("m-0 rounded border border-line bg-panel2 p-2 text-[12px]", Math.abs(score) === agree ? (score > 0 ? "text-up" : "text-down") : "text-muted")}>
          {Math.abs(score) === agree ? `Đồng thuận ${score > 0 ? "TĂNG" : "GIẢM"} ở cả ${agree} khung.` : `Các khung chưa đồng thuận (điểm ${score > 0 ? "+" : ""}${score}/${agree}).`}
        </p>
      )}
    </div>
  );
}
