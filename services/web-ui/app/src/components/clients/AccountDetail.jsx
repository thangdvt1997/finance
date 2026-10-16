import { useState } from "react";
import { Dialog } from "../dialog";
import { Async, Chip, Panel, Stat } from "../ui";
import { EChart, css } from "../charts";
import { ageText } from "../../lib/freshness";
import { clean, dateTime, money, pct, signCls, time, date } from "../../lib/format";
import { AUDIT_TONE, AUDIT_VN, isMasterActor, useAdminDetail, useEquityHist, useJnQuick } from "../../lib/clientsQueries";
import { ACTIONS, ConfirmDialog } from "./ActionDialogs";
import { HealthChip, KV, RiskChip, StatusChip, fmtDT } from "./bits";
import ViewAsDialog from "../fleet/ViewAsDialog";

export function EquitySpark({ id }) {
  const q = useEquityHist(id, 7);
  return (
    <Async q={q} rows={3} empty="Chưa có lịch sử equity 7 ngày." isEmpty={(d) => !d?.length}>
      {(pts) => {
        const build = () => {
          const eq = pts.map((p) => [Date.parse(p.ts), p.equity]);
          const vals = pts.map((p) => p.equity).filter((v) => v != null); const lo = Math.min(...vals), hi = Math.max(...vals), pad = (hi - lo) * 0.15 || 1;
          const ax = { axisLine: { lineStyle: { color: css("--line2") } }, axisLabel: { color: css("--muted"), fontSize: 10.5 }, splitLine: { lineStyle: { color: css("--line") } } };
          return { animation: false, backgroundColor: "transparent", grid: { left: 54, right: 8, top: 8, bottom: 20 },
            tooltip: { trigger: "axis", backgroundColor: css("--panel2"), borderColor: css("--line2"), textStyle: { color: css("--fg"), fontSize: 12 }, formatter: (a) => `${dateTime(a[0].value[0])}<br/>Equity: <b>${money(a[0].value[1])}</b>` },
            xAxis: { type: "time", ...ax, splitLine: { show: false }, axisLabel: { ...ax.axisLabel, formatter: (v) => date(v) } },
            yAxis: { type: "value", min: lo - pad, max: hi + pad, ...ax, axisLabel: { ...ax.axisLabel, formatter: (v) => Math.round(v).toLocaleString("en-US") } },
            series: [{ type: "line", data: eq, showSymbol: false, lineStyle: { width: 2, color: css("--accent") }, areaStyle: { color: css("--accent-bg") } }] };
        };
        return <EChart build={build} deps={[pts]} height={150} label={`Equity 7 ngày của ${id}`} />;
      }}
    </Async>
  );
}

export function Quick({ row }) {
  const jn = useJnQuick(row.account_id);
  const s = jn.data;
  return (
    <div className="grid grid-cols-[repeat(auto-fit,minmax(8.5rem,1fr))] gap-3">
      <Stat label="Equity" value={row.equity == null ? "—" : money(row.equity)} big />
      <Stat label="Balance" value={row.balance == null ? "—" : money(row.balance)} />
      <Stat label="Lãi/lỗ đang mở" value={row.floating == null ? "—" : money(row.floating)} tone={signCls(row.floating)} sub={`${row.posCount} vị thế`} />
      <Stat label="Mức margin" value={row.marginLevel == null ? "—" : `${row.marginLevel.toFixed(0)}%`} tone={row.marginLevel != null && row.marginLevel < 150 ? "down" : ""} />
      <Stat label="Drawdown từ đỉnh" value={row.dd == null ? "—" : `${row.dd.toFixed(1)}%`} tone={row.dd >= 10 ? "down" : ""} />
      <Stat label="P/L hôm nay" value={pct(row.dayPnlPct)} tone={signCls(row.dayPnlPct)} />
      <Stat label="Win rate (nhật ký)" value={s?.win_rate == null ? "—" : `${(s.win_rate * 100).toFixed(0)}%`} sub={s ? `${s.n} lệnh · ${s.wins} thắng` : jn.isError ? "chưa có nhật ký" : "đang tải…"} />
      <Stat label="Net P/L (nhật ký)" value={s ? money(s.net) : "—"} tone={s ? signCls(s.net) : ""} sub={s?.profit_factor != null ? `PF ${s.profit_factor.toFixed(2)}` : undefined} />
    </div>
  );
}

const sideOf = (p) => (p.type === 1 || String(p.side).toLowerCase() === "sell" ? "Bán" : "Mua");

export default function AccountDetail({ id, rows, onClose, onView, onToast }) {
  const row = rows?.find((r) => r.account_id === id);
  const q = useAdminDetail(row);
  const [act, setAct] = useState(null);
  const d = q.data;
  const locked = row && ((row.locked_until && Date.parse(row.locked_until) > Date.now()) || row.failed_attempts > 0);
  const btn = (k, disabled) => { const A = ACTIONS[k]; return <button key={k} className="btn" disabled={disabled} onClick={() => setAct(k)}><A.icon size={13} aria-hidden="true" />{A.label}</button>; };

  return (
    <>
      <Dialog open onClose={onClose} variant="drawer" title={row ? `${row.label || row.login} · ${row.account_id}` : id}>
        <div className="p-3 grid gap-3">
          {!row ? (
            <p className="m-0 text-muted">Không tìm thấy tài khoản <span className="num">{id}</span> trong danh sách (có thể đã bị xoá).</p>
          ) : (
            <>
              <div className="flex flex-wrap items-center gap-2">
                <StatusChip status={row.status} /><HealthChip row={row} /><RiskChip level={row.riskLevel} reasons={row.riskReasons} />
                {row.failed_attempts > 0 && <Chip tone="accent">{row.failed_attempts} lần sai</Chip>}
                {row.locked_until && Date.parse(row.locked_until) > Date.now() && <Chip tone="down">Khoá tạm đến {time(row.locked_until)}</Chip>}
              </div>
              {row.riskReasons.length > 0 && <p role="note" className="m-0 text-[12.5px] text-muted">{row.riskReasons.join(" · ")}</p>}

              <div className="flex flex-wrap gap-2" role="group" aria-label="Hành động quản trị">
                {btn("passcode")}{btn("pairing")}{btn("rotate")}
                {row.status === "suspended" ? btn("activate") : btn("suspend", row.status === "pending")}
                {btn("logout", !(row.sessions_open > 0))}
                {locked && btn("unlock")}
                {btn("impersonate", row.status === "pending")}
                {btn("delete")}
              </div>

              <Panel title="Thống kê nhanh"><Quick row={row} /></Panel>
              {row.status !== "pending" && <Panel title="Equity 7 ngày" bodyClass="flex flex-col"><EquitySpark id={row.account_id} /></Panel>}

              <div className="grid gap-3 md:grid-cols-2">
                <Panel title="Hồ sơ" pad={false}><dl className="m-0 px-3 py-1">
                  <KV k="Khách hàng">{row.client_name}</KV><KV k="Nền tảng" mono>{row.platform.toUpperCase()}</KV><KV k="Số tài khoản" mono>{row.login}</KV><KV k="Server">{row.server}</KV>
                  <KV k="Tạo lúc">{fmtDT(row.created_at)}</KV><KV k="Đăng nhập cuối">{fmtDT(row.last_login_at)}</KV>
                  <KV k="Ghép cặp">{row.pairing_pending ? `Đang chờ · hạn ${fmtDT(row.pairing_expires_at)}${Date.parse(row.pairing_expires_at) < Date.now() ? " (đã hết hạn)" : ""}` : "Đã ghép"}</KV>
                  <KV k="Ghi chú">{row.notes}</KV></dl></Panel>
                <Panel title="Kết nối EA" pad={false}><dl className="m-0 px-3 py-1">
                  <KV k="Phiên bản EA" mono>{row.ea_version}{row.eaOutdated ? " (có bản mới)" : ""}</KV><KV k="Build terminal" mono>{row.terminal_build}</KV>
                  <KV k="Dữ liệu cuối">{row.lastData ? `${fmtDT(row.lastData)} · ${ageText(row.age)}` : "Chưa có"}</KV>
                  <KV k="Độ trễ snapshot" mono>{row.snapAge == null ? "—" : ageText(row.snapAge)}</KV><KV k="Độ trễ mạng EA" mono>{row.latency_ms == null ? "—" : `${row.latency_ms} ms`}</KV>
                  <KV k="Đòn bẩy hiệu dụng" mono>{row.leverage == null ? "—" : `${row.leverage.toFixed(1)}×`}</KV><KV k="Exposure ước tính" mono>{row.exposure == null ? "—" : money(row.exposure)}</KV></dl></Panel>
              </div>

              {row.positions.length > 0 && (
                <Panel title={`Vị thế đang mở (${row.positions.length})`} pad={false}><div className="scroll-x"><table className="tbl" style={{ minWidth: 420 }}>
                  <thead><tr><th>Symbol</th><th>Hướng</th><th className="r">Khối lượng</th><th className="r">Lãi/lỗ</th></tr></thead>
                  <tbody>{row.positions.map((p) => <tr key={p.ticket}><td>{p.symbol}</td><td>{sideOf(p)}</td><td className="r num">{p.volume}</td><td className={`r num ${signCls(p.profit)}`}>{money(p.profit)}</td></tr>)}</tbody></table></div></Panel>
              )}

              <Panel title={`Phiên đang mở (${d?.sessions?.length ?? row.sessions_open ?? 0})`} pad={false}>
                <Async q={q} rows={2} isEmpty={(x) => !x?.sessions?.length} empty="Không có phiên nào đang mở.">
                  {(x) => <div className="scroll-x"><table className="tbl" style={{ minWidth: 480 }}><thead><tr><th>Bắt đầu</th><th>Hoạt động cuối</th><th>IP</th><th>Thiết bị</th></tr></thead>
                    <tbody>{x.sessions.map((s) => <tr key={s.id}><td>{fmtDT(s.created_at)}</td><td>{fmtDT(s.last_seen_at)}</td><td className="num">{s.ip}</td><td>{s.user_agent}</td></tr>)}</tbody></table></div>}
                </Async>
              </Panel>

              <Panel title="Lịch sử đăng nhập" pad={false}>
                <Async q={q} rows={3} isEmpty={(x) => !x?.history?.length} empty="Chưa có lượt đăng nhập nào.">
                  {(x) => <div className="scroll-x"><table className="tbl" style={{ minWidth: 480 }}><thead><tr><th>Thời gian</th><th>Sự kiện</th><th>IP</th><th>Chi tiết</th></tr></thead>
                    <tbody>{x.history.slice(0, 15).map((h) => <tr key={h.id}><td>{fmtDT(h.ts)}</td><td><Chip tone={h.action === "login_ok" || h.action === "pair_ok" ? "up" : AUDIT_TONE[h.action] || ""}>{AUDIT_VN[h.action] || h.action}</Chip></td><td className="num">{h.ip}</td><td className="text-muted">{h.detail?.reason || ""}</td></tr>)}</tbody></table></div>}
                </Async>
              </Panel>

              {row.lastAlert && <Panel title="Cảnh báo gần nhất"><div className="flex flex-wrap items-center gap-2 text-[12.5px]"><Chip tone={row.lastAlert.level === "crit" ? "down" : "accent"}>{row.lastAlert.level === "crit" ? "Nghiêm trọng" : "Cảnh báo"}</Chip>{clean(row.lastAlert.title)}<span className="ml-auto text-faint">{fmtDT(row.lastAlert.ts)}</span></div></Panel>}

              <Panel title="Hoạt động quản trị gần đây" pad={false}>
                <Async q={q} rows={2} isEmpty={(x) => !x?.events?.length} empty="Chưa có hoạt động quản trị.">
                  {(x) => <ul className="m-0 p-0 list-none divide-y divide-line">{x.events.slice(0, 8).map((e) => (
                    <li key={e.id} className="flex flex-wrap items-center gap-2 px-3 py-2 text-[12.5px]"><Chip tone={AUDIT_TONE[e.action]}>{AUDIT_VN[e.action] || e.action}</Chip><span className="text-muted">{isMasterActor(e.actor_label) ? e.actor_label : "hệ thống"}</span>
                      <span className="ml-auto text-faint">{fmtDT(e.ts)}</span></li>))}</ul>}
                </Async>
              </Panel>
            </>
          )}
        </div>
      </Dialog>
      {act === "impersonate" && row && <ViewAsDialog open accountId={row.account_id} label={row.label} onClose={() => setAct(null)} />}
      {act && act !== "impersonate" && row && <ConfirmDialog kind={act} row={row} onClose={() => setAct(null)} onDone={(k) => { if (k === "impersonate") { onView(row.account_id); return; } onToast?.(`${ACTIONS[k].label}: đã thực hiện cho ${row.account_id}.`); if (k === "delete") onClose(); }} />}
    </>
  );
}
