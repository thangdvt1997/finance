import { useMemo, useState } from "react";
import { useQuery, keepPreviousData } from "@tanstack/react-query";
import { FlaskConical, ShieldAlert, ShieldCheck, LineChart, Layers, ListOrdered, Activity } from "lucide-react";
import { Async, Chip, Freshness, PageHead, Panel, Seg, Sparkline, Stat, cn } from "../components/ui";
import { FRESH } from "../lib/freshness";
import { EChart, css } from "../components/charts";
import { api } from "../lib/api";
import { dateTime, date, price, rel, signCls, symbolLabel } from "../lib/format";
import PaperQuality from "./PaperQuality";

/* Trang "Giao dịch mô phỏng" (service paper-trader). MỌI số liệu ở đây là MÔ PHỎNG — không phải tiền thật. */

const usePaper = (path, params, opts = {}) =>
  useQuery({
    queryKey: ["paper", path, params],
    queryFn: ({ signal }) => api(`/paper${path}`, params, signal),
    staleTime: 15_000,
    refetchInterval: 60_000,
    placeholderData: keepPreviousData,
    ...opts,
  });

const fmtMoney = (v, ccy) => {
  if (v == null || Number.isNaN(v)) return "—";
  if (ccy === "VND") return `${Math.round(v).toLocaleString("vi-VN")} ₫`;
  const s = Number(v).toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  return ccy === "USD" ? (v < 0 ? `-$${s.slice(1)}` : `$${s}`) : `${s} ${ccy || ""}`.trim();
};
const fmtQty = (v) => (v == null ? "—" : Number(v).toLocaleString("en-US", { maximumFractionDigits: 2 }));
const P = (x, dp = 2) => (x == null || Number.isNaN(x) ? "—" : `${x > 0 ? "+" : ""}${(x * 100).toFixed(dp)}%`);   // phân số -> %
const N2 = (x) => (x == null || Number.isNaN(x) ? "—" : Number(x).toFixed(2));

const STATUS = {
  active: { label: "ĐANG HOẠT ĐỘNG", tone: "up", icon: ShieldCheck },
  halted: { label: "TẠM DỪNG (kill-switch)", tone: "accent", icon: ShieldAlert },
  locked: { label: "KHOÁ CỨNG — cần reset tay", tone: "down", icon: ShieldAlert },
};
const ORDER_TONE = { filled: "up", pending: "accent", rejected: "down", cancelled: "", expired: "" };
const ORDER_LABEL = { filled: "đã khớp", pending: "chờ khớp", rejected: "bị chặn", cancelled: "huỷ", expired: "hết hạn" };

function Banner() {
  return (
    <div role="note" className="flex gap-3 items-start rounded-md border px-3 py-2 text-[12.5px]"
      style={{ borderColor: "var(--accent)", background: "var(--accent-bg)" }}>
      <FlaskConical size={16} className="text-accent shrink-0 mt-[2px]" aria-hidden="true" />
      <div>
        <b className="text-accent tracking-wide">MÔ PHỎNG — KHÔNG PHẢI TIỀN THẬT.</b>{" "}
        <span className="text-fg">
          Đây là forward test: lệnh ảo khớp theo giá mở cửa của nến kế tiếp, đã tính spread, trượt giá, phí và swap theo giả định bảo thủ. Không có kết nối
          broker/MT, không có đường đặt lệnh thật. Kết quả mô phỏng không đảm bảo kết quả tương lai và không phải khuyến nghị đầu tư.
        </span>
      </div>
    </div>
  );
}

function AccountCards({ items, sel, onSel }) {
  const rank = (a) => (!a.meaningful ? 2 : a.strategy === "buy_and_hold" ? 1 : 0);
  const order = [...items].sort((a, b) => rank(a) - rank(b) || a.account_id.localeCompare(b.account_id));
  return (
    <div className="grid gap-2 grid-cols-[repeat(auto-fill,minmax(15.5rem,1fr))]" role="group" aria-label="Chọn tài khoản mô phỏng">
      {order.map((a) => {
        const st = STATUS[a.status] || STATUS.active;
        const isBench = a.strategy === "buy_and_hold";
        return (
          <button key={a.account_id} type="button" aria-pressed={sel === a.account_id} onClick={() => onSel(a.account_id)}
            className={cn("text-left panel p-3 cursor-pointer flex flex-col items-stretch gap-1 min-w-0 overflow-hidden", sel === a.account_id && "outline outline-2 outline-accent")}
            style={{ font: "inherit", color: "inherit" }}>
            <span className="font-semibold text-[12.5px] truncate block w-full min-w-0" title={a.name}>{a.name}</span>
            <span className="flex gap-1 flex-wrap min-h-[20px]">
              {isBench ? <Chip>đối chứng</Chip> : a.meaningful ? <Chip tone="ro">chiến lược</Chip> : null}
              {!a.meaningful && <Chip tone="accent" title="Cửa sổ rút gọn, replay dữ liệu quá khứ: chỉ để kiểm tra đường ống">kiểm thử đường ống</Chip>}
              {a.status !== "active" && <Chip tone={st.tone}>{a.status === "locked" ? "KHOÁ CỨNG" : "TẠM DỪNG"}</Chip>}
            </span>
            <div className="flex items-end justify-between gap-2">
              <div>
                <div className="num text-[17px]">{fmtMoney(a.equity, a.base_ccy)}</div>
                <div className={cn("num text-[12px]", signCls(a.total_return))}>{P(a.total_return)} <span className="text-faint">từ vốn</span></div>
              </div>
              <Sparkline values={(a.spark || []).map((p) => p.index)} width={84} height={30} />
            </div>
          </button>
        );
      })}
    </div>
  );
}

function EquityVsBenchmark({ id, name }) {
  const q = usePaper(`/accounts/${id}/equity`, { limit: 3000 });
  return (
    <Panel title="Equity so với benchmark (chuẩn hoá = 100)" icon={LineChart} bodyClass="flex flex-col"
      right={<span className="text-[11.5px] text-faint">MÔ PHỎNG</span>}>
      <Async q={q} rows={6} empty="Chưa có điểm equity nào.">
        {(d) => {
          const s = d.series || [], b = d.benchmark || [];
          if (!s.length) return <div className="text-muted">Chưa có điểm equity nào.</div>;
          const build = () => {
            const toX = (r) => [new Date(r.ts).getTime(), r.index];
            const vals = [...s, ...b].map((r) => r.index);
            const lo = Math.min(...vals, 100), hi = Math.max(...vals, 100), pad = Math.max((hi - lo) * 0.2, 0.5);
            const axis = { axisLine: { lineStyle: { color: css("--line2") } }, axisLabel: { color: css("--muted"), fontSize: 11 }, splitLine: { lineStyle: { color: css("--line") } } };
            const few = s.length < 40;
            return {
              animation: false, backgroundColor: "transparent",
              grid: [{ left: 54, right: 16, top: 12, height: "58%" }, { left: 54, right: 16, top: "76%", bottom: 26 }],
              tooltip: { trigger: "axis", backgroundColor: css("--panel2"), borderColor: css("--line2"), textStyle: { color: css("--fg"), fontSize: 12 },
                formatter: (a) => `${dateTime(a[0].value[0])}<br/>${a.map((x) => `${x.marker}${x.seriesName}: <b>${x.seriesName === "Drawdown" ? (x.value[1] * 100).toFixed(2) + "%" : x.value[1].toFixed(2)}</b>`).join("<br/>")}` },
              axisPointer: { link: [{ xAxisIndex: "all" }] },
              xAxis: [{ type: "time", gridIndex: 0, ...axis, axisLabel: { show: false }, splitLine: { show: false } },
                      { type: "time", gridIndex: 1, splitNumber: 5, ...axis, axisLabel: { ...axis.axisLabel, formatter: (v) => date(v) }, splitLine: { show: false } }],
              yAxis: [{ type: "value", gridIndex: 0, min: lo - pad, max: hi + pad, scale: true, ...axis, axisLabel: { ...axis.axisLabel, formatter: (v) => v.toFixed(1) } },
                      { type: "value", gridIndex: 1, max: 0, min: (v) => Math.min(v.min * 1.2, -0.01), ...axis, splitNumber: 2, axisLabel: { ...axis.axisLabel, formatter: (v) => `${(v * 100).toFixed(0)}%` } }],
              series: [
                { name: "Chiến lược", type: "line", xAxisIndex: 0, yAxisIndex: 0, data: s.map(toX), showSymbol: few, symbolSize: 6, lineStyle: { width: 2.2, color: css("--accent") }, itemStyle: { color: css("--accent") },
                  markLine: { silent: true, symbol: "none", label: { show: false }, lineStyle: { color: css("--faint"), type: "dotted" }, data: [{ yAxis: 100 }] } },
                ...(b.length ? [{ name: "Benchmark", type: "line", xAxisIndex: 0, yAxisIndex: 0, data: b.map(toX), showSymbol: few, symbolSize: 5, lineStyle: { width: 1.6, color: css("--info"), type: "dashed" }, itemStyle: { color: css("--info") } }] : []),
                { name: "Drawdown", type: "line", xAxisIndex: 1, yAxisIndex: 1, data: (d.drawdown || []).map((r) => [new Date(r.ts).getTime(), r.dd ?? 0]), showSymbol: false, lineStyle: { width: 1, color: css("--down") }, areaStyle: { color: css("--down-bg") } },
              ],
            };
          };
          return (
            <>
              <div className="flex flex-wrap items-center gap-4 text-[12px] mb-1" aria-hidden="true">
                <span className="flex items-center gap-[6px]"><i className="inline-block w-4 h-[3px]" style={{ background: "var(--accent)" }} /> {name}</span>
                {b.length > 0 && <span className="flex items-center gap-[6px]"><i className="inline-block w-4 border-t-2 border-dashed" style={{ borderColor: "var(--info)" }} /> Benchmark: {d.benchmark_id}</span>}
                <span className="flex items-center gap-[6px]"><i className="inline-block w-4 h-[3px]" style={{ background: "var(--down)" }} /> Drawdown</span>
                <span className="ml-auto text-faint">{s.length} điểm · {date(s[0].ts)} → {date(s[s.length - 1].ts)}</span>
              </div>
              <EChart build={build} deps={[d]} height={300} label={`Đường equity mô phỏng của ${name} so với benchmark, kèm drawdown`} />
              {s.length < 20 && <p className="m-0 mt-1 text-[12px] text-muted">Mới bắt đầu forward test ({s.length} điểm). Cần tối thiểu 8–12 tuần dữ liệu mô phỏng trước khi diễn giải kết quả.</p>}
            </>
          );
        }}
      </Async>
    </Panel>
  );
}

function Meter({ label, cur, limit }) {
  // cur, limit là phân số âm (lỗ). Mức dùng = cur/limit (0..1+)
  const used = limit ? Math.max(0, Math.min(1, cur / limit)) : 0;
  const tone = used >= 0.8 ? "var(--down)" : used >= 0.5 ? "var(--accent)" : "var(--up)";
  return (
    <div className="min-w-0">
      <div className="flex justify-between gap-2 text-[12px]">
        <span className="text-muted">{label}</span>
        <span className="num"><span className={signCls(cur)}>{P(cur)}</span> <span className="text-faint">/ giới hạn {P(limit)}</span></span>
      </div>
      <div className="h-[6px] rounded bg-panel2 border border-line mt-1 overflow-hidden" role="meter" aria-valuemin={0} aria-valuemax={100}
        aria-valuenow={Math.round(used * 100)} aria-label={`${label}: đã dùng ${Math.round(used * 100)}% hạn mức`}>
        <div style={{ width: `${used * 100}%`, background: tone, height: "100%" }} />
      </div>
    </div>
  );
}

function KillSwitch({ id }) {
  const q = usePaper(`/accounts/${id}/kill-switch`);
  return (
    <Panel title="Kill-switch & giới hạn rủi ro" icon={ShieldCheck}>
      <Async q={q} rows={5}>
        {(k) => {
          const st = STATUS[k.status] || STATUS.active;
          const Ic = st.icon;
          const r = k.rules || {};
          return (
            <div className="flex flex-col gap-3">
              <div className="flex items-center gap-2 flex-wrap">
                <Chip tone={st.tone} className="text-[12px]"><Ic size={13} aria-hidden="true" /> {st.label}</Chip>
                {k.status === "halted" && k.halt_until && <span className="text-[12px] text-muted">mở lại {dateTime(k.halt_until)}</span>}
              </div>
              {k.reason && <div className="text-[12.5px] text-down">Lý do: {k.reason}</div>}
              <Meter label="Lỗ trong ngày" cur={Math.min(0, k.current.daily)} limit={k.limits.daily} />
              <Meter label="Lỗ trong tuần" cur={Math.min(0, k.current.weekly)} limit={k.limits.weekly} />
              <Meter label="Drawdown từ đỉnh (khoá cứng)" cur={Math.min(0, k.current.drawdown)} limit={k.limits.drawdown} />
              <dl className="grid grid-cols-2 gap-x-4 gap-y-1 m-0 text-[12px]">
                {[["Đòn bẩy tối đa", r.max_leverage != null ? `${r.max_leverage}×` : "—"], ["Tỷ trọng/symbol tối đa", r.max_weight != null ? `${(r.max_weight * 100).toFixed(0)}%` : "—"],
                  ["Lệnh/phút tối đa", r.max_orders_per_minute ?? "—"], ["Định cỡ vị thế", r.sizing?.mode === "vol_target" ? `vol targeting ${(r.sizing.target_vol * 100).toFixed(0)}%` : r.sizing?.mode ?? "—"],
                  ["Tất toán khi dừng", r.flatten_on_halt ? "có" : "không"], ["Bộ lọc tin", "chặn tăng vị thế T-15..T+30"]].map(([a, b]) => (
                  <div key={a} className="contents"><dt className="text-muted">{a}</dt><dd className="m-0 text-right num">{b}</dd></div>
                ))}
              </dl>
            </div>
          );
        }}
      </Async>
    </Panel>
  );
}

function Positions({ id, ccy }) {
  const q = usePaper(`/accounts/${id}/positions`);
  const acc = usePaper(`/accounts/${id}`);
  const eq = acc.data?.equity;
  return (
    <Panel title="Vị thế mô phỏng hiện tại" icon={Layers} pad={false} scroll>
      <Async q={q} rows={3} empty="Đang đứng ngoài thị trường (không có vị thế)." hint="Chiến lược chưa đủ dữ liệu hoặc đang ở trạng thái tiền mặt.">
        {(d) => {
          const rows = d.items || [];
          if (!rows.length) return <div className="p-3 text-muted">Đang đứng ngoài thị trường (không có vị thế). Lệnh đã đặt sẽ khớp ở giá mở cửa của nến kế tiếp.</div>;
          return (
            <div className="scroll-x">
              <table className="tbl" style={{ minWidth: 560 }}>
                <thead><tr><th>Mã</th><th>Hướng</th><th className="r">Khối lượng</th><th className="r">Giá vào</th><th className="r">Giá đánh dấu</th><th className="r">Tỷ trọng</th><th className="r">Lãi/lỗ chưa chốt</th></tr></thead>
                <tbody>
                  {rows.map((p) => (
                    <tr key={p.symbol}>
                      <td><b>{symbolLabel(p.symbol)}</b></td>
                      <td><Chip tone={p.qty > 0 ? "up" : "down"}>{p.qty > 0 ? "MUA" : "BÁN"}</Chip></td>
                      <td className="r num">{fmtQty(Math.abs(p.qty))}</td>
                      <td className="r num">{price(p.symbol, p.avg_price)}</td>
                      <td className="r num">{price(p.symbol, p.mark_price)}</td>
                      <td className="r num">{eq ? `${((p.notional / eq) * 100).toFixed(1)}%` : "—"}</td>
                      <td className={cn("r num", signCls(p.unrealized_pnl))}>{fmtMoney(p.unrealized_pnl, ccy)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          );
        }}
      </Async>
    </Panel>
  );
}

function Activity3({ id, ccy }) {
  const [tab, setTab] = useState("orders");
  const orders = usePaper(`/accounts/${id}/orders`, { limit: 40 }, { enabled: tab === "orders" });
  const fills = usePaper(`/accounts/${id}/fills`, { limit: 40 }, { enabled: tab === "fills" });
  const events = usePaper(`/accounts/${id}/events`, { limit: 40 }, { enabled: tab === "events" });
  const q = { orders, fills, events }[tab];
  return (
    <Panel title="Nhật ký mô phỏng" icon={ListOrdered} pad={false} scroll
      right={<Seg value={tab} onChange={setTab} label="Loại nhật ký" options={[{ value: "orders", label: "Lệnh" }, { value: "fills", label: "Fill" }, { value: "events", label: "Sự kiện" }]} />}>
      <Async q={q} rows={4} empty="Chưa có bản ghi.">
        {(d) => {
          const rows = d.items || [];
          if (!rows.length) return <div className="p-3 text-muted">Chưa có bản ghi.</div>;
          if (tab === "orders")
            return (
              <div className="scroll-x"><table className="tbl" style={{ minWidth: 560 }}>
                <thead><tr><th>Quyết định lúc</th><th>Mã</th><th>Hướng</th><th className="r">Khối lượng</th><th className="r">Tỷ trọng mục tiêu</th><th>Trạng thái</th></tr></thead>
                <tbody>{rows.map((o) => (
                  <tr key={o.client_order_id}>
                    <td className="num">{dateTime(o.decision_ts)}</td><td><b>{symbolLabel(o.symbol)}</b></td>
                    <td><Chip tone={o.side === "buy" ? "up" : "down"}>{o.side === "buy" ? "MUA" : "BÁN"}</Chip></td>
                    <td className="r num">{fmtQty(o.qty)}</td><td className="r num">{o.target_weight != null ? `${(o.target_weight * 100).toFixed(1)}%` : "—"}</td>
                    <td><Chip tone={ORDER_TONE[o.status]} title={o.reason || undefined}>{ORDER_LABEL[o.status] || o.status}</Chip>{o.reason ? <span className="text-faint text-[11px] ml-1">{o.reason}</span> : null}</td>
                  </tr>))}</tbody></table></div>
            );
          if (tab === "fills")
            return (
              <div className="scroll-x"><table className="tbl" style={{ minWidth: 640 }}>
                <thead><tr><th>Nến khớp</th><th>Mã</th><th>Hướng</th><th className="r">Khối lượng</th><th className="r">Giá mở (mid)</th><th className="r">Giá khớp</th><th className="r">Phí+thuế</th><th className="r">Lãi/lỗ chốt</th></tr></thead>
                <tbody>{rows.map((f) => (
                  <tr key={f.client_order_id}>
                    <td className="num">{dateTime(f.ts)}</td><td><b>{symbolLabel(f.symbol)}</b></td>
                    <td><Chip tone={f.side === "buy" ? "up" : "down"}>{f.side === "buy" ? "MUA" : "BÁN"}</Chip></td>
                    <td className="r num">{fmtQty(f.qty)}</td><td className="r num text-muted">{price(f.symbol, f.ref_price)}</td><td className="r num">{price(f.symbol, f.price)}</td>
                    <td className="r num text-muted">{fmtMoney((f.commission || 0) + (f.tax || 0), ccy)}</td>
                    <td className={cn("r num", signCls(f.realized_pnl))}>{f.realized_pnl ? fmtMoney(f.realized_pnl, ccy) : "—"}</td>
                  </tr>))}</tbody></table></div>
            );
          return (
            <ul className="m-0 p-0 list-none">
              {rows.map((e) => (
                <li key={e.id} className="flex gap-2 items-start px-3 py-[7px] border-b border-line text-[12.5px]">
                  <Chip tone={e.severity === "crit" ? "down" : e.severity === "warn" ? "accent" : ""}>{e.type}</Chip>
                  <span className="min-w-0 flex-1">{e.message}</span>
                  <span className="text-faint num text-[11.5px] shrink-0" title={dateTime(e.ts)}>{rel(e.ts)}</span>
                </li>
              ))}
            </ul>
          );
        }}
      </Async>
    </Panel>
  );
}

function Stats({ id, ccy }) {
  const q = usePaper(`/accounts/${id}/stats`);
  return (
    <Panel title="Hiệu suất & rủi ro (empyrical)" icon={Activity}>
      <Async q={q} rows={5}>
        {(s) => {
          const t = s.trading || {}, c = t.costs || {};
          const cell = (v, f) => (s.reliable || v == null ? f(v) : f(v));
          return (
            <div className="flex flex-col gap-3">
              {!s.reliable && <div className="text-[12px] text-muted">{s.note || "Mẫu quá ngắn: chỉ số chưa có ý nghĩa thống kê."} <b className="text-accent">({s.days ?? 0} ngày dữ liệu)</b></div>}
              <div className={cn("grid grid-cols-[repeat(auto-fit,minmax(8.5rem,1fr))] gap-4", !s.reliable && "border-l-2 border-dashed border-line pl-3")}>
                <Stat label="Tổng lợi suất" value={P(s.total_return)} tone={signCls(s.total_return)} />
                <Stat label="CAGR" value={s.cagr == null ? "—" : P(s.cagr)} sub={s.cagr == null ? "cần ≥ 30 ngày" : undefined} />
                <Stat label="Biến động năm" value={s.annual_volatility == null ? "—" : P(s.annual_volatility).replace("+", "")} />
                <Stat label="Sharpe" value={cell(s.sharpe, N2)} />
                <Stat label="Sortino" value={cell(s.sortino, N2)} />
                <Stat label="Calmar" value={s.calmar == null ? "—" : N2(s.calmar)} />
                <Stat label="Max drawdown" value={P(s.max_drawdown)} tone={signCls(s.max_drawdown)} />
                <Stat label="Drawdown hiện tại" value={P(s.current_drawdown)} tone={signCls(s.current_drawdown)} />
                {s.benchmark_total_return != null && <Stat label="So với benchmark" value={P(s.excess_total_return)} tone={signCls(s.excess_total_return)} sub={`benchmark ${P(s.benchmark_total_return)}`} />}
                {s.beta != null && <Stat label="Beta / Alpha năm" value={`${N2(s.beta)} / ${P(s.alpha)}`} />}
              </div>
              <div className="border-t border-line pt-2">
                <div className="text-[11.5px] text-muted mb-1">Giao dịch & chi phí lũy kế (đơn vị {ccy})</div>
                <div className="grid grid-cols-[repeat(auto-fit,minmax(8.5rem,1fr))] gap-4">
                  <Stat label="Lệnh / fill" value={`${t.orders ?? 0} / ${t.fills ?? 0}`} />
                  <Stat label="Vòng quay (× equity)" value={t.turnover_x_equity == null ? "—" : t.turnover_x_equity.toFixed(2)} />
                  <Stat label="Phí + thuế" value={fmtMoney((c.commission || 0) + (c.tax || 0), ccy)} />
                  <Stat label="Spread (ước tính)" value={fmtMoney(c.spread, ccy)} />
                  <Stat label="Trượt giá (ước tính)" value={fmtMoney(c.slippage, ccy)} />
                  <Stat label="Swap/funding" value={fmtMoney(c.swap, ccy)} />
                  <Stat label="Tỷ lệ lệnh chốt lãi" value={t.win_rate_closed == null ? "—" : `${(t.win_rate_closed * 100).toFixed(0)}%`} />
                </div>
              </div>
            </div>
          );
        }}
      </Async>
    </Panel>
  );
}

export default function Paper() {
  const ov = usePaper("/overview", { points: 90 });
  const [sel, setSel] = useState("");
  const items = ov.data?.items || [];
  const acct = useMemo(() => items.find((a) => a.account_id === sel) || items.find((a) => a.meaningful && a.strategy !== "buy_and_hold") || items[0], [items, sel]);
  return (
    <>
      <PageHead title="Giao dịch mô phỏng (paper trading)" sub="Forward test các phương pháp theo thời gian thực trước khi đụng cổng pháp lý. Kiểm chứng bằng dữ liệu thật, vốn ảo."
        right={<Chip tone="accent" className="text-[12px]"><FlaskConical size={13} aria-hidden="true" /> MÔ PHỎNG — không phải tiền thật</Chip>} />
      <Banner />
      <Async q={ov} rows={6} empty="Chưa có tài khoản mô phỏng." hint="Bật service paper-trader (compose tools) và chạy infra/db/create_paper_role.sh.">
        {() =>
          !acct ? null : (
            <>
              <AccountCards items={items} sel={acct.account_id} onSel={setSel} />
              <div className="flex flex-wrap items-center gap-2 text-[12.5px] text-muted">
                <b className="text-fg text-[14px]">{acct.name}</b>
                <span>chiến lược <b className="text-fg">{acct.strategy}</b> · tái cân bằng {acct.rebalance} · {acct.universe?.length ?? 0} mã · vốn ban đầu {fmtMoney(acct.initial_capital, acct.base_ccy)}</span>
                <span className="ml-auto">bắt đầu {acct.replay ? "REPLAY (dữ liệu quá khứ) " : "forward "}{dateTime(acct.inception)} · cập nhật {acct.replay ? rel(acct.as_of) : <Freshness ts={acct.as_of} source="paper" label="Mốc định giá gần nhất" {...FRESH.paper} />}</span>
              </div>
              {!acct.meaningful && <div role="note" className="text-[12.5px] text-accent">Tài khoản kiểm thử đường ống: cửa sổ rút gọn trên vài ngày dữ liệu, KHÔNG có ý nghĩa thống kê.</div>}
              <div className="grid gap-3 lg:grid-cols-[minmax(0,2fr)_minmax(0,1fr)]">
                <EquityVsBenchmark id={acct.account_id} name={acct.name} />
                <KillSwitch id={acct.account_id} />
              </div>
              <div className="grid gap-3 lg:grid-cols-2">
                <Positions id={acct.account_id} ccy={acct.base_ccy} />
                <Activity3 id={acct.account_id} ccy={acct.base_ccy} />
              </div>
              <Stats id={acct.account_id} ccy={acct.base_ccy} />
              <PaperQuality id={acct.account_id} ccy={acct.base_ccy} />
            </>
          )
        }
      </Async>
    </>
  );
}
