// Biên độ trung bình theo giờ UTC + so sánh phiên Tokyo / London / New York. Thống kê quá khứ, tham khảo.
import { useEffect, useMemo, useState } from "react";
import * as echarts from "echarts/core";
import { MarkAreaComponent } from "echarts/components";
import { AlertTriangle, Info } from "lucide-react";
import { EChart, css } from "../charts";
import { cn } from "../ui";
import { QState } from "./bits";
import { useSessions } from "../../lib/queries";
import { fpct } from "../../lib/intel";

echarts.use([MarkAreaComponent]);

const SESS = [
  { k: "tokyo", name: "Tokyo", col: "--info" },
  { k: "london", name: "London", col: "--accent" },
  { k: "newyork", name: "New York", col: "--up" },
];
const p2 = (n) => String(n).padStart(2, "0");
const vnHour = (h) => (h + 7) % 24;
const MIN_N = 5;

export function SessionRangesView({ symbol, compact }) {
  const q = useSessions();
  const [sel, setSel] = useState("");
  useEffect(() => { setSel(""); }, [symbol]);
  const items = useMemo(() => q.data?.items || [], [q.data]);
  const syms = useMemo(() => items.map((x) => x.symbol).sort(), [items]);
  const eff = sel || (symbol && syms.includes(symbol) ? symbol : "") || (syms.includes("EURUSD") ? "EURUSD" : syms[0] || "");
  const it = useMemo(() => items.find((x) => x.symbol === eff), [items, eff]);
  const hourly = useMemo(() => (it?.hourly || []).slice().sort((a, b) => a.hour - b.hour), [it]);
  const peaks = useMemo(() => hourly.filter((h) => h.avg_range_pct != null).sort((a, b) => b.avg_range_pct - a.avg_range_pct).slice(0, 3), [hourly]);
  const lowN = hourly.some((h) => h.n < MIN_N) || SESS.some((s) => (it?.sessions?.[s.k]?.days ?? MIN_N) < MIN_N);
  const minN = hourly.length ? Math.min(...hourly.map((h) => h.n)) : 0;
  const hasData = it && hourly.length > 0;

  const build = () => {
    const fg = css("--muted"), line = css("--line"), panel = css("--panel"), line2 = css("--line2");
    const peak = peaks[0]?.hour;
    const cats = hourly.map((h) => p2(h.hour));
    const idx = (h) => Math.max(0, Math.min(cats.length - 1, hourly.findIndex((x) => x.hour === h)));
    const areas = SESS.map((s) => {
      const w = it?.sessions?.[s.k];
      if (!w || w.start_utc == null) return null;
      const a = idx(w.start_utc), b = idx((w.end_utc - 1 + 24) % 24);
      return [{ name: s.name, xAxis: cats[a], itemStyle: { color: css(s.col), opacity: 0.1 } }, { xAxis: cats[Math.max(a, b)] }];
    }).filter(Boolean);
    return {
      animation: false,
      grid: { left: 46, right: 12, top: 14, bottom: 40 },
      tooltip: {
        trigger: "axis", axisPointer: { type: "shadow" }, confine: true, backgroundColor: panel, borderColor: line2, textStyle: { color: css("--fg"), fontSize: 12 },
        formatter: (ps) => {
          const h = hourly[ps[0].dataIndex];
          return `<b>${p2(h.hour)}:00 UTC</b> · ${p2(vnHour(h.hour))}:00 giờ VN<br/>Biên độ TB: ${h.avg_range_pct == null ? "—" : `${h.avg_range_pct.toFixed(3)}%`}<br/>Số mẫu: ${h.n}${h.n < MIN_N ? " (ít)" : ""}`;
        },
      },
      xAxis: {
        type: "category", data: cats, axisLine: { lineStyle: { color: line2 } }, axisTick: { show: false },
        axisLabel: { color: fg, fontSize: 10.5, interval: 0, formatter: (v) => `${v}\n{vn|${p2(vnHour(+v))}}`, rich: { vn: { color: css("--faint"), fontSize: 10 } } },
      },
      yAxis: { type: "value", axisLabel: { color: fg, fontSize: 11, formatter: (v) => `${v}%` }, splitLine: { lineStyle: { color: line } } },
      series: [{
        type: "bar", barMaxWidth: 22,
        data: hourly.map((h) => ({ value: h.avg_range_pct, itemStyle: { color: h.hour === peak ? css("--accent") : css("--info"), opacity: h.n < MIN_N ? 0.4 : 0.9, borderRadius: [2, 2, 0, 0] } })),
        markArea: { silent: true, label: { show: true, position: "insideTop", color: fg, fontSize: 10.5 }, data: areas },
      }],
    };
  };

  return (
    <div className={cn("flex flex-col gap-3", compact && "tm-pad")}>
      <div className="flex flex-wrap items-center gap-2">
        <label className="flex items-center gap-1 text-[12px] text-muted">Mã
          <select className="field" aria-label="Chọn mã" value={eff} onChange={(e) => setSel(e.target.value)} disabled={!syms.length}>
            {syms.map((s) => <option key={s} value={s}>{s}</option>)}
          </select>
        </label>
        {it && <span className="chip" title="Số ngày trong cửa sổ thống kê">{it.days_window} ngày · {it.bars} nến</span>}
      </div>

      <QState q={q} compact={compact} rows={6} empty="Chưa có thống kê phiên." hint="Cần đủ nến giờ đã lưu." isEmpty={(x) => !x || !(x.items || []).length} />
      {!q.isPending && !q.isError && items.length > 0 && !hasData && (
        <div className="text-[12.5px] text-muted">Chưa có thống kê phiên cho {eff || "mã này"}.</div>
      )}
      {hasData && (
        <>
          {lowN && (
            <div role="note" className="flex gap-2 items-start text-[12px] text-muted rounded-md border border-line2 bg-panel2 px-2 py-1.5">
              <AlertTriangle size={14} className="text-accent shrink-0 mt-[1px]" aria-hidden="true" />
              <span>Độ tin cậy thấp: có giờ hoặc phiên chỉ có dưới {MIN_N} ngày mẫu (ít nhất {minN}). Cột mờ = mẫu ít.</span>
            </div>
          )}
          <div className="text-[12.5px]">
            Giờ biến động mạnh nhất:{" "}
            {peaks.map((h, i) => (
              <span key={h.hour}>{i > 0 && ", "}<b className="num">{p2(vnHour(h.hour))}:00</b> <span className="text-faint">({p2(h.hour)}:00 UTC, {h.avg_range_pct.toFixed(3)}%)</span></span>
            ))}{" "}
            <span className="text-faint">- giờ Việt Nam.</span>
          </div>
          <div className="flex flex-col" style={{ minHeight: compact ? 190 : 260 }}>
            <EChart build={build} deps={[it, hourly]} height={compact ? 190 : 260} label={`Biên độ trung bình theo giờ của ${eff}`} />
          </div>
          <p className="m-0 text-[11px] text-faint">Trục ngang: dòng trên = giờ UTC, dòng dưới = giờ VN (UTC+7). Vùng nền = phiên Tokyo / London / New York (cố định theo UTC, không chỉnh DST).</p>

          <div className="overflow-auto" role="region" aria-label="So sánh các phiên" tabIndex={0}>
            <table className="tbl" style={{ minWidth: compact ? 380 : 520 }}>
              <thead>
                <tr>
                  <th scope="col" className="text-left">Phiên</th>
                  <th scope="col" className="text-right">Giờ VN</th>
                  <th scope="col" className="text-right">Biên độ TB</th>
                  <th scope="col" className="text-right">|Lợi suất| TB</th>
                  {!compact && <th scope="col" className="text-right">Lợi suất TB</th>}
                  <th scope="col" className="text-right">Ngày mẫu</th>
                </tr>
              </thead>
              <tbody>
                {SESS.map((s) => {
                  const w = it.sessions?.[s.k];
                  if (!w) return null;
                  const best = Math.max(...SESS.map((x) => it.sessions?.[x.k]?.avg_range_pct ?? 0));
                  return (
                    <tr key={s.k}>
                      <th scope="row" className="text-left whitespace-nowrap"><span aria-hidden="true" style={{ display: "inline-block", width: 8, height: 8, borderRadius: 2, marginRight: 6, background: `var(${s.col})` }} />{s.name}</th>
                      <td className="num text-right whitespace-nowrap">{p2(vnHour(w.start_utc))}:00–{p2(vnHour(w.end_utc))}:00</td>
                      <td className="num text-right">{w.avg_range_pct != null ? `${w.avg_range_pct.toFixed(3)}%` : "—"}{w.avg_range_pct != null && w.avg_range_pct === best && <span className="text-accent" title="Cao nhất trong 3 phiên"> ▲</span>}</td>
                      <td className="num text-right">{w.avg_abs_return_pct != null ? `${w.avg_abs_return_pct.toFixed(3)}%` : "—"}</td>
                      {!compact && <td className={cn("num text-right", w.avg_return_pct > 0 ? "up" : w.avg_return_pct < 0 ? "down" : "")}>{fpct(w.avg_return_pct, 3)}</td>}
                      <td className={cn("num text-right", w.days < MIN_N && "text-accent")} title={w.days < MIN_N ? "Mẫu ít, độ tin cậy thấp" : undefined}>{w.days}{w.days < MIN_N && " !"}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
          <p className="m-0 text-[11px] text-faint flex gap-1 items-start">
            <Info size={12} className="shrink-0 mt-[2px]" aria-hidden="true" />
            <span>Thống kê quá khứ trên dữ liệu giá đã lưu, không dự báo và không phải khuyến nghị. Biên độ = (cao − thấp) / giá.</span>
          </p>
        </>
      )}
    </div>
  );
}

export default SessionRangesView;
