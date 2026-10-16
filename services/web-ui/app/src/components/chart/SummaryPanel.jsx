// "Tóm tắt kỹ thuật" (kiểu TradingView): 3 đồng hồ Dao động / Tổng hợp / Trung bình động + bảng chi tiết + số liệu từ analytics máy chủ.
// CHỈ BÁO KỸ THUẬT, KHÔNG PHẢI KHUYẾN NGHỊ ĐẦU TƯ.
import { useMemo } from "react";
import { cn } from "../ui";
import { technicalSummary, verdict, verdictScore, VERDICT_LABEL, ACTION_LABEL } from "./signals";
import { price, dateTime } from "../../lib/format";

const SEG = [
  { c: "var(--down)", o: 1 }, { c: "var(--down)", o: 0.55 }, { c: "var(--faint)", o: 0.6 }, { c: "var(--up)", o: 0.55 }, { c: "var(--up)", o: 1 },
];

function arc(cx, cy, r, a0, a1) {
  const p = (a) => [cx + r * Math.cos(a), cy - r * Math.sin(a)];
  const [x0, y0] = p(a0), [x1, y1] = p(a1);
  return `M${x0.toFixed(2)} ${y0.toFixed(2)} A${r} ${r} 0 0 1 ${x1.toFixed(2)} ${y1.toFixed(2)}`;
}

export function Gauge({ title, t, size = "md" }) {
  const v = verdict(t), score = verdictScore(t);
  const angle = -90 + ((score + 1) / 2) * 180; // -90 (bán mạnh) … +90 (mua mạnh)
  const tone = v.includes("buy") ? "text-up" : v.includes("sell") ? "text-down" : "text-muted";
  const big = size === "lg";
  return (
    <figure className="m-0 flex min-w-0 flex-col items-center" aria-label={`${title}: ${VERDICT_LABEL[v]}`}>
      <figcaption className="text-[11.5px] font-medium text-muted">{title}</figcaption>
      <svg viewBox="0 0 120 70" className={big ? "w-[150px]" : "w-[104px]"} role="img" aria-hidden="true">
        {SEG.map((s, i) => {
          const a0 = Math.PI - (i * Math.PI) / 5 - 0.03, a1 = Math.PI - ((i + 1) * Math.PI) / 5 + 0.03;
          return <path key={i} d={arc(60, 62, 48, a0, a1)} fill="none" strokeWidth="9" stroke={s.c} strokeOpacity={s.o} />;
        })}
        <g transform={`rotate(${angle.toFixed(1)} 60 62)`}>
          <path d="M60 62 L58.4 22 L60 16 L61.6 22 Z" fill="var(--fg)" />
        </g>
        <circle cx="60" cy="62" r="3.4" fill="var(--fg)" />
      </svg>
      <b className={cn("text-[13.5px]", tone)}>{VERDICT_LABEL[v]}</b>
      <div className="mt-0.5 flex gap-2 text-[11px] num">
        <span className="text-down">{t.sell}</span><span className="text-faint">{t.neutral}</span><span className="text-up">{t.buy}</span>
      </div>
    </figure>
  );
}

const ACT_CLS = { buy: "up", sell: "down", neutral: "text-muted" };

function Table({ title, items, dec }) {
  if (!items.length) return null;
  return (
    <section className="mt-3">
      <h3 className="m-0 mb-1 text-[11.5px] font-semibold text-muted">{title}</h3>
      <table className="tbl !text-[12px]">
        <tbody>
          {items.map((it) => (
            <tr key={it.name}>
              <td className="!py-[3px]">{it.name}</td>
              <td className="r num !py-[3px]">{Number.isFinite(it.value) ? (Math.abs(it.value) >= 1000 ? it.value.toFixed(0) : it.value.toFixed(Math.abs(it.value) < 10 ? Math.max(dec, 2) : 2)) : "—"}</td>
              <td className={cn("r !py-[3px] font-semibold", ACT_CLS[it.action])}>{ACTION_LABEL[it.action]}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  );
}

const TREND = { up: "Tăng", down: "Giảm", side: "Đi ngang" };
const MOM = { overbought: "Quá mua", oversold: "Quá bán", bullish: "Tích cực", bearish: "Tiêu cực", neutral: "Trung tính" };

export default function SummaryPanel({ cols, tf, symbol, decimals, server, serverQ, serverPivot, onTogglePivot }) {
  const sum = useMemo(() => technicalSummary(cols), [cols]);
  const ind = server?.indicators || {};
  const pv = server?.pivot;
  return (
    <div className="p-3 text-[12.5px]">
      <div className="mb-2 flex items-baseline justify-between gap-2">
        <h2 className="m-0 text-[13px] font-semibold">Tóm tắt kỹ thuật · {symbol.replace(/^(VN|US):/, "")} · {tf}</h2>
      </div>
      {!sum.ready ? <p className="text-muted">Cần thêm dữ liệu nến để tính tóm tắt.</p> : (
        <>
          <div className="grid grid-cols-3 items-start gap-1">
            <Gauge title="Dao động" t={sum.osc} />
            <Gauge title="Tổng hợp" t={sum.all} size="lg" />
            <Gauge title="MA" t={sum.ma} />
          </div>
          <Table title="Dao động" items={sum.osc.items} dec={decimals} />
          <Table title="Trung bình động" items={sum.ma.items} dec={decimals} />
        </>
      )}

      <section className="mt-4 border-t border-line pt-3">
        <h3 className="m-0 mb-1 text-[11.5px] font-semibold text-muted">Từ máy chủ (analytics)</h3>
        {serverQ?.isPending && serverQ.fetchStatus !== "idle" && <p className="text-muted">Đang tải…</p>}
        {(serverQ?.isError || (serverQ?.isSuccess && !server) || (serverQ?.isPending && serverQ.fetchStatus === "idle")) && <p className="text-muted">Chưa có phân tích máy chủ cho mã/khung này.</p>}
        {server && (
          <>
            <div className="grid grid-cols-2 gap-x-3 gap-y-1">
              <KV k="Xu hướng" v={TREND[server.trend] || server.trend} />
              <KV k="Động lượng" v={MOM[server.momentum] || server.momentum} />
              <KV k="RSI" v={ind.rsi?.toFixed(1)} />
              <KV k="ADX" v={ind.adx?.toFixed(1)} />
              <KV k="ATR" v={ind.atr != null ? price(symbol, ind.atr).replace(/^0\./, "0.") : null} sub={server.atr_pct != null ? `${server.atr_pct}%` : null} />
              <KV k="Stoch %K" v={ind.stoch_k?.toFixed(1)} />
            </div>
            {pv && (
              <table className="tbl mt-2 !text-[12px]">
                <tbody>
                  {["r2", "r1", "p", "s1", "s2"].filter((k) => pv[k] != null).map((k) => (
                    <tr key={k}><td className="!py-[2px] font-medium">{k.toUpperCase()}</td><td className="r num !py-[2px]">{price(symbol, pv[k])}</td></tr>
                  ))}
                </tbody>
              </table>
            )}
            {pv && <button type="button" className="btn mt-2 w-full justify-center" aria-pressed={serverPivot} onClick={onTogglePivot}>{serverPivot ? "Ẩn pivot trên biểu đồ" : "Vẽ pivot máy chủ lên biểu đồ"}</button>}
            {server.states?.length > 0 && (
              <ul className="m-0 mt-2 flex list-none flex-wrap gap-1 p-0">
                {server.states.map((s) => <li key={s.code} className={cn("chip", s.tone === "up" ? "up" : s.tone === "down" ? "down" : "")} title={s.rule}>{s.label}</li>)}
              </ul>
            )}
            <p className="m-0 mt-2 text-[11px] text-faint">Cập nhật {server.bar_ts ? dateTime(server.bar_ts) : "—"} · {server.pivot_note || ""}</p>
          </>
        )}
      </section>
      <p className="m-0 mt-3 rounded border border-line bg-panel2 p-2 text-[11px] text-muted">
        Chỉ báo kỹ thuật, không phải khuyến nghị đầu tư. Kết quả tính từ {cols.n} nến đã nạp của khung {tf}.
      </p>
    </div>
  );
}

function KV({ k, v, sub }) {
  return (
    <div className="flex items-baseline justify-between gap-2 border-b border-line py-[2px]">
      <span className="text-muted">{k}</span>
      <span className="num">{v ?? "—"}{sub && <span className="ml-1 text-faint text-[11px]">{sub}</span>}</span>
    </div>
  );
}
