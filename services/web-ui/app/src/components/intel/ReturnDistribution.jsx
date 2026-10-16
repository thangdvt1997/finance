// Phân phối lợi suất ngày: histogram + đường chuẩn, VaR/ES lịch sử, thống kê & giải thích. Không dự báo.
import { useMemo, useState } from "react";
import { EChart, css } from "../charts";
import { Seg, cn } from "../ui";
import { fnum, useDistribution } from "../../lib/intel";
import { useSymbols } from "../../lib/queries";
import { QState } from "./bits";

const WINDOWS = [60, 120, 250, 500, 1000].map((v) => ({ value: v, label: `${v}` }));
const sp = (v, dp = 2) => (v == null || Number.isNaN(v) ? "—" : `${v > 0 ? "+" : v < 0 ? "−" : ""}${Math.abs(v).toFixed(dp)}%`);

function nearestBin(bins, x) {
  let best = 0, bd = Infinity;
  bins.forEach((b, i) => { const m = (b.x0 + b.x1) / 2; const dd = Math.abs(m - x); if (dd < bd) { bd = dd; best = i; } });
  return best;
}

function skewText(s) {
  if (s == null) return "—";
  if (s <= -0.3) return "Lệch trái: các phiên giảm mạnh xuất hiện nhiều/lớn hơn các phiên tăng mạnh.";
  if (s >= 0.3) return "Lệch phải: các phiên tăng mạnh nổi trội hơn các phiên giảm mạnh.";
  return "Gần đối xứng: phiên tăng và giảm lớn xuất hiện tương đương.";
}
function kurtText(k) {
  if (k == null) return "—";
  if (k >= 1) return "Đuôi dày: biến động cực đoan xảy ra thường xuyên hơn so với phân phối chuẩn.";
  if (k <= -0.5) return "Đuôi mỏng: ít biến động cực đoan hơn phân phối chuẩn.";
  return "Đuôi gần giống phân phối chuẩn.";
}

export function ReturnDistributionView({ symbol: symProp, window: winProp, compact = false, onSymbol, height }) {
  const all = useSymbols();
  const [symLocal, setSymLocal] = useState("US:SPY");
  const [winLocal, setWinLocal] = useState(250);
  const symbol = symProp || symLocal;
  const win = winProp ?? winLocal;
  const q = useDistribution(symbol, win);
  const d = q.data;
  const opts = useMemo(() => {
    const l = (all.data || []).map((s) => ({ v: s.symbol, t: `${s.symbol.replace(/^[A-Za-z]+:/, "")}${s.name ? ` — ${s.name}` : ""}` }));
    if (symbol && !l.some((o) => o.v === symbol)) l.unshift({ v: symbol, t: symbol });
    return l;
  }, [all.data, symbol]);
  const setSym = (s) => { setSymLocal(s); onSymbol?.(s); };

  const bins = d?.bins || [];
  const cats = useMemo(() => bins.map((b) => ((b.x0 + b.x1) / 2).toFixed(2)), [bins]);
  const h = height ?? (compact ? 220 : 300);
  const build = () => {
    const fg = css("--fg"), muted = css("--muted"), line = css("--line2"), panel = css("--panel");
    const acc = css("--accent") || "#f0b84f", dn = css("--down") || "#ff5c7a", info = css("--info") || "#5aa9ff";
    const marks = [];
    if (d?.var95_pct != null && bins.length) marks.push({ xAxis: nearestBin(bins, -Math.abs(d.var95_pct)), lineStyle: { color: dn, type: "dashed", width: 1.5 }, label: { formatter: `VaR95 ${sp(-Math.abs(d.var95_pct))}`, color: dn, fontSize: 10.5, position: "insideEndTop" } });
    if (d?.es95_pct != null && bins.length) marks.push({ xAxis: nearestBin(bins, -Math.abs(d.es95_pct)), lineStyle: { color: dn, type: "solid", width: 1.5 }, label: { formatter: `ES95 ${sp(-Math.abs(d.es95_pct))}`, color: dn, fontSize: 10.5, position: "insideStartTop" } });
    return {
      animation: false,
      grid: { left: 6, right: 12, top: 16, bottom: 4, containLabel: true },
      tooltip: {
        trigger: "axis", axisPointer: { type: "shadow" }, confine: true, backgroundColor: panel, borderColor: line, textStyle: { color: fg, fontSize: 12 },
        formatter: (ps) => {
          const i = ps?.[0]?.dataIndex; const b = bins[i];
          if (!b) return "";
          return `<b>Lợi suất ${sp(b.x0)} … ${sp(b.x1)}</b><br/>${b.n} phiên (thực tế)<br/>${fnum(b.normal, 1)} phiên (nếu phân phối chuẩn)`;
        },
      },
      xAxis: { type: "category", data: cats, name: "Lợi suất ngày (%)", nameLocation: "middle", nameGap: 26, nameTextStyle: { color: muted, fontSize: 11 }, axisLabel: { color: muted, fontSize: 10.5, interval: Math.max(0, Math.round(cats.length / 8) - 1), formatter: (v) => `${Number(v) > 0 ? "+" : ""}${v}` }, axisLine: { lineStyle: { color: line } }, axisTick: { show: false } },
      yAxis: { type: "value", name: "Số phiên", nameTextStyle: { color: muted, fontSize: 11 }, axisLabel: { color: muted, fontSize: 10.5 }, splitLine: { lineStyle: { color: line, opacity: 0.5 } } },
      series: [
        { name: "Thực tế", type: "bar", data: bins.map((b) => b.n), barCategoryGap: "8%", itemStyle: { color: acc, opacity: 0.8 }, markLine: { silent: true, symbol: "none", animation: false, data: marks } },
        { name: "Phân phối chuẩn", type: "line", data: bins.map((b) => b.normal), showSymbol: false, smooth: true, lineStyle: { color: info, width: 1.8 }, z: 3 },
      ],
    };
  };

  const rows = d ? [
    ["Trung bình / phiên", sp(d.mean_pct, 3)],
    ["Độ lệch chuẩn", sp(d.std_pct, 3).replace(/^[+−]/, "")],
    ["Độ lệch (skew)", fnum(d.skew, 2)],
    ["Độ nhọn dư (kurtosis)", fnum(d.kurtosis, 2)],
    ["Thấp nhất", sp(d.min_pct)],
    ["Cao nhất", sp(d.max_pct)],
    ["Phân vị 5%", sp(d.p05_pct)],
    ["Phân vị 95%", sp(d.p95_pct)],
    ["VaR 95% (1 phiên)", sp(-Math.abs(d.var95_pct ?? NaN))],
    ["ES 95% (1 phiên)", sp(-Math.abs(d.es95_pct ?? NaN))],
    ["% phiên tăng", d.positive_pct == null ? "—" : `${fnum(d.positive_pct, 1)}%`],
    ["Số phiên", d.n == null ? "—" : String(d.n)],
  ] : [];

  return (
    <div className={cn("grid gap-3", compact && "tm-pad")}>
      {(!compact || !symProp) && (
        <div className="flex flex-wrap items-center gap-2">
          {!symProp && (
            <>
              <label className="sr-only" htmlFor="dist-sym">Chọn mã</label>
              <select id="dist-sym" className="field max-w-[260px]" value={symbol} onChange={(e) => setSym(e.target.value)}>
                {opts.map((o) => <option key={o.v} value={o.v}>{o.t}</option>)}
              </select>
            </>
          )}
          {winProp == null && <Seg value={win} onChange={setWinLocal} options={WINDOWS} label="Số phiên tính" />}
        </div>
      )}
      <QState q={q} empty="Chưa đủ dữ liệu cho mã này." hint="Cần nến ngày đủ dài; thử mã hoặc cửa sổ ngắn hơn." rows={5} compact={compact} isEmpty={(x) => !x || !x.bins?.length} />
      {d?.bins?.length > 0 && (
        <div className={cn("grid gap-3", !compact && "lg:grid-cols-[minmax(0,1fr)_17rem]")}>
          <div className="min-w-0 grid gap-1">
            {!compact && <div className="text-[12.5px] font-semibold">{d.label || d.symbol} <span className="text-faint font-normal">· {d.name}</span></div>}
            <div className="flex flex-col" style={{ minHeight: h }}>
              <EChart build={build} deps={[d, win]} height={h} label={`Histogram lợi suất ngày ${d.label || symbol}, ${d.n} phiên`} />
            </div>
            <div className="flex flex-wrap gap-x-4 gap-y-1 text-[11px] text-muted" aria-hidden="true">
              <span><i className="inline-block w-[10px] h-[10px] rounded-sm align-middle mr-1" style={{ background: "var(--accent)" }} />Thực tế</span>
              <span><i className="inline-block w-[14px] h-[2px] align-middle mr-1" style={{ background: "var(--info, #5aa9ff)" }} />Phân phối chuẩn</span>
              <span className="text-down">┆ VaR95 / ES95</span>
            </div>
          </div>
          <div className="min-w-0">
            <table className="tbl" aria-label="Thống kê phân phối">
              <tbody>
                {(compact ? rows.filter(([l]) => /VaR|ES|Độ lệch chuẩn|% phiên|Số phiên/.test(l)) : rows).map(([l, v]) => (
                  <tr key={l}><td className="text-muted">{l}</td><td className="r num">{v}</td></tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
      {d?.bins?.length > 0 && !compact && (
        <div className="grid gap-1 text-[12.5px] text-muted max-w-[90ch]">
          <p className="m-0"><b className="text-fg">Độ lệch ({fnum(d.skew, 2)}).</b> {skewText(d.skew)}</p>
          <p className="m-0"><b className="text-fg">Độ nhọn dư ({fnum(d.kurtosis, 2)}).</b> {kurtText(d.kurtosis)}</p>
          <p className="m-0"><b className="text-fg">VaR 95% ≈ {sp(-Math.abs(d.var95_pct ?? NaN))}.</b> Trong lịch sử cửa sổ này, 95% số phiên lỗ không vượt mức đó; <b className="text-fg">ES 95% ≈ {sp(-Math.abs(d.es95_pct ?? NaN))}</b> là mức lỗ trung bình của 5% phiên tệ nhất.</p>
        </div>
      )}
      <p className={cn("m-0 text-[11.5px] text-faint", compact && "px-0")}>{d?.disclaimer || "Thống kê lịch sử, không dự báo tương lai."} Tham khảo, không phải khuyến nghị đầu tư.</p>
    </div>
  );
}

export default ReturnDistributionView;
