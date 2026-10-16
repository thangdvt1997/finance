import { useMemo, useState } from "react";
import { Wallet, LineChart } from "lucide-react";
import { Async, Chip, Freshness, PageHead, Panel, Seg, Stat, cn } from "../components/ui";
import { FRESH } from "../lib/freshness";
import { EChart, css } from "../components/charts";
import { useAccounts, useEquity } from "../lib/queries";
import { RiskSection } from "../components/riskpanels";
import { dateTime, money, pct, price, rel, signCls, symbolLabel, time, date } from "../lib/format";

const RANGES = { "1D": 1, "7D": 7, "30D": 30 };

function EquityChart({ id, range }) {
  const from = useMemo(() => new Date(Date.now() - RANGES[range] * 86400e3).toISOString().slice(0, 16) + ":00Z", [range, id]);
  const q = useEquity(id, from);
  return (
    <Async q={q} rows={6} empty="Chưa có lịch sử equity trong khoảng này." hint="Mỗi snapshot từ mt-bridge sẽ thành một điểm trên biểu đồ.">
      {(pts) => {
        const build = () => {
          const eq = pts.map((p) => [new Date(p.ts).getTime(), p.equity]);
          const bal = pts.map((p) => [new Date(p.ts).getTime(), p.balance]);
          const vals = pts.flatMap((p) => [p.equity, p.balance]).filter((v) => v != null);
          const lo = Math.min(...vals), hi = Math.max(...vals), pad = (hi - lo) * 0.15 || Math.max(Math.abs(hi) * 0.002, 1);
          const dp = hi - lo + 2 * pad < 10 ? 2 : 0; // khoảng giá trị hẹp -> hiện thập phân để nhãn trục không trùng nhau
          const axis = { axisLine: { lineStyle: { color: css("--line2") } }, axisLabel: { color: css("--muted"), fontSize: 11 }, splitLine: { lineStyle: { color: css("--line") } } };
          return {
            animation: false, backgroundColor: "transparent", grid: { left: 62, right: 14, top: 14, bottom: 26 },
            tooltip: { trigger: "axis", backgroundColor: css("--panel2"), borderColor: css("--line2"), textStyle: { color: css("--fg"), fontSize: 12 },
              formatter: (a) => `${dateTime(a[0].value[0])}<br/>${a.map((s) => `${s.marker}${s.seriesName}: <b>${money(s.value[1])}</b>`).join("<br/>")}` },
            xAxis: { type: "time", ...axis, axisLabel: { ...axis.axisLabel, formatter: (v) => (RANGES[range] > 1 ? date(v) : time(v)) }, splitLine: { show: false } },
            yAxis: { type: "value", min: lo - pad, max: hi + pad, ...axis, axisLabel: { ...axis.axisLabel, formatter: (v) => v.toLocaleString("en-US", { minimumFractionDigits: dp, maximumFractionDigits: dp }) } },
            series: [
              { name: "Equity", type: "line", data: eq, showSymbol: false, smooth: false, lineStyle: { width: 2, color: css("--accent") }, itemStyle: { color: css("--accent") },
                areaStyle: { color: css("--accent-bg") } },
              { name: "Balance", type: "line", data: bal, showSymbol: false, step: "end", lineStyle: { width: 1.2, color: css("--muted"), type: "dashed" }, itemStyle: { color: css("--muted") } },
            ],
          };
        };
        return <EChart build={build} deps={[pts, range]} height={240} label={`Biểu đồ equity và balance của tài khoản ${id}`} />;
      }}
    </Async>
  );
}

const side = (p) => (typeof p.side === "string" ? p.side.toLowerCase() : p.type === 1 ? "sell" : "buy");

export default function Accounts() {
  const q = useAccounts();
  const [sel, setSel] = useState("");
  const [range, setRange] = useState("7D");
  const list = q.data || [];
  const acct = list.find((a) => a.account_id === sel) || list[0];

  const view = acct && (() => {
    const pos = acct.positions || [];
    const floating = pos.reduce((s, p) => s + (p.profit || 0), 0);
    const free = acct.equity != null && acct.margin != null ? acct.equity - acct.margin : null;
    const level = acct.margin ? (acct.equity / acct.margin) * 100 : null;
    return { pos, floating, free, level };
  })();

  return (
    <>
      <PageHead title="Tài khoản MT4/MT5" sub="Snapshot từ mt-bridge qua tài khoản investor. Chỉ đọc: hệ thống không thể đặt, sửa hay đóng lệnh."
        right={<Chip tone="ro">READ-ONLY · investor</Chip>} />
      <Async q={q} rows={6} empty="Chưa có tài khoản nào gửi snapshot." hint="Bật mt-bridge (MT_ENABLED=true), cấu hình accounts.yaml với mật khẩu investor.">
        {() => (
          <>
            {list.length > 1 && <Seg value={acct.account_id} onChange={setSel} label="Chọn tài khoản" options={list.map((a) => ({ value: a.account_id, label: `${a.account_id} · ${a.platform.toUpperCase()}` }))} />}
            <Panel title={`${acct.account_id} · ${acct.platform.toUpperCase()}`} icon={Wallet} right={<Freshness ts={acct.ts} source={acct.platform.toUpperCase()} label="Snapshot tài khoản" {...FRESH.account} />}>
              <div className="grid grid-cols-[repeat(auto-fit,minmax(9.5rem,1fr))] gap-4">
                <Stat label="Equity" big value={money(acct.equity)} />
                <Stat label="Balance" big value={money(acct.balance)} />
                <Stat label="Lãi/lỗ đang mở" big value={money(view.floating)} tone={signCls(view.floating)} sub={`${view.pos.length} lệnh`} />
                <Stat label="Margin đã dùng" value={money(acct.margin)} />
                <Stat label="Margin còn trống" value={money(view.free)} />
                <Stat label="Mức margin" value={view.level == null ? "—" : `${view.level.toFixed(0)}%`} tone={view.level != null && view.level < 150 ? "down" : ""} sub={view.level != null && view.level < 150 ? "Thấp, cần chú ý" : "An toàn"} />
              </div>
            </Panel>
            <div className="grid gap-3 lg:flex-1 lg:min-h-[28rem] lg:grid-rows-[minmax(0,1.15fr)_minmax(0,1fr)] 2xl:grid-rows-[minmax(0,1fr)] 2xl:grid-cols-[minmax(0,3fr)_minmax(0,2fr)] grid-fill">
            <Panel title="Equity theo thời gian" icon={LineChart} bodyClass="flex flex-col" right={<Seg value={range} onChange={setRange} options={Object.keys(RANGES)} label="Khoảng thời gian" />}>
              <EquityChart id={acct.account_id} range={range} />
            </Panel>
            <Panel title="Vị thế đang mở" pad={false} scroll>
              {view.pos.length === 0 ? (
                <div className="p-3 text-muted">Tài khoản không có lệnh mở.</div>
              ) : (
                <div className="scroll-x">
                  <table className="tbl" style={{ minWidth: 700 }}>
                    <thead><tr><th>Mã</th><th>Hướng</th><th className="r">Lot</th><th className="r">Giá vào</th><th className="r">Giá hiện tại</th><th className="r">SL</th><th className="r">TP</th><th className="r">Swap</th><th className="r">Lãi/lỗ</th></tr></thead>
                    <tbody>
                      {view.pos.map((p, i) => (
                        <tr key={p.position_id || p.ticket || i}>
                          <td><b>{symbolLabel(p.symbol)}</b></td>
                          <td><Chip tone={side(p) === "buy" ? "up" : "down"}>{side(p) === "buy" ? "MUA" : "BÁN"}</Chip></td>
                          <td className="r num">{p.volume ?? p.lots}</td>
                          <td className="r num">{price(p.symbol, p.price_open ?? p.open_price)}</td>
                          <td className="r num">{price(p.symbol, p.price_current ?? p.price)}</td>
                          <td className="r num text-muted">{p.sl ? price(p.symbol, p.sl) : "—"}</td>
                          <td className="r num text-muted">{p.tp ? price(p.symbol, p.tp) : "—"}</td>
                          <td className="r num text-muted">{money(p.swap ?? 0)}</td>
                          <td className={cn("r num", signCls(p.profit))}>{money(p.profit)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </Panel>
            </div>
          </>
        )}
      </Async>
      <RiskSection />
    </>
  );
}
