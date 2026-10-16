import { useEffect, useState } from "react";
import { ShieldAlert, Gauge, TrendingDown, Layers, Zap, Network, AlertTriangle } from "lucide-react";
import { Async, Chip, Panel, Seg, Stat, cn } from "./ui";
import { EChart, css } from "./charts";
import { useRiskAccounts, useRiskAccount } from "../lib/queries";
import { money, pct, signCls, symbolLabel, dateTime } from "../lib/format";

/** Mục "Rủi ro tài khoản" (risk-monitor). READ-ONLY: số liệu ước tính từ snapshot + lịch sử D1, không phải lời khuyên. */
const TONE = { ok: "up", warn: "", crit: "down", na: "" };
const STATUS_VN = { ok: "Trong hạn mức", warn: "Gần hạn mức", crit: "Vượt hạn mức", na: "—" };
const f1 = (n, dp = 1) => (n == null || Number.isNaN(n) ? "—" : n.toLocaleString("en-US", { maximumFractionDigits: dp, minimumFractionDigits: dp }));
const barColor = (s) => (s === "crit" ? "var(--down)" : s === "warn" ? "var(--accent)" : "var(--up)");

function Budget({ items }) {
  return (
    <div className="grid gap-x-6 gap-y-2 sm:grid-cols-2">
      {items.map((i) => {
        const used = i.used_pct == null ? 0 : Math.min(i.used_pct, 100);
        return (
          <div key={i.key} className="min-w-0">
            <div className="flex justify-between gap-2 text-[12px]">
              <span className="truncate text-muted">{i.label}</span>
              <span className="num shrink-0">{i.value == null ? "—" : f1(i.value, 2)}{i.unit} / {i.direction === "min" ? "≥ " : ""}{i.limit}{i.unit}</span>
            </div>
            <div role="progressbar" aria-label={i.label} aria-valuenow={Math.round(used)} aria-valuemin={0} aria-valuemax={100}
              className="mt-1 h-[6px] overflow-hidden rounded bg-panel2">
              <div style={{ width: `${used}%`, background: barColor(i.status) }} className="h-full rounded" />
            </div>
            <div className="mt-[2px] text-[11px] text-faint">{STATUS_VN[i.status]} · {i.used_pct == null ? "—" : `${i.used_pct.toFixed(0)}% hạn mức`}</div>
          </div>
        );
      })}
    </div>
  );
}

function Underwater({ dd }) {
  if (!dd?.available || dd.underwater.length < 2) return <div className="text-muted p-1">Chưa đủ lịch sử equity để vẽ drawdown.</div>;
  const build = () => ({
    animation: false, backgroundColor: "transparent", grid: { left: 46, right: 12, top: 10, bottom: 24 },
    tooltip: { trigger: "axis", backgroundColor: css("--panel2"), borderColor: css("--line2"), textStyle: { color: css("--fg"), fontSize: 12 },
      formatter: (a) => `${dateTime(a[0].value[0])}<br/>Drawdown: <b>${a[0].value[1].toFixed(2)}%</b>` },
    xAxis: { type: "time", axisLabel: { color: css("--muted"), fontSize: 11 }, axisLine: { lineStyle: { color: css("--line2") } }, splitLine: { show: false } },
    yAxis: { type: "value", max: 0, axisLabel: { color: css("--muted"), fontSize: 11, formatter: "{value}%" }, splitLine: { lineStyle: { color: css("--line") } } },
    series: [{ type: "line", data: dd.underwater.map((p) => [p.t * 1000, p.dd]), showSymbol: false, lineStyle: { width: 1.5, color: css("--down") }, areaStyle: { color: css("--down-bg") } }],
  });
  return <EChart build={build} deps={[dd]} height={170} label="Đường drawdown (underwater) của tài khoản" />;
}

function StressBars({ rows }) {
  const mx = Math.max(1, ...rows.map((r) => Math.abs(r.pnl_pct ?? 0)));
  return (
    <div className="scroll-x">
      <table className="tbl" style={{ minWidth: 640 }}>
        <thead><tr><th>Kịch bản</th><th className="r">P&amp;L</th><th className="r">% equity</th><th style={{ width: "28%" }}></th><th className="r">Phủ dữ liệu</th><th>Cờ</th></tr></thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.id}>
              <td><b>{r.name}</b>{r.window && <div className="text-[11px] text-faint">{r.window}</div>}</td>
              <td className={cn("r num", signCls(r.pnl))}>{money(r.pnl)}</td>
              <td className={cn("r num", signCls(r.pnl_pct))}>{pct(r.pnl_pct)}</td>
              <td>
                <div className="h-[8px] rounded bg-panel2" aria-hidden="true">
                  <div style={{ width: `${Math.min(100, Math.abs(r.pnl_pct ?? 0) / mx * 100)}%`, background: (r.pnl ?? 0) < 0 ? "var(--down)" : "var(--up)" }} className="h-full rounded" />
                </div>
              </td>
              <td className="r num text-muted">{f1(r.coverage_pct, 0)}%</td>
              <td>{r.breach_stop_out ? <Chip tone="down">stop-out</Chip> : r.breach_zero ? <Chip tone="down">equity ≤ 0</Chip> : r.coverage_pct < 100 ? <Chip title={`Thiếu dữ liệu: ${r.missing.join(", ")}`}>thiếu dữ liệu</Chip> : null}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function VarTable({ v }) {
  if (!v?.available) return <div className="text-muted p-1">{v?.reason || "Chưa tính được VaR."}</div>;
  const rows = [
    ["Lịch sử", v.hist["95"], v.hist["99"], v.hist.es],
    ["Tham số (σ toàn kỳ)", v.normal["95"], v.normal["99"], v.normal.es],
    ["Tham số EWMA λ=0,94", v.ewma["95"], v.ewma["99"], v.ewma.es],
  ];
  const cell = (c) => <><b>{money(c.var)}</b> <span className="text-faint">({f1(c.var_pct, 2)}%)</span></>;
  const ecell = (c) => <><b>{money(c.es)}</b> <span className="text-faint">({f1(c.es_pct, 2)}%)</span></>;
  const bt = v.backtest;
  return (
    <>
      <div className="scroll-x">
        <table className="tbl" style={{ minWidth: 560 }}>
          <thead><tr><th>Phương pháp (1 ngày)</th><th className="r">VaR 95%</th><th className="r">VaR 99%</th><th className="r">ES 97,5%</th></tr></thead>
          <tbody>{rows.map(([n, a, b, e]) => <tr key={n}><td>{n}</td><td className="r num">{cell(a)}</td><td className="r num">{cell(b)}</td><td className="r num">{ecell(e)}</td></tr>)}</tbody>
        </table>
      </div>
      <p className="mt-2 text-[11.5px] text-faint">
        {v.days} ngày D1 ({v.from} → {v.to}) · phủ {f1(v.coverage_pct, 0)}% giá trị · 10 ngày (căn bậc hai): ES ≈ {money(v.horizons["10"]?.hist_es)} ·
        {bt ? ` backtest EWMA95: ${bt.exceptions}/${bt.days} lần vượt (kỳ vọng ${bt.expected}), Kupiec p=${bt.kupiec_p.toFixed(2)} — ${bt.verdict}.` : " chưa đủ dữ liệu backtest."}
        {" "}Dựng từ lịch sử áp lên vị thế hiện tại; gap/sự kiện cực đoan có thể vượt VaR.
      </p>
    </>
  );
}

function Corr({ v }) {
  if (!v?.available) return null;
  const rc = v.risk_contrib;
  return (
    <div className="grid gap-4 md:grid-cols-2">
      <div>
        <div className="mb-1 text-[12px] text-muted">Đóng góp rủi ro (Euler) · {f1(rc.effective_bets, 1)} "vị thế độc lập" hiệu dụng · DR {f1(rc.diversification_ratio, 2)}</div>
        {rc.items.slice(0, 8).map((it) => (
          <div key={it.symbol} className="flex items-center gap-2 text-[12px]">
            <span className="w-[5.5rem] truncate">{symbolLabel(it.symbol)}</span>
            <div className="h-[6px] flex-1 rounded bg-panel2"><div className="h-full rounded" style={{ width: `${Math.min(100, Math.abs(it.risk_share) * 100)}%`, background: it.risk_share < 0 ? "var(--up)" : "var(--accent)" }} /></div>
            <span className="num w-12 text-right">{f1(it.risk_share * 100, 0)}%</span>
          </div>
        ))}
      </div>
      <div>
        <div className="mb-1 text-[12px] text-muted">Cặp tương quan mạnh nhất ({v.correlation.window_days} ngày) · |ρ| TB {f1(v.correlation.avg_abs_corr, 2)}</div>
        {v.correlation.top_pairs.slice(0, 6).map((p) => (
          <div key={p.a + p.b} className="flex justify-between gap-2 text-[12px]">
            <span className="truncate">{symbolLabel(p.a)} / {symbolLabel(p.b)}</span>
            <span className="num shrink-0">{p.rho.toFixed(2)} {p.effective_same_bet && <Chip tone="down" title="Hai vị thế thực chất là cùng một cược">cùng cược</Chip>}</span>
          </div>
        ))}
        {v.correlation.top_pairs.length === 0 && <div className="text-muted">Chỉ có 1 mã nên chưa có cặp.</div>}
      </div>
    </div>
  );
}

function ExposureTables({ e }) {
  const eqPct = (x) => (x == null ? "—" : `${f1(x, 0)}%`);
  return (
    <div className="grid gap-4 lg:grid-cols-2">
      <div className="scroll-x">
        <table className="tbl" style={{ minWidth: 380 }}>
          <caption className="text-left text-[12px] text-muted pb-1">Theo tiền tệ (net)</caption>
          <thead><tr><th>Tiền tệ</th><th className="r">Net</th><th className="r">% equity</th></tr></thead>
          <tbody>{e.by_currency.length ? e.by_currency.map((c) => <tr key={c.ccy}><td><b>{c.ccy}</b></td><td className={cn("r num", signCls(c.net_value))}>{money(c.net_value)}</td><td className="r num">{eqPct(c.pct_equity)}</td></tr>) : <tr><td colSpan={3} className="text-muted">Không có exposure FX/kim loại.</td></tr>}</tbody>
        </table>
      </div>
      <div className="scroll-x">
        <table className="tbl" style={{ minWidth: 420 }}>
          <caption className="text-left text-[12px] text-muted pb-1">Theo mã ({e.mode === "hedging" ? "hedging: lot mua/bán tách, bù trừ" : e.mode === "netting" ? "netting: 1 vị thế/mã" : "net"})</caption>
          <thead><tr><th>Mã</th><th className="r">Mua</th><th className="r">Bán</th><th className="r">Net</th><th className="r">Giá trị net</th></tr></thead>
          <tbody>{e.by_symbol.slice(0, 12).map((s) => (
            <tr key={s.symbol}><td><b>{symbolLabel(s.symbol)}</b></td><td className="r num">{f1(s.long_lots, 2)}</td><td className="r num">{f1(s.short_lots, 2)}</td>
              <td className="r num">{f1(s.net_lots, 2)}</td><td className={cn("r num", signCls(s.net_value))}>{money(s.net_value)}</td></tr>))}</tbody>
        </table>
      </div>
    </div>
  );
}

function RiskBody({ id }) {
  const q = useRiskAccount(id);
  return (
    <Async q={q} rows={6} empty="Chưa có dữ liệu rủi ro." hint="risk-monitor chưa tính xong chu kỳ đầu.">
      {(r) => {
        const m = r.margin, e = r.exposure, dd = r.drawdown, v = r.var;
        const ddOk = dd?.available;
        return (
          <>
            {r.warnings?.length > 0 && (
              <div role="status" className="flex gap-2 rounded-md border border-line bg-panel2 px-3 py-2 text-[12.5px] text-muted">
                <AlertTriangle size={15} aria-hidden="true" className="mt-[2px] shrink-0" />
                <ul className="min-w-0">{r.warnings.map((w) => <li key={w}>{w}</li>)}</ul>
              </div>
            )}
            <Panel title="Margin, đòn bẩy, drawdown" icon={Gauge} right={<Chip tone={TONE[r.budget.status]}>{STATUS_VN[r.budget.status]}</Chip>}>
              <div className="grid grid-cols-[repeat(auto-fit,minmax(9.5rem,1fr))] gap-4">
                {m ? (
                  <>
                    <Stat label="Mức margin" big value={m.margin_level_pct == null ? "—" : `${f1(m.margin_level_pct, 0)}%`} tone={m.status === "ok" || m.status === "no_position" ? "" : "down"}
                      sub={{ ok: "An toàn", warn: "Thấp, cần chú ý", margin_call: "Dưới mức margin call", stop_out: "Chạm stop-out", no_position: "Không có vị thế" }[m.status]} />
                    <Stat label="Margin tự do" value={money(m.free_margin)} sub={`Margin dùng ${f1(m.margin_used_pct_equity, 0)}% equity`} />
                    <Stat label="Tới stop-out" value={money(m.distance_to_stop_out)} sub={m.adverse_move_pct_gross != null ? `≈ ${f1(m.adverse_move_pct_gross, 2)}% bất lợi (gross) · stop-out ${m.stop_out_pct}%` : `${f1(m.distance_pct_equity, 0)}% equity`} />
                  </>
                ) : <Stat label="Margin" value="—" sub="Tài khoản paper không có margin" />}
                <Stat label="Đòn bẩy hiệu dụng" value={e.leverage_gross == null ? "—" : `${f1(e.leverage_gross, 2)}x`} sub={m?.nominal_leverage ? `Danh nghĩa 1:${m.nominal_leverage}` : `Net ${f1(e.leverage_net, 2)}x`} />
                <Stat label="Lãi/lỗ hôm nay" value={ddOk ? pct(dd.day.pnl_pct) : "—"} tone={ddOk ? signCls(dd.day.pnl_pct) : ""} sub={ddOk ? `Tuần ${pct(dd.week.pnl_pct)}` : ""} />
                <Stat label="Drawdown từ đỉnh" value={ddOk ? pct(dd.dd_from_peak_pct) : "—"} tone={ddOk ? signCls(dd.dd_from_peak_pct) : ""} sub={ddOk ? `Tối đa ${pct(dd.max_dd_pct)}` : ""} />
                <Stat label="ES 97,5% / 1 ngày" value={v.available ? `${f1(v.hist.es.es_pct, 2)}%` : "—"} sub={v.available ? money(v.hist.es.es) : ""} />
              </div>
            </Panel>
            <Panel title="Ngân sách rủi ro" icon={ShieldAlert}><Budget items={r.budget.items} /></Panel>
            <div className="grid gap-3 lg:grid-cols-2">
              <Panel title="Drawdown (underwater)" icon={TrendingDown}><Underwater dd={dd} /></Panel>
              <Panel title="VaR / ES" icon={Layers} pad><VarTable v={v} /></Panel>
            </div>
            <Panel title="Exposure" icon={Layers}>
              {e.positions === 0 ? <div className="text-muted">Không có vị thế mở.</div> : <ExposureTables e={e} />}
            </Panel>
            <Panel title="Stress test (áp lên vị thế hiện tại)" icon={Zap} pad={false}>
              {r.stress.length ? <StressBars rows={r.stress} /> : <div className="p-3 text-muted">Không có vị thế để stress.</div>}
              <p className="px-3 pb-2 text-[11.5px] text-faint">Kịch bản lịch sử dùng biến động giá thật từ bars D1 trong cửa sổ nêu trên; kịch bản giả định chỉnh trong cấu hình. Chưa tính trượt giá/gap/spread giãn: thực tế có thể xấu hơn.</p>
            </Panel>
            {v.available && <Panel title="Tương quan & đóng góp rủi ro" icon={Network}><Corr v={v} /></Panel>}
            <p className="text-[11.5px] text-faint">{r.disclaimer} Cập nhật {dateTime(r.generated_at)}.</p>
          </>
        );
      }}
    </Async>
  );
}

export function RiskSection() {
  const q = useRiskAccounts();
  const [sel, setSel] = useState("");
  const list = (q.data?.accounts || []).filter((a) => !a.error);
  const pick = list.find((a) => a.account_id === sel) ||
    list.find((a) => a.kind === "mt" && a.positions > 0) || list.find((a) => a.kind === "paper" && a.meaningful && a.positions > 0) || list[0];
  useEffect(() => { if (pick && pick.account_id !== sel) setSel(pick.account_id); }, [pick?.account_id]); // eslint-disable-line react-hooks/exhaustive-deps
  return (
    <section aria-label="Rủi ro tài khoản" className="grid gap-3">
      <div className="flex flex-wrap items-center gap-2">
        <h2 className="text-[15px] font-semibold">Rủi ro tài khoản</h2>
        <Chip tone="ro">READ-ONLY · ước tính</Chip>
        {pick?.kind === "paper" && <Chip title="Tài khoản mô phỏng (paper), dùng engine rủi ro giống tài khoản MT">MÔ PHỎNG</Chip>}
      </div>
      <Async q={q} rows={3} isEmpty={(d) => !d?.accounts?.length} empty="Chưa có tài khoản nào để tính rủi ro." hint="Cần snapshot MT (mt-bridge) hoặc tài khoản paper.">
        {() => (
          <>
            <div className="scroll-x">
              <Seg value={pick.account_id} onChange={setSel} label="Chọn tài khoản để xem rủi ro"
                options={list.filter((a) => !a.error).map((a) => ({ value: a.account_id, label: `${a.account_id}${a.kind === "paper" ? " · paper" : ` · ${a.platform.toUpperCase()}`}` }))} />
            </div>
            {pick && <RiskBody id={pick.account_id} />}
          </>
        )}
      </Async>
    </section>
  );
}
