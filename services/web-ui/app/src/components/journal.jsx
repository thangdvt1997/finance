// Nhật ký giao dịch: các khối hiển thị thống kê (chỉ-đọc). Số liệu tính ở service journal; ở đây chỉ vẽ.
import { useEffect, useMemo, useRef, useState } from "react";
import { Chip, Panel, Seg, Stat, cn } from "./ui";
import { DataTable } from "./table";
import { EChart, css } from "./charts";
import { dateTime, dur, signCls } from "../lib/format";

// ---------- định dạng ----------
export const fN = (n, dp = 2) => (n == null || Number.isNaN(n) ? "—" : Number(n).toLocaleString("en-US", { minimumFractionDigits: dp, maximumFractionDigits: dp }));
export const fS = (n, dp = 2) => (n == null || Number.isNaN(n) ? "—" : `${n > 0 ? "+" : ""}${fN(n, dp)}`);
export const fP = (n, dp = 1) => (n == null || Number.isNaN(n) ? "—" : `${Number(n).toFixed(dp)}%`);
export const fWR = (n) => (n == null ? "—" : `${(n * 100).toFixed(1)}%`);
export const fR = (n) => (n == null || Number.isNaN(n) ? "—" : `${n > 0 ? "+" : ""}${Number(n).toFixed(2)}R`);
export const fPF = (n) => (n == null ? "—" : fN(n, 2));
export const SIDE = { buy: "Mua", sell: "Bán" };
export const SESSION = { asia: "Á (Asia)", london: "London", london_ny: "London–New York", ny: "New York", late: "Cuối phiên" };
export const RULE_LABEL = {
  news_window: "Vào lệnh trong cửa sổ rủi ro tin (high impact)",
  reentry_after_loss: "Vào lại ngay sau lệnh thua",
  size_up_after_loss: "Tăng khối lượng sau lệnh thua",
  averaging_down: "Nhồi lệnh bình quân giá xấu",
  overtrading_day: "Quá nhiều lệnh trong ngày",
  overtrading_hour: "Quá nhiều lệnh trong 1 giờ",
  no_sl: "Vào lệnh không đặt SL",
};
export const ruleLabel = (r) => RULE_LABEL[r] || r;
const tone = (n) => (n > 0 ? "up" : n < 0 ? "down" : "");
const ms = (t) => new Date(t).getTime();

const axisBase = () => ({
  axisLine: { lineStyle: { color: css("--line2") } },
  axisLabel: { color: css("--muted"), fontSize: 11 },
  splitLine: { lineStyle: { color: css("--line") } },
});
const tipBase = () => ({ backgroundColor: css("--panel2"), borderColor: css("--line2"), textStyle: { color: css("--fg"), fontSize: 12 } });

/** Nhãn/tooltip của tài khoản: MT/Paper + MÔ PHỎNG / FIXTURE. */
export function accountFlags(a) {
  const src = String(a?.source || "");
  const sim = src.startsWith("sim:");
  const fixture = !sim && (/fixture|lab|demo/i.test(src) || /^demo/i.test(a?.account_id || ""));
  return { sim, fixture };
}
export function AccountBadges({ a }) {
  if (!a) return null;
  const { sim, fixture } = accountFlags(a);
  return (
    <>
      <Chip tone={a.kind === "mt" ? "ro" : "accent"} title={a.kind === "mt" ? "Tài khoản MT4/MT5 (EA gửi lịch sử deal), chỉ đọc" : "Tài khoản paper (mô phỏng của hệ thống)"}>{a.kind === "mt" ? "MT" : "Paper"}</Chip>
      {sim && <Chip tone="down" title={"Dữ liệu MÔ PHỎNG để thử giao diện, không phải lệnh thật"}>MÔ PHỎNG</Chip>}
      {fixture && <Chip tone="accent" title={"Dữ liệu FIXTURE phòng lab, không phải lệnh thật"}>FIXTURE</Chip>}
    </>
  );
}

// ---------- KPI ----------
function Kpi({ label, value, sub, cls, title }) {
  return (
    <div className="panel panel-b !py-2.5 min-w-0" title={title}>
      <Stat label={label} value={<span className={cls}>{value}</span>} sub={sub} big />
    </div>
  );
}
export function KpiRow({ s, eq, cur }) {
  const c = cur ? ` ${cur}` : "";
  return (
    <div className="grid gap-2 grid-cols-2 md:grid-cols-4 2xl:grid-cols-8" role="group" aria-label="Chỉ số chính">
      <Kpi label="Net P/L" value={fS(s.net)} cls={tone(s.net)} sub={`Gộp lãi ${fN(s.gross_profit, 0)} · lỗ ${fN(s.gross_loss, 0)}${c}`} />
      <Kpi label="Lệnh đã đóng" value={fN(s.n, 0)} sub={`${s.wins} thắng · ${s.losses} thua · ${s.breakeven} hoà`} />
      <Kpi label="Win rate" value={fWR(s.win_rate)} sub={`Best ${fS(s.best, 0)} · Worst ${fS(s.worst, 0)}`} />
      <Kpi label="Profit factor" value={fPF(s.profit_factor)} title={s.profit_factor == null ? "Không có lệnh lỗ nên PF không xác định" : undefined} sub={s.profit_factor == null ? "chưa có lệnh lỗ" : "lãi gộp / lỗ gộp"} />
      <Kpi label="Expectancy" value={fS(s.expectancy)} cls={tone(s.expectancy)} sub="kỳ vọng / lệnh" />
      <Kpi label="Avg win / loss" value={<>{fN(s.avg_win, 1)} <span className="text-faint">/</span> {fN(s.avg_loss, 1)}</>} sub={`payoff ${fPF(s.payoff)}`} />
      <Kpi label="Max drawdown" value={fN(eq?.max_dd)} cls={eq?.max_dd > 0 ? "down" : ""} sub={eq?.max_dd_pct != null ? `${fP(eq.max_dd_pct, 2)} · hiện tại ${fN(eq.current_dd)}` : `hiện tại ${fN(eq?.current_dd)} · % cần số dư gốc`} />
      <Kpi label="R trung bình" value={s.avg_r == null ? "—" : fR(s.avg_r)} cls={tone(s.avg_r)} sub={s.n_r ? `${s.n_r} lệnh có SL` : "không có lệnh có SL"} />
    </div>
  );
}

// ---------- vốn + drawdown ----------
export function EquityPanel({ eq, cur }) {
  const pts = eq?.points || [];
  const build = () => {
    const eqd = pts.map((p) => [ms(p.t), p.equity]);
    const bal = pts.filter((p) => p.kind === "balance").map((p) => [ms(p.t), p.equity]);
    const dd = pts.map((p) => [ms(p.t), -Math.abs(p.dd || 0)]);
    return {
      animation: false, backgroundColor: "transparent",
      axisPointer: { link: [{ xAxisIndex: "all" }] },
      grid: [{ left: 62, right: 14, top: 12, height: "58%" }, { left: 62, right: 14, top: "74%", bottom: 24 }],
      tooltip: {
        trigger: "axis", ...tipBase(),
        formatter: (a) => {
          const i = a[0]?.dataIndex;
          const p = pts[i];
          if (!p) return "";
          const lines = [`${dateTime(p.t)} · lệnh #${p.ticket ?? "—"}`];
          lines.push(`Vốn: <b>${fN(p.equity)}</b>${cur ? " " + cur : ""}`);
          lines.push(`Drawdown: <b class="down">-${fN(p.dd)}</b>${p.dd_pct != null ? ` (${fP(p.dd_pct, 2)})` : ""}`);
          if (p.kind === "balance") lines.push("<b>Nạp/rút (balance)</b>");
          return lines.join("<br/>");
        },
      },
      xAxis: [
        { type: "time", gridIndex: 0, ...axisBase(), axisLabel: { show: false }, splitLine: { show: false } },
        { type: "time", gridIndex: 1, ...axisBase() },
      ],
      yAxis: [
        { type: "value", gridIndex: 0, scale: true, ...axisBase() },
        { type: "value", gridIndex: 1, max: 0, ...axisBase(), splitNumber: 2 },
      ],
      dataZoom: [{ type: "inside", xAxisIndex: [0, 1] }],
      series: [
        { name: "Vốn", type: "line", xAxisIndex: 0, yAxisIndex: 0, showSymbol: false, data: eqd, lineStyle: { color: css("--accent"), width: 1.8 }, areaStyle: { color: css("--accent"), opacity: 0.07 } },
        { name: "Nạp/rút", type: "scatter", xAxisIndex: 0, yAxisIndex: 0, data: bal, symbol: "diamond", symbolSize: 11, itemStyle: { color: css("--info") }, tooltip: { show: false } },
        { name: "Drawdown", type: "line", xAxisIndex: 1, yAxisIndex: 1, showSymbol: false, data: dd, lineStyle: { color: css("--down"), width: 1.2 }, areaStyle: { color: css("--down"), opacity: 0.2 } },
      ],
    };
  };
  const nb = pts.filter((p) => p.kind === "balance").length;
  return (
    <Panel title="Đường vốn và drawdown" right={<>{nb > 0 && <Chip tone="ro" title="Điểm nạp/rút (balance) hiện bằng hình thoi xanh">{nb} nạp/rút</Chip>}<span className="text-[11.5px] text-faint num">{eq?.base ? `vốn gốc ${fN(eq.base, 0)}` : "chưa biết vốn gốc"}</span></>} className="min-h-[340px]" bodyClass="flex flex-col">
      {pts.length < 2 ? <div className="text-muted py-6">Chưa đủ điểm để vẽ đường vốn (cần ít nhất 2 lệnh đã đóng).</div>
        : <EChart build={build} deps={[eq]} height={300} label="Đường vốn theo lệnh đã đóng và drawdown" />}
    </Panel>
  );
}

// ---------- lịch heatmap ----------
const dayMs = 86400000;
const keyOf = (d) => new Date(d).toISOString().slice(0, 10);
const parseKey = (k) => Date.UTC(+k.slice(0, 4), +k.slice(5, 7) - 1, +k.slice(8, 10));
const MON = ["T1", "T2", "T3", "T4", "T5", "T6", "T7", "T8", "T9", "T10", "T11", "T12"];
const DOW = ["T2", "T3", "T4", "T5", "T6", "T7", "CN"];

export function CalendarHeat({ calendar, picked, onPick, cur }) {
  const [hov, setHov] = useState(null);
  const scroller = useRef(null);
  const { weeks, max, byKey } = useMemo(() => {
    const byKey = new Map((calendar || []).map((d) => [d.date, d]));
    if (!calendar?.length) return { weeks: [], max: 0, byKey };
    const keys = calendar.map((d) => d.date).sort();
    const first = parseKey(keys[0]);
    const last = parseKey(keys[keys.length - 1]);
    const start = first - ((new Date(first).getUTCDay() + 6) % 7) * dayMs; // về thứ Hai
    const weeks = [];
    for (let w = start; w <= last; w += 7 * dayMs) weeks.push(Array.from({ length: 7 }, (_, i) => { const t = w + i * dayMs; return t < first || t > last ? null : keyOf(t); }));
    const max = Math.max(1e-9, ...calendar.map((d) => Math.abs(d.net)));
    return { weeks, max, byKey };
  }, [calendar]);
  useEffect(() => { if (scroller.current) scroller.current.scrollLeft = scroller.current.scrollWidth; }, [weeks.length]);
  const cell = (k) => {
    const d = byKey.get(k);
    if (!d) return { background: "transparent", border: "1px dashed var(--line)" };
    const a = 0.18 + 0.72 * Math.min(1, Math.abs(d.net) / max);
    const c = d.net > 0 ? "var(--up)" : d.net < 0 ? "var(--down)" : "var(--faint)";
    return { background: `color-mix(in srgb, ${c} ${Math.round(a * 100)}%, var(--panel))`, border: picked === k ? "2px solid var(--accent)" : "1px solid transparent" };
  };
  const monthAt = (w) => { const k = w.find(Boolean); return k && (k.slice(8) <= "07" || w === weeks[0]) ? MON[+k.slice(5, 7) - 1] + (k.slice(5, 7) === "01" ? ` ${k.slice(0, 4)}` : "") : ""; };
  const info = hov ? byKey.get(hov) : null;
  return (
    <Panel title="Lịch lãi/lỗ theo ngày" right={picked ? <button className="btn" onClick={() => onPick(null)}>Bỏ lọc ngày {picked}</button> : <span className="text-[11.5px] text-faint">bấm một ô để lọc bảng lệnh theo ngày</span>}>
      {!weeks.length ? <div className="text-muted">Chưa có ngày nào có lệnh trong khoảng này.</div> : (
        <>
          <div ref={scroller} className="scroll-x pb-1">
            <div className="inline-flex gap-[3px]" role="grid" aria-label="Lịch lãi lỗ theo ngày, cột là tuần, hàng là thứ">
              <div className="flex flex-col gap-[3px] pt-[16px] pr-1 text-[10px] text-faint" aria-hidden="true">
                {DOW.map((d) => <div key={d} className="h-[18px] leading-[18px]">{d}</div>)}
              </div>
              {weeks.map((w, wi) => (
                <div key={wi} className="flex flex-col gap-[3px]" role="row">
                  <div className="h-[13px] text-[10px] text-faint leading-[13px] whitespace-nowrap overflow-visible w-[18px]" aria-hidden="true">{monthAt(w)}</div>
                  {w.map((k, di) => k ? (
                    <button key={k} type="button" role="gridcell" onClick={() => onPick(picked === k ? null : k)} onMouseEnter={() => setHov(k)} onFocus={() => setHov(k)} onMouseLeave={() => setHov(null)}
                      className="w-[18px] h-[18px] rounded-[3px] p-0 cursor-pointer" style={cell(k)}
                      aria-selected={picked === k}
                      aria-label={byKey.get(k) ? `${k}: ${byKey.get(k).n} lệnh, ${byKey.get(k).wins} thắng, ${byKey.get(k).losses} thua, net ${fS(byKey.get(k).net)}` : `${k}: không có lệnh`} />
                  ) : <div key={di} className="w-[18px] h-[18px]" />)}
                </div>
              ))}
            </div>
          </div>
          <div className="mt-2 min-h-[2.4rem] text-[12.5px]" aria-live="polite">
            {info ? <span><b className="num">{info.date}</b> · {info.n} lệnh · <span className="up">{info.wins} thắng</span> · <span className="down">{info.losses} thua</span> · net <b className={cn("num", signCls(info.net))}>{fS(info.net)}{cur ? " " + cur : ""}</b></span>
              : <span className="text-faint">Rê chuột hoặc Tab vào một ô để xem chi tiết. Xanh = lãi, đỏ = lỗ, đậm theo |net| (tối đa {fN(max, 0)}).</span>}
          </div>
        </>
      )}
    </Panel>
  );
}

// ---------- phân bố R ----------
export function RPanel({ r }) {
  const bins = r?.bins || [];
  const build = () => ({
    animation: false, backgroundColor: "transparent", grid: { left: 40, right: 10, top: 10, bottom: 38 },
    tooltip: { trigger: "axis", ...tipBase(), formatter: (a) => `${a[0].name}: <b>${a[0].value}</b> lệnh` },
    xAxis: { type: "category", data: bins.map((b) => b.label), ...axisBase(), axisLabel: { color: css("--muted"), fontSize: 10, interval: 0, rotate: bins.length > 8 ? 35 : 0 } },
    yAxis: { type: "value", minInterval: 1, ...axisBase() },
    series: [{ type: "bar", data: bins.map((b) => ({ value: b.n, itemStyle: { color: /^(<|-)/.test(b.label) ? css("--down") : css("--up"), opacity: 0.85 } })), barMaxWidth: 34 }],
  });
  return (
    <Panel title="Phân bố R-multiple" right={r?.pct_with_sl != null ? <Chip title="Tỷ lệ lệnh có đặt SL lúc vào (R chỉ tính được cho các lệnh này)">{fP(r.pct_with_sl, 0)} lệnh có SL</Chip> : null} bodyClass="flex flex-col">
      {!r?.n ? <div className="text-muted py-4">Không có lệnh nào đặt SL nên chưa tính được R. Hãy đặt SL lúc vào để đo R-multiple.</div> : (
        <>
          <div className="flex flex-wrap gap-x-5 gap-y-1 mb-2 text-[12.5px]">
            <span>Trung bình <b className="num">{fR(r.avg)}</b></span><span>Trung vị <b className="num">{fR(r.median)}</b></span><span>Expectancy <b className="num">{fR(r.expectancy_r)}</b></span><span className="text-faint">{r.n} lệnh</span>
          </div>
          <EChart build={build} deps={[r]} height={200} label="Histogram R-multiple" />
        </>
      )}
    </Panel>
  );
}

// ---------- nhóm: giờ / thứ / phiên / symbol / hướng / EA ----------
export const DIMS = [
  { id: "hour", label: "Giờ vào" }, { id: "weekday", label: "Thứ" }, { id: "session", label: "Phiên" },
  { id: "symbol", label: "Symbol" }, { id: "side", label: "Hướng" }, { id: "magic", label: "EA / magic" },
];
const dimLabel = (dim, r) => r.label ?? (dim === "hour" ? `${String(r.key).padStart(2, "0")}h` : dim === "session" ? SESSION[r.key] || r.key : dim === "side" ? SIDE[r.key] || r.key : dim === "magic" && r.key === "manual" ? "Thủ công" : String(r.key));

export function GroupPanel({ groups, dim, setDim }) {
  const rows = groups?.[dim] || [];
  const named = rows.map((r) => ({ ...r, name: dimLabel(dim, r) }));
  const build = () => ({
    animation: false, backgroundColor: "transparent", grid: { left: 54, right: 10, top: 10, bottom: dim === "hour" || named.length > 8 ? 44 : 28 },
    tooltip: { trigger: "axis", ...tipBase(), formatter: (a) => { const r = named[a[0].dataIndex]; return `<b>${r.name}</b><br/>${r.n} lệnh · WR ${fWR(r.win_rate)}<br/>Net <b>${fS(r.net)}</b> · PF ${fPF(r.profit_factor)}`; } },
    xAxis: { type: "category", data: named.map((r) => r.name), ...axisBase(), axisLabel: { color: css("--muted"), fontSize: 10.5, interval: 0, rotate: named.length > 8 ? 40 : 0 } },
    yAxis: { type: "value", ...axisBase() },
    series: [{ type: "bar", data: named.map((r) => ({ value: r.net, itemStyle: { color: r.net >= 0 ? css("--up") : css("--down"), opacity: 0.85 } })), barMaxWidth: 30 }],
  });
  const cols = useMemo(() => [
    { id: "name", header: "Nhóm", accessorKey: "name", cell: (c) => <b>{c.getValue()}</b> },
    { id: "n", header: "Lệnh", accessorKey: "n", meta: { align: "r" }, cell: (c) => <span className="num">{c.getValue()}</span> },
    { id: "net", header: "Net", accessorKey: "net", meta: { align: "r" }, cell: (c) => <span className={cn("num", signCls(c.getValue()))}>{fS(c.getValue())}</span> },
    { id: "wr", header: "WR", accessorKey: "win_rate", meta: { align: "r" }, cell: (c) => <span className="num">{fWR(c.getValue())}</span> },
    { id: "pf", header: "PF", accessorKey: "profit_factor", meta: { align: "r" }, cell: (c) => <span className="num">{fPF(c.getValue())}</span> },
    { id: "exp", header: "Expectancy", accessorKey: "expectancy", meta: { align: "r" }, cell: (c) => <span className={cn("num", signCls(c.getValue()))}>{fS(c.getValue())}</span> },
    { id: "r", header: "R TB", accessorKey: "avg_r", meta: { align: "r" }, cell: (c) => <span className="num">{c.getValue() == null ? "—" : fR(c.getValue())}</span> },
  ], []);
  return (
    <Panel title="Thống kê theo nhóm" right={<Seg value={dim} onChange={setDim} options={DIMS.map((d) => ({ value: d.id, label: d.label }))} label="Chiều thống kê" />} bodyClass="flex flex-col gap-3">
      {!named.length ? <div className="text-muted">Chưa có dữ liệu cho chiều này.</div> : (
        <>
          <EChart build={build} deps={[groups, dim]} height={190} label={`Net theo ${DIMS.find((d) => d.id === dim)?.label}`} />
          <DataTable data={named} columns={cols} minWidth={460} initialSort={dim === "hour" || dim === "weekday" ? [] : [{ id: "net", desc: true }]} />
        </>
      )}
    </Panel>
  );
}

// ---------- đóng góp EA ----------
export function ContributionPanel({ rows }) {
  const cols = useMemo(() => [
    { id: "ea", header: "EA / chiến lược", accessorKey: "ea", cell: (c) => <b>{c.getValue() === "manual" ? "Thủ công" : c.getValue()}</b> },
    { id: "n", header: "Lệnh", accessorKey: "n", meta: { align: "r" }, cell: (c) => <span className="num">{c.getValue()}</span> },
    { id: "net", header: "Net", accessorKey: "net", meta: { align: "r" }, cell: (c) => <span className={cn("num", signCls(c.getValue()))}>{fS(c.getValue())}</span> },
    { id: "wr", header: "WR", accessorKey: "win_rate", meta: { align: "r" }, cell: (c) => <span className="num">{fWR(c.getValue())}</span> },
    { id: "pf", header: "PF", accessorKey: "profit_factor", meta: { align: "r" }, cell: (c) => <span className="num">{fPF(c.getValue())}</span> },
    { id: "exp", header: "Expectancy", accessorKey: "expectancy", meta: { align: "r" }, cell: (c) => <span className="num">{fS(c.getValue())}</span> },
    { id: "share", header: "Đóng góp", accessorKey: "share_pct", meta: { align: "r" }, cell: (c) => { const r = c.row.original; return <span className="num" title={`Tỷ trọng theo |net|: ${fP(r.abs_share_pct)}`}>{c.getValue() == null ? `${fP(r.abs_share_pct, 0)} |net|` : fP(c.getValue())}</span>; } },
  ], []);
  return (
    <Panel title="Đóng góp theo EA / chiến lược" right={<span className="text-[11.5px] text-faint">đóng góp = tỷ trọng net trong tổng net; để trống khi tổng net quá nhỏ</span>}>
      <DataTable data={rows || []} columns={cols} minWidth={560} initialSort={[{ id: "net", desc: true }]} empty="Chưa có dữ liệu EA/magic." />
    </Panel>
  );
}

// ---------- chuỗi, thời gian giữ, chi phí ----------
export function MiscPanel({ s, streaks, hold, costs, cur }) {
  const bk = hold?.buckets || [];
  const mx = Math.max(1, ...bk.map((b) => b.n));
  return (
    <Panel title="Chuỗi · thời gian giữ · chi phí" bodyClass="grid gap-4 md:grid-cols-3">
      <div className="grid gap-2 content-start">
        <h3 className="m-0 text-[12px] text-muted font-semibold">Chuỗi thắng/thua</h3>
        <Stat label="Chuỗi thắng dài nhất" value={`${streaks?.max_win_streak ?? 0} lệnh`} tone="up" />
        <Stat label="Chuỗi thua dài nhất" value={`${streaks?.max_loss_streak ?? 0} lệnh`} tone="down" sub={streaks?.worst_loss_run != null ? `tổng lỗ chuỗi xấu nhất ${fS(streaks.worst_loss_run)}` : undefined} />
        <Stat label="Chuỗi hiện tại" value={streaks?.current?.len ? `${streaks.current.len} ${streaks.current.type === "win" ? "thắng" : streaks.current.type === "loss" ? "thua" : streaks.current.type}` : "—"} />
      </div>
      <div className="grid gap-2 content-start">
        <h3 className="m-0 text-[12px] text-muted font-semibold">Thời gian giữ lệnh</h3>
        <div className="grid grid-cols-2 gap-2">
          <Stat label="Trung bình" value={dur(hold?.avg_s)} /><Stat label="Trung vị" value={dur(hold?.median_s)} />
          <Stat label="TB lệnh thắng" value={dur(hold?.avg_win_s)} tone="up" /><Stat label="TB lệnh thua" value={dur(hold?.avg_loss_s)} tone="down" />
        </div>
        <div className="grid gap-1" role="list" aria-label="Phân bố thời gian giữ">
          {bk.map((b) => (
            <div key={b.bucket} role="listitem" className="grid grid-cols-[5.5rem_1fr_auto] items-center gap-2 text-[11.5px]" title={`${b.bucket}: ${b.n} lệnh, net ${fS(b.net)}`}>
              <span className="text-muted truncate">{b.bucket}</span>
              <span className="h-2 rounded bg-panel2 overflow-hidden"><span className="block h-full" style={{ width: `${(b.n / mx) * 100}%`, background: b.net >= 0 ? "var(--up)" : "var(--down)", opacity: 0.8 }} /></span>
              <span className="num text-faint">{b.n} · <span className={signCls(b.net)}>{fS(b.net, 0)}</span></span>
            </div>
          ))}
        </div>
      </div>
      <div className="grid gap-2 content-start">
        <h3 className="m-0 text-[12px] text-muted font-semibold">Chi phí</h3>
        <div className="grid grid-cols-2 gap-2">
          <Stat label="Commission" value={fS(costs?.commission)} /><Stat label="Swap" value={fS(costs?.swap)} />
          <Stat label="Lãi gộp trước phí" value={fN(costs?.gross_profit_before_costs, 0)} />
          <Stat label="Phí / lãi gộp" value={costs?.costs_pct_of_gross == null ? "—" : fP(costs.costs_pct_of_gross)} />
        </div>
        {(costs?.spread_cost != null || costs?.slippage_cost != null) && <div className="text-[12px] text-muted">Spread ước tính {fN(costs.spread_cost)} · trượt giá {fN(costs.slippage_cost)} {cur}</div>}
        {costs?.note && <div className="text-[11.5px] text-faint">{costs.note}</div>}
      </div>
    </Panel>
  );
}
