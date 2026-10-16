import { useState } from "react";
import { useQuery, keepPreviousData } from "@tanstack/react-query";
import { BadgeCheck, Fingerprint, Gauge, Receipt, ScrollText, TrendingDown } from "lucide-react";
import { Async, Chip, Panel, Seg, Stat, cn } from "../components/ui";
import { EChart, css } from "../components/charts";
import { api } from "../lib/api";
import { date, dateTime, signCls } from "../lib/format";

/* Panel "Chất lượng & quản trị" của trang Mô phỏng: hiệu suất có CI, TCA, giám sát suy giảm, strategy card + giai đoạn, hash-chain.
   MỌI số liệu là MÔ PHỎNG; mẫu forward test còn rất ngắn nên chỉ số điểm chưa có ý nghĩa thống kê. */

const useQ = (path, opts = {}) =>
  useQuery({ queryKey: ["paper", path], queryFn: ({ signal }) => api(`/paper${path}`, {}, signal), staleTime: 30_000, refetchInterval: 120_000, placeholderData: keepPreviousData, ...opts });

const P = (x, dp = 1) => (x == null || Number.isNaN(x) ? "—" : `${x > 0 ? "+" : ""}${(x * 100).toFixed(dp)}%`);
const P0 = (x, dp = 1) => (x == null || Number.isNaN(x) ? "—" : `${(x * 100).toFixed(dp)}%`);
const N = (x, dp = 2) => (x == null || Number.isNaN(x) ? "—" : Number(x).toFixed(dp));
const ci = (c, f) => (c ? `[${f(c[0])} … ${f(c[1])}]` : "—");
const short = (h) => (h ? `${h.slice(0, 10)}…` : "—");

const STAGE_TONE = { review_ready: "up", paper_early: "accent", paper_hold: "accent", suspended: "down", pipeline_test: "", retired: "", no_card: "" };
const LIGHT = { green: ["up", "XANH — chưa thấy lệch"], yellow: ["accent", "VÀNG — theo dõi"], red: ["down", "ĐỎ — rà soát"], insufficient: ["", "chưa đủ mẫu"], "n/a": ["", "không áp dụng"] };
const DIAG = { none: "chưa lệch bất thường", signal: "suy giảm TÍN HIỆU", execution: "suy giảm THỰC THI", both: "suy giảm CẢ HAI", insufficient: "chưa đủ mẫu", "n/a": "không có kỳ vọng backtest cùng tham số" };

function Light({ s }) {
  const [tone, label] = LIGHT[s] || ["", s || "—"];
  return <Chip tone={tone}>{label}</Chip>;
}

/* ------------------------------------------------------------------------------------------ dải tổng quan */
function Overview({ id }) {
  const card = useQ(`/accounts/${id}/card`);
  const drift = useQ(`/accounts/${id}/drift`);
  const ver = useQ(`/accounts/${id}/verify`);
  return (
    <Async q={card} rows={2}>
      {(c) => {
        const ev = c.evaluation || {}, pr = ev.progress || {}, d = drift.data, v = ver.data, cf = c.config || {};
        return (
          <div className="grid gap-3 grid-cols-[repeat(auto-fit,minmax(14rem,1fr))]">
            <div className="flex flex-col gap-1 min-w-0">
              <span className="text-[11.5px] text-muted">Giai đoạn chiến lược (tự tính)</span>
              <span><Chip tone={STAGE_TONE[ev.stage]} className="text-[12px]">{ev.stage_label}</Chip></span>
              {pr.pct != null && (
                <div className="mt-1">
                  <div className="h-[6px] rounded bg-panel2 border border-line overflow-hidden" role="progressbar" aria-valuemin={0} aria-valuemax={100}
                    aria-valuenow={Math.round(pr.pct * 100)} aria-label="Tiến độ thời gian tối thiểu của giai đoạn paper">
                    <div style={{ width: `${pr.pct * 100}%`, background: "var(--accent)", height: "100%" }} />
                  </div>
                  <span className="text-[11.5px] text-muted num">{N(pr.weeks, 1)} / {pr.weeks_required} tuần · {pr.days} / {pr.days_required} ngày</span>
                </div>
              )}
            </div>
            <div className="flex flex-col gap-1 min-w-0">
              <span className="text-[11.5px] text-muted">Giám sát suy giảm vs backtest</span>
              <span><Light s={d?.status} /></span>
              <span className="text-[11.5px] text-muted">{d ? DIAG[d.diagnosis] || d.diagnosis : "…"}{d?.n_days != null ? ` · ${d.n_days} ngày` : ""}</span>
            </div>
            <div className="flex flex-col gap-1 min-w-0">
              <span className="text-[11.5px] text-muted">Hash-chain journal</span>
              <span>{v ? <Chip tone={v.ok === false ? "down" : v.ok ? "up" : ""}>{v.ok === false ? "ĐỨT / BỊ SỬA" : v.ok ? "NGUYÊN VẸN" : "chưa có chuỗi"}</Chip> : "…"}</span>
              <span className="text-[11.5px] text-muted num" title={v?.head?.hash}>{v ? `${v.entries} bản ghi · đầu chuỗi ${short(v.head?.hash)}` : ""}</span>
            </div>
            <div className="flex flex-col gap-1 min-w-0">
              <span className="text-[11.5px] text-muted">Cấu hình bất biến</span>
              <span><Chip tone="ro">phiên bản v{cf.version ?? "?"}</Chip></span>
              <span className="text-[11.5px] text-muted num" title={cf.config_hash}>hash {short(cf.config_hash)} · tham số {short(cf.params_hash)}</span>
            </div>
          </div>
        );
      }}
    </Async>
  );
}

/* ------------------------------------------------------------------------------------------ hiệu suất CI */
const METRIC_ROWS = [["cagr", "CAGR", P], ["vol", "Biến động năm", P0], ["sharpe", "Sharpe", N], ["sortino", "Sortino", N], ["calmar", "Calmar", N], ["max_dd", "Max drawdown", P], ["hit_rate", "% ngày lãi", P0]];

function PerfTab({ id }) {
  const q = useQ(`/accounts/${id}/performance`);
  return (
    <Async q={q} rows={6}>
      {(p) => {
        const m = p.metrics || {}, ref = p.backtest_reference, bms = Object.entries(p.benchmarks || {});
        const btMap = ref ? { sharpe: [ref.sharpe, ref.sharpe_ci95], vol: [ref.vol_ann], cagr: [ref.cagr], max_dd: [ref.max_dd] } : {};
        const f = Object.fromEntries(METRIC_ROWS.map(([k, , fn]) => [k, fn]));
        return (
          <div className="flex flex-col gap-4">
            <p className="m-0 text-[12.5px] text-muted">
              {p.ci_note || "CI 95% bằng stationary bootstrap (hạt giống cố định)."} <b className="text-accent">{p.days} ngày lợi suất</b>
              {p.ci_method ? ` · ${p.ci_method.B} mẫu bootstrap, khối TB ${p.ci_method.mean_block}` : ""}
            </p>
            <div className="scroll-x"><table className="tbl" style={{ minWidth: 520 }}>
              <thead><tr><th>Chỉ số</th><th className="r">Giá trị</th><th className="r">CI 95%</th><th className="r">Backtest 1990-2026</th></tr></thead>
              <tbody>
                {METRIC_ROWS.map(([k, label, fn]) => (
                  <tr key={k}>
                    <td>{label}</td><td className="r num">{fn(m[k]?.value)}</td><td className="r num text-muted">{ci(m[k]?.ci95, fn)}</td>
                    <td className="r num text-faint">{btMap[k] ? `${f[k](btMap[k][0])}${btMap[k][1] ? " " + ci(btMap[k][1], f[k]) : ""}` : "—"}</td>
                  </tr>))}
              </tbody></table></div>
            {bms.length > 0 && (
              <div>
                <div className="text-[11.5px] text-muted mb-1">So với benchmark (alpha/beta: OLS, CI xấp xỉ)</div>
                <div className="scroll-x"><table className="tbl" style={{ minWidth: 640 }}>
                  <thead><tr><th>Benchmark</th><th className="r">Vượt trội</th><th className="r">Alpha năm</th><th className="r">Beta</th><th className="r">Tương quan</th><th className="r">IR</th><th className="r">Up/Down capture</th></tr></thead>
                  <tbody>{bms.map(([b, c]) => (
                    <tr key={b}><td><b>{b}</b> <span className="text-faint">({c.n} ngày)</span></td>
                      <td className={cn("r num", signCls(c.excess_total_return))}>{P(c.excess_total_return, 2)}</td>
                      <td className="r num" title={c.alpha_ci ? `CI ${ci(c.alpha_ci, P)}` : c.note}>{c.alpha_ann == null ? "—" : P(c.alpha_ann)}</td>
                      <td className="r num">{N(c.beta)}</td><td className="r num">{N(c.correlation)}</td><td className="r num">{N(c.information_ratio)}</td>
                      <td className="r num">{N(c.up_capture)} / {N(c.down_capture)}</td></tr>))}</tbody></table></div>
              </div>
            )}
            <RollingChart p={p} />
            <div className="grid gap-4 lg:grid-cols-2">
              <Attribution a={p.attribution} />
              <Leverage l={p.leverage} />
            </div>
          </div>
        );
      }}
    </Async>
  );
}

function RollingChart({ p }) {
  const pts = p.rolling?.points || [];
  if (!pts.length) return <p className="m-0 text-[12px] text-faint">Rolling Sharpe/DD (30 và 90 ngày) xuất hiện khi đủ {Math.min(...(p.rolling?.windows?.length ? p.rolling.windows : [30]))} ngày dữ liệu.</p>;
  const build = () => {
    const axis = { axisLine: { lineStyle: { color: css("--line2") } }, axisLabel: { color: css("--muted"), fontSize: 11 }, splitLine: { lineStyle: { color: css("--line") } } };
    const t = (r) => new Date(r.ts).getTime();
    const wins = p.rolling.windows;
    return {
      animation: false, backgroundColor: "transparent", legend: { top: 0, textStyle: { color: css("--muted"), fontSize: 11 } },
      grid: [{ left: 48, right: 12, top: 26, height: "42%" }, { left: 48, right: 12, top: "64%", bottom: 22 }],
      tooltip: { trigger: "axis", backgroundColor: css("--panel2"), borderColor: css("--line2"), textStyle: { color: css("--fg"), fontSize: 12 } },
      xAxis: [{ type: "time", gridIndex: 0, ...axis, axisLabel: { show: false } }, { type: "time", gridIndex: 1, ...axis, axisLabel: { ...axis.axisLabel, formatter: (v) => date(v) } }],
      yAxis: [{ type: "value", gridIndex: 0, ...axis, scale: true }, { type: "value", gridIndex: 1, ...axis, max: 0, axisLabel: { ...axis.axisLabel, formatter: (v) => `${(v * 100).toFixed(0)}%` } }],
      series: [
        ...wins.flatMap((w, i) => [
          { name: `Sharpe ${w}n`, type: "line", xAxisIndex: 0, yAxisIndex: 0, showSymbol: false, data: pts.filter((r) => r[`sharpe${w}`] != null).map((r) => [t(r), r[`sharpe${w}`]]), lineWidth: 1.6, lineStyle: { color: css(i ? "--info" : "--accent") }, itemStyle: { color: css(i ? "--info" : "--accent") } },
          ...(i === wins.length - 1 ? [{ name: `CI95 ${w}n (trên)`, type: "line", xAxisIndex: 0, yAxisIndex: 0, showSymbol: false, data: pts.filter((r) => r[`sharpe${w}_hi`] != null).map((r) => [t(r), r[`sharpe${w}_hi`]]), lineStyle: { type: "dotted", width: 1, color: css("--faint") }, itemStyle: { color: css("--faint") } },
            { name: `CI95 ${w}n (dưới)`, type: "line", xAxisIndex: 0, yAxisIndex: 0, showSymbol: false, data: pts.filter((r) => r[`sharpe${w}_lo`] != null).map((r) => [t(r), r[`sharpe${w}_lo`]]), lineStyle: { type: "dotted", width: 1, color: css("--faint") }, itemStyle: { color: css("--faint") } }] : []),
        ]),
        ...wins.map((w, i) => ({ name: `DD ${w}n`, type: "line", xAxisIndex: 1, yAxisIndex: 1, showSymbol: false, data: pts.filter((r) => r[`dd${w}`] != null).map((r) => [t(r), r[`dd${w}`]]), lineStyle: { width: 1.2, color: css(i ? "--down" : "--accent") }, itemStyle: { color: css(i ? "--down" : "--accent") } })),
      ],
    };
  };
  return <div><div className="text-[11.5px] text-muted mb-1">Rolling Sharpe (dải chấm = CI95 giải tích, Lo 2002) và drawdown trong cửa sổ</div>
    <EChart build={build} deps={[p]} height={260} label="Rolling Sharpe và rolling drawdown của tài khoản mô phỏng" /></div>;
}

function Attribution({ a }) {
  if (!a) return null;
  const rows = a.classes || [];
  const mx = Math.max(1e-9, ...rows.map((r) => Math.abs(r.pnl)));
  return (
    <div>
      <div className="text-[11.5px] text-muted mb-1">Đóng góp lãi/lỗ theo lớp tài sản ({a.ccy}) — đã chốt + chưa chốt − phí/thuế</div>
      {rows.length === 0 ? <div className="text-muted text-[12.5px]">Chưa có giao dịch.</div> : (
        <ul className="m-0 p-0 list-none grid gap-[6px]">
          {rows.map((r) => (
            <li key={r.class} className="grid grid-cols-[4.5rem_1fr_auto] gap-2 items-center text-[12.5px]">
              <span className="text-muted">{r.class}</span>
              <div className="h-[8px] rounded bg-panel2 border border-line relative overflow-hidden" aria-hidden="true">
                <div style={{ position: "absolute", left: r.pnl >= 0 ? "50%" : `${50 - (Math.abs(r.pnl) / mx) * 50}%`, width: `${(Math.abs(r.pnl) / mx) * 50}%`, top: 0, bottom: 0, background: r.pnl >= 0 ? "var(--up)" : "var(--down)" }} />
              </div>
              <span className={cn("num", signCls(r.pnl))}>{r.pnl.toFixed(2)} <span className="text-faint">({P(r.pct_initial, 2)})</span></span>
            </li>))}
        </ul>)}
      <div className="text-[11.5px] text-faint mt-1 num">swap/funding {a.swap_funding?.toFixed(2)} · chênh sổ (phải ≈ 0) {a.unreconciled?.toFixed(2)}</div>
    </div>
  );
}

function Leverage({ l }) {
  const s = l?.series || [];
  if (!s.length) return null;
  const build = () => {
    const axis = { axisLine: { lineStyle: { color: css("--line2") } }, axisLabel: { color: css("--muted"), fontSize: 11 }, splitLine: { lineStyle: { color: css("--line") } } };
    return { animation: false, backgroundColor: "transparent", grid: { left: 40, right: 8, top: 10, bottom: 22 }, tooltip: { trigger: "axis", backgroundColor: css("--panel2"), borderColor: css("--line2"), textStyle: { color: css("--fg"), fontSize: 12 } },
      xAxis: { type: "time", ...axis, axisLabel: { ...axis.axisLabel, formatter: (v) => date(v) } }, yAxis: { type: "value", ...axis, axisLabel: { ...axis.axisLabel, formatter: (v) => `${v.toFixed(1)}×` } },
      series: [{ name: "Đòn bẩy gộp", type: "line", showSymbol: s.length < 40, data: s.map((r) => [new Date(r.ts).getTime(), r.gross]), lineStyle: { color: css("--accent"), width: 1.8 } },
               { name: "Net", type: "line", showSymbol: false, data: s.map((r) => [new Date(r.ts).getTime(), r.net]), lineStyle: { color: css("--info"), width: 1.2, type: "dashed" } }] };
  };
  return <div><div className="text-[11.5px] text-muted mb-1">Đòn bẩy theo thời gian — hiện {N(l.current_gross)}× (TB {N(l.mean_gross)}×, tối đa {N(l.max_gross)}×)</div>
    <EChart build={build} deps={[l]} height={150} label="Đòn bẩy gộp và net theo thời gian" /></div>;
}

/* ------------------------------------------------------------------------------------------ TCA */
function TcaTab({ id, ccy }) {
  const q = useQ(`/accounts/${id}/tca`);
  return (
    <Async q={q} rows={5}>
      {(t) => {
        const o = t.overall, c = t.costs_cum || {};
        return (
          <div className="flex flex-col gap-4">
            <p className="m-0 text-[12px] text-muted">{t.model}. Giá khớp do bộ mô phỏng sinh ra nên “thực tế” = mô hình có tính biên độ bar; khi có fill demo/live sẽ dùng cùng công thức so với quote.</p>
            {o ? (
              <div className="grid grid-cols-[repeat(auto-fit,minmax(9rem,1fr))] gap-4">
                <Stat label="Trượt giá+spread thực" value={`${N(o.realized_slip_bps)} bps`} sub={`giả định cố định ${N(o.assumed_slip_bps)} bps`} />
                <Stat label="Phần do biên độ bar" value={`${N(o.range_extra_bps)} bps`} />
                <Stat label="Chi phí toàn phần/chiều" value={`${N(o.all_in_bps)} bps`} sub={`giả định ${N(o.assumed_all_in_bps)} bps`} />
                <Stat label="Thực / giả định" value={o.ratio == null ? "—" : `${N(o.ratio)}×`} sub={t.status === "insufficient" ? "cần ≥ 10 fill" : <Light s={t.status} />} />
                <Stat label="Số fill" value={o.fills} />
              </div>) : <div className="text-muted text-[12.5px]">Chưa có fill nào.</div>}
            <div className="grid grid-cols-[repeat(auto-fit,minmax(9rem,1fr))] gap-4 border-t border-line pt-2">
              <Stat label={`Chi phí luỹ kế (${ccy})`} value={N(c.total)} sub={`${P0(c.pct_of_initial, 3)} vốn`} />
              <Stat label="Spread / trượt giá" value={`${N(c.spread)} / ${N(c.slippage)}`} />
              <Stat label="Phí+thuế / swap" value={`${N((c.commission || 0) + (c.tax || 0))} / ${N(c.swap)}`} />
              <Stat label="Vòng quay (× equity)" value={N(t.turnover?.x_equity)} sub={t.turnover?.x_equity_annualized ? `${N(t.turnover.x_equity_annualized, 1)}/năm vs backtest ${N(t.backtest_reference?.turnover_per_year, 1)}` : "chưa đủ 20 ngày để quy năm"} />
              <Stat label="Chi phí/năm" value={t.cost_drag_annualized == null ? "—" : P0(t.cost_drag_annualized, 2)} sub={t.backtest_reference?.cost_drag_per_year ? `backtest ${P0(t.backtest_reference.cost_drag_per_year, 2)}` : undefined} />
            </div>
            {(t.by_class || []).length > 0 && (
              <div className="scroll-x"><table className="tbl" style={{ minWidth: 520 }}>
                <thead><tr><th>Lớp</th><th className="r">Fill</th><th className="r">Thực (bps)</th><th className="r">Giả định</th><th className="r">Thực/giả định</th></tr></thead>
                <tbody>{t.by_class.map((r) => <tr key={r.class}><td>{r.class}</td><td className="r num">{r.fills}</td><td className="r num">{N(r.all_in_bps)}</td><td className="r num text-muted">{N(r.assumed_all_in_bps)}</td><td className="r num">{N(r.ratio)}</td></tr>)}</tbody></table></div>)}
          </div>
        );
      }}
    </Async>
  );
}

/* ------------------------------------------------------------------------------------------ suy giảm */
function DriftTab({ id }) {
  const q = useQ(`/accounts/${id}/drift`);
  return (
    <Async q={q} rows={5}>
      {(d) => {
        if (d.status === "n/a" || !d.signal) return <div className="text-[12.5px] text-muted">{d.note || "Chưa đủ dữ liệu."} <Light s={d.status} /></div>;
        const s = d.signal, c = s.cusum, dec = d.decomposition, ex = d.execution || {};
        const build = () => {
          const axis = { axisLine: { lineStyle: { color: css("--line2") } }, axisLabel: { color: css("--muted"), fontSize: 11 }, splitLine: { lineStyle: { color: css("--line") } } };
          return { animation: false, backgroundColor: "transparent", grid: { left: 44, right: 10, top: 10, bottom: 22 }, tooltip: { trigger: "axis", backgroundColor: css("--panel2"), borderColor: css("--line2"), textStyle: { color: css("--fg"), fontSize: 12 } },
            xAxis: { type: "category", ...axis, data: s.cusum_path.map((_, i) => i + 1) }, yAxis: { type: "value", ...axis, max: Math.max(c.h * 1.1, ...s.cusum_path) },
            series: [{ name: "CUSUM (suy giảm)", type: "line", showSymbol: false, data: s.cusum_path, lineStyle: { color: css("--accent"), width: 1.8 },
              markLine: { silent: true, symbol: "none", label: { formatter: (x) => x.name, color: css("--muted"), fontSize: 10 }, data: [{ yAxis: c.h, name: "ngưỡng đỏ", lineStyle: { color: css("--down") } }, { yAxis: c.h_warn, name: "ngưỡng vàng", lineStyle: { color: css("--accent"), type: "dashed" } }] } }] };
        };
        return (
          <div className="flex flex-col gap-4">
            <div className="flex flex-wrap items-center gap-2"><Light s={d.status} /> <b className="text-[13px]">{d.diagnosis_text}</b></div>
            <div className="grid grid-cols-[repeat(auto-fit,minmax(10rem,1fr))] gap-4">
              <Stat label="Sharpe live vs kỳ vọng" value={`${N(s.live_sharpe)} vs ${N(s.expected_sharpe)}`} sub={`vol live ${P0(s.live_vol_ann)}`} />
              <Stat label="Kiểm định trung bình" value={`t = ${N(s.t_stat)}`} sub={`p(kém kỳ vọng) = ${N(s.p_below_expected, 3)}`} />
              <Stat label="CUSUM / ngưỡng đỏ" value={`${N(c.S, 1)} / ${N(c.h, 1)}`} sub={c.breached ? `vượt ${s.cusum_breach_date ? date(s.cusum_breach_date) : ""}` : `${P0(c.ratio, 0)} ngưỡng`} />
              <Stat label="Ngày lãi (ngày có vị thế)" value={`${P0(s.hit_rate.observed, 0)} vs ${P0(s.hit_rate.expected, 0)}`} sub={`p = ${N(s.hit_rate.p_below_expected, 3)} · n=${s.hit_rate.active_days}`} />
            </div>
            <div><div className="text-[11.5px] text-muted mb-1">CUSUM một phía: phát hiện Sharpe tụt từ {N(s.expected_sharpe)} xuống {d.alt_sharpe}; ngưỡng đỏ chọn để báo động giả TB ~ {Math.round(d.arl0_days / 252)} năm/lần</div>
              <EChart build={build} deps={[d]} height={170} label="Đường CUSUM so với ngưỡng cảnh báo" /></div>
            <div className="grid gap-3 lg:grid-cols-2 border-t border-line pt-2">
              <div><div className="text-[11.5px] text-muted mb-1">Suy giảm TÍN HIỆU (lợi suất gộp, trước chi phí)</div>
                {dec ? <dl className="grid grid-cols-2 gap-x-3 gap-y-1 m-0 text-[12px]">
                  {[["Lợi suất/năm ròng", P(dec.mean_net_ann)], ["Lợi suất/năm gộp", P(dec.mean_gross_ann)], ["Kỳ vọng/năm", P(dec.expected_mean_ann)], ["Thiếu hụt do chi phí", dec.share_of_shortfall_due_to_cost == null ? "—" : P0(dec.share_of_shortfall_due_to_cost, 0)]]
                    .map(([a, b]) => <div key={a} className="contents"><dt className="text-muted">{a}</dt><dd className="m-0 text-right num">{b}</dd></div>)}</dl> : <span className="text-faint text-[12px]">—</span>}</div>
              <div><div className="text-[11.5px] text-muted mb-1">Suy giảm THỰC THI (chi phí thực / giả định)</div>
                <div className="flex items-center gap-2 text-[12.5px]"><Light s={ex.status} /> <span className="num">{ex.cost_ratio_vs_assumed == null ? "—" : `${N(ex.cost_ratio_vs_assumed)}×`}</span> <span className="text-faint">({ex.fills} fill)</span></div>
                <div className="text-[11px] text-faint mt-1">{ex.rule}</div></div>
            </div>
            <p className="m-0 text-[11.5px] text-faint">{d.multiple_testing_note} Đỏ = rà soát; vàng chỉ hiển thị (không gửi cảnh báo). Với Sharpe ~0,5, CUSUM trên dữ liệu ngày cần hàng năm để kết luận.</p>
          </div>
        );
      }}
    </Async>
  );
}

/* ------------------------------------------------------------------------------------------ strategy card */
function CardTab({ id }) {
  const q = useQ(`/accounts/${id}/card`);
  return (
    <Async q={q} rows={6}>
      {(c) => {
        const cd = c.card, ev = c.evaluation || {}, bt = cd?.backtest || {};
        return (
          <div className="flex flex-col gap-4">
            <div className="flex flex-wrap items-center gap-2"><Chip tone={STAGE_TONE[ev.stage]} className="text-[12px]">{ev.stage_label}</Chip>
              {cd && <span className="text-[12.5px] text-muted">thẻ <b className="text-fg">{cd.id}</b> v{cd.version} · giai đoạn khai báo: {cd.declared_stage}</span>}</div>
            {ev.note && <p className="m-0 text-[12px] text-muted">{ev.note}</p>}
            {(ev.criteria || []).length > 0 && (
              <div className="scroll-x"><table className="tbl" style={{ minWidth: 560 }}>
                <thead><tr><th>Tiêu chí chuyển giai đoạn paper → xét duyệt</th><th className="r">Yêu cầu</th><th className="r">Hiện tại</th><th>Kết quả</th></tr></thead>
                <tbody>{ev.criteria.map((k) => (
                  <tr key={k.id}><td>{k.label}{k.hard && <span className="text-faint text-[11px]"> · chặn cứng</span>}</td>
                    <td className="r num text-muted">{typeof k.required === "boolean" ? (k.required ? "có" : "không") : `${k.required ?? "—"} ${k.unit || ""}`}</td>
                    <td className="r num">{k.actual === true ? "có" : k.actual === false ? "không" : `${k.actual ?? "—"}`}</td>
                    <td><Chip tone={k.ok === true ? "up" : k.ok === false ? "down" : ""}>{k.ok === true ? "đạt" : k.ok === false ? "chưa đạt" : "chưa đủ dữ liệu"}</Chip></td></tr>))}</tbody></table></div>)}
            {cd ? (
              <>
                <div className="grid gap-3 lg:grid-cols-2 text-[12.5px]">
                  <div><div className="text-[11.5px] text-muted">Mô tả</div>{cd.description}</div>
                  <div><div className="text-[11.5px] text-muted">Giả thuyết (và điều kiện làm nó sai)</div>{cd.hypothesis}</div>
                </div>
                <div className="grid grid-cols-[repeat(auto-fit,minmax(9rem,1fr))] gap-4">
                  <Stat label="Backtest Sharpe (CI95)" value={N(bt.sharpe)} sub={ci(bt.sharpe_ci95, N)} />
                  <Stat label="CAGR / vol" value={`${P0(bt.cagr_total)} / ${P0(bt.vol)}`} />
                  <Stat label="MaxDD backtest" value={P(bt.max_dd)} />
                  <Stat label="Deflated Sharpe" value={N(bt.dsr)} sub="ngưỡng đặt trước 0,95" />
                  <Stat label="Kỳ vọng forward" value={ci(cd.expectation?.sharpe_forward, N)} sub="Sharpe sau chi phí" />
                </div>
                <div className="grid gap-3 lg:grid-cols-2">
                  <div><div className="text-[11.5px] text-muted mb-1">Kiểm định backtest → paper (kể cả mục KHÔNG đạt)</div>
                    <ul className="m-0 p-0 list-none grid gap-1 text-[12.5px]">{(cd.backtest_gates || []).map((g) => (
                      <li key={g.id} className="flex gap-2 items-start"><Chip tone={g.result === "pass" ? "up" : "down"}>{g.result === "pass" ? "đạt" : "không đạt"}</Chip><span>{g.label} <span className="text-faint">— {g.detail}</span></span></li>))}</ul></div>
                  <div><div className="text-[11.5px] text-muted mb-1">Điều kiện dừng / rủi ro đã biết</div>
                    <ul className="m-0 pl-4 grid gap-1 text-[12.5px]">{[...(cd.stop_conditions || []), ...(cd.known_risks || [])].map((s, i) => <li key={i}>{s}</li>)}</ul></div>
                </div>
                <div className="text-[11.5px] text-faint num">Duyệt: {cd.approval?.approved_by || "chưa có người duyệt"} · tham số cố định hash {short(c.config?.params_hash)} · cấu hình hash {short(c.config?.config_hash)}</div>
              </>) : <div className="text-muted text-[12.5px]">Tài khoản này không có strategy card (đối chứng hoặc chưa viết thẻ).</div>}
          </div>
        );
      }}
    </Async>
  );
}

/* ------------------------------------------------------------------------------------------ hash-chain + phiên bản */
function IntegrityTab({ id }) {
  const v = useQ(`/accounts/${id}/verify`);
  const cv = useQ(`/accounts/${id}/config-versions`);
  return (
    <div className="grid gap-4 lg:grid-cols-2">
      <Async q={v} rows={4}>
        {(x) => (
          <div className="flex flex-col gap-2 text-[12.5px]">
            <div className="flex items-center gap-2"><Chip tone={x.ok === false ? "down" : x.ok ? "up" : ""} className="text-[12px]">{x.ok === false ? "CHUỖI ĐỨT / BỊ SỬA" : x.ok ? "CHUỖI NGUYÊN VẸN" : "chưa có chuỗi"}</Chip>
              <span className="text-muted num">{x.entries} bản ghi · kiểm lúc {dateTime(x.checked_at)}</span></div>
            <dl className="grid grid-cols-2 gap-x-3 gap-y-1 m-0 text-[12px]">
              {[["Đầu chuỗi (seq)", x.head ? `#${x.head.seq} ${short(x.head.hash)}` : "—"], ["Neo ngoài DB", x.anchor_ok == null ? "chưa có" : x.anchor_ok ? "khớp" : "LỆCH"],
                ["Phạm vi", Object.entries(x.scope || {}).map(([k, n]) => `${k} ${n}`).join(" · ")]].map(([a, b]) => <div key={a} className="contents"><dt className="text-muted">{a}</dt><dd className="m-0 text-right num">{b}</dd></div>)}</dl>
            {(x.problems || []).length > 0 && <ul className="m-0 pl-4 text-down">{x.problems.slice(0, 8).map((p, i) => <li key={i}>{p.type}: {p.kind || ""} {p.ref || p.seq}</li>)}</ul>}
            <p className="m-0 text-[11.5px] text-faint">{x.tamper_evident}</p>
          </div>)}
      </Async>
      <Async q={cv} rows={3} empty="Chưa có phiên bản cấu hình.">
        {(x) => (
          <div className="flex flex-col gap-2 text-[12.5px]">
            <div className="text-[11.5px] text-muted">Phiên bản cấu hình bất biến (đổi tham số/rủi ro/chi phí → phiên bản mới, đồng hồ đánh giá bắt đầu lại)</div>
            <ul className="m-0 p-0 list-none grid gap-1">{(x.items || []).slice().reverse().map((v_) => (
              <li key={v_.version} className="flex gap-2 items-center"><Chip tone={v_.version === x.current?.version ? "ro" : ""}>v{v_.version}</Chip>
                <span className="num text-muted" title={v_.config_hash}>{short(v_.config_hash)}</span><span className="text-faint num text-[11.5px]">{dateTime(v_.created_at)}</span></li>))}</ul>
          </div>)}
      </Async>
    </div>
  );
}

const TABS = [{ value: "perf", label: "Hiệu suất + CI" }, { value: "tca", label: "TCA" }, { value: "drift", label: "Suy giảm" }, { value: "card", label: "Strategy card" }, { value: "chain", label: "Toàn vẹn" }];
const ICON = { perf: Gauge, tca: Receipt, drift: TrendingDown, card: ScrollText, chain: Fingerprint };

export default function PaperQuality({ id, ccy }) {
  const [tab, setTab] = useState("perf");
  const Ic = ICON[tab] || BadgeCheck;
  return (
    <Panel title="Chất lượng & quản trị chiến lược (mô phỏng)" icon={Ic}
      right={<Seg value={tab} onChange={setTab} label="Chọn phần chất lượng" options={TABS} />}>
      <div className="flex flex-col gap-4">
        <Overview id={id} />
        <div className="border-t border-line pt-3">
          {tab === "perf" && <PerfTab id={id} />}
          {tab === "tca" && <TcaTab id={id} ccy={ccy} />}
          {tab === "drift" && <DriftTab id={id} />}
          {tab === "card" && <CardTab id={id} />}
          {tab === "chain" && <IntegrityTab id={id} />}
        </div>
      </div>
    </Panel>
  );
}
